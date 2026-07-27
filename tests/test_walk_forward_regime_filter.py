import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from app.candle import Candle
from app.candle_mapper import dataframe_to_candles
from app.ema_cross_strategy import EMACrossStrategy
from app.engine import BacktestEngine
from app.market_regime import (
    MarketRegime,
    MarketRegimeDetector,
    MarketTrend,
    MarketVolatility,
)
from app.regime_filter_research import (
    CausalRegimeCache,
    ResearchConfig,
    WarmupStrategy,
    _run_variant,
    build_analysis,
    build_windows,
    compounded_diagnostics,
    fingerprint_candles,
    research_verdict,
    run_walk_forward,
    summarize,
)
from app.regime_filtered_strategy import RegimeFilteredStrategy
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_filter import TradingFilter
from app.trading_types import ExitReason, TradeAction
from scripts import walk_forward_regime_filter as script


def market_data(
    start: str = "2020-01-01",
    periods: int = 1100,
    freq: str = "D",
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    closes = [
        100 + index * 0.015 + ((index % 20) - 10) * 0.4
        for index in range(periods)
    ]
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": 10.0,
        }
    )


def small_config(**changes) -> ResearchConfig:
    return replace(
        ResearchConfig(
            fast_ema=2,
            slow_ema=4,
            train_months=6,
            test_months=3,
            step_months=3,
        ),
        **changes,
    )


def test_build_windows_has_half_open_boundaries_and_exact_step() -> None:
    data = market_data()
    windows = build_windows(data, small_config(max_windows=3))

    assert len(windows) == 3
    for window in windows:
        assert window.train_end == window.test_start
        train = data[
            (data.datetime >= window.train_start)
            & (data.datetime < window.train_end)
        ]
        test = data[
            (data.datetime >= window.test_start)
            & (data.datetime < window.test_end)
        ]
        assert set(train.datetime).isdisjoint(test.datetime)
        assert test.datetime.iloc[0] == window.test_start
        combined = pd.concat([train, test]).sort_index()
        expected = data[
            (data.datetime >= window.train_start)
            & (data.datetime < window.test_end)
        ]
        assert combined.index.tolist() == expected.index.tolist()
    assert (
        windows[1].train_start
        == windows[0].train_start + pd.DateOffset(months=3)
    )


def test_windows_preserve_timezone_and_drop_incomplete_tail() -> None:
    data = market_data(periods=400)
    data["datetime"] = data["datetime"].dt.tz_convert("Asia/Tokyo")
    windows = build_windows(
        data,
        small_config(
            train_months=6,
            test_months=3,
            step_months=3,
        ),
    )

    assert len(windows) == 2
    assert str(windows[0].test_start.tz) == "Asia/Tokyo"
    assert windows[-1].test_end <= (
        data.datetime.iloc[-1] + pd.Timedelta(days=1)
    )
    next_train_start = windows[-1].train_start + pd.DateOffset(months=3)
    next_test_end = next_train_start + pd.DateOffset(months=9)
    assert next_test_end > data.datetime.iloc[-1] + pd.Timedelta(days=1)


def test_warmup_updates_strategy_but_suppresses_train_signals() -> None:
    class RecordingStrategy:
        def __init__(self):
            self.indexes = []

        def generate_signal(self, candles, index):
            self.indexes.append(index)
            return Signal.BUY

    base = RecordingStrategy()
    strategy = WarmupStrategy(base, trade_start_index=2)
    candles = [Candle(i, 100, 101, 99, 100) for i in range(4)]

    signals = [
        strategy.generate_signal(candles, index) for index in range(4)
    ]

    assert signals == [Signal.HOLD, Signal.HOLD, Signal.BUY, Signal.BUY]
    assert base.indexes == [0, 1, 2, 3]


def test_train_never_trades_or_transfers_position() -> None:
    data = market_data(periods=500)
    config = small_config(max_windows=1)
    window = build_windows(data, config)[0]
    train = data[data.datetime < window.train_end]
    test = data[
        (data.datetime >= window.test_start)
        & (data.datetime < window.test_end)
    ]
    from app.candle_mapper import dataframe_to_candles

    history = dataframe_to_candles(pd.concat([train, test]))
    cache = CausalRegimeCache(
        MarketRegimeDetector(2, 4),
        window_id="one",
    )
    item, result = _run_variant(
        history,
        trade_start_index=len(train),
        window=window,
        variant="baseline",
        config=config,
        cache=cache,
    )

    assert result.initial_balance == config.initial_balance
    assert all(
        trade.entry_timestamp >= int(window.test_start.timestamp())
        for trade in result.trades
    )
    assert item.initial_balance == config.initial_balance


def test_every_window_has_independent_balance_and_state() -> None:
    results = run_walk_forward(
        market_data(),
        small_config(max_windows=2),
    )

    assert all(item.initial_balance == 1000 for item in results)
    assert [item.window_number for item in results].count(1) == 3
    assert [item.window_number for item in results].count(2) == 3


def test_every_window_builds_fresh_research_objects(monkeypatch) -> None:
    from app import regime_filter_research as research

    created = {
        "ema": [],
        "wrapper": [],
        "detector": [],
        "cache": [],
        "engine": [],
    }

    def recorder(name, original):
        def create(*args, **kwargs):
            item = original(*args, **kwargs)
            created[name].append(item)
            return item

        return create

    monkeypatch.setattr(
        research,
        "EMACrossStrategy",
        recorder("ema", research.EMACrossStrategy),
    )
    monkeypatch.setattr(
        research,
        "RegimeFilteredStrategy",
        recorder("wrapper", research.RegimeFilteredStrategy),
    )
    monkeypatch.setattr(
        research,
        "MarketRegimeDetector",
        recorder("detector", research.MarketRegimeDetector),
    )
    monkeypatch.setattr(
        research,
        "CausalRegimeCache",
        recorder("cache", research.CausalRegimeCache),
    )
    monkeypatch.setattr(
        research,
        "BacktestEngine",
        recorder("engine", research.BacktestEngine),
    )

    run_walk_forward(market_data(), small_config(max_windows=2))

    assert len(created["ema"]) == 6
    assert len(created["wrapper"]) == 4
    # One detector is constructed by config validation; the remaining
    # two are the independent detector instances for the two windows.
    assert len(created["detector"]) == 3
    assert len(created["cache"]) == 2
    assert len(created["engine"]) == 6
    assert all(
        len(items) == len({id(item) for item in items})
        for items in created.values()
    )


def test_fingerprint_and_cache_distinguish_ohlc_and_windows() -> None:
    first = [
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 100, 102, 99, 101, 1),
    ]
    changed = [first[0], Candle(2, 100, 103, 98, 102, 2)]
    assert fingerprint_candles(first) != fingerprint_candles(changed)
    regime = MarketRegime(
        MarketTrend.TREND_UP, MarketVolatility.NORMAL, 1
    )
    detector_one = Mock()
    detector_one.detect.return_value = regime
    detector_two = Mock()
    detector_two.detect.return_value = regime
    cache_one = CausalRegimeCache(detector_one, window_id="one")
    cache_two = CausalRegimeCache(detector_two, window_id="two")

    cache_one.detect_at(first, 1)
    cache_one.detect_at(first, 1)
    cache_one.detect_at(changed, 1)
    cache_two.detect_at(first, 1)

    assert detector_one.detect.call_count == 2
    assert detector_two.detect.call_count == 1


def test_detector_only_equals_baseline_and_never_blocks() -> None:
    results = run_walk_forward(
        market_data(periods=500),
        small_config(max_windows=1),
    )
    baseline, detector_only, _ = results

    for field in (
        "final_balance",
        "return_percent",
        "maximum_drawdown_percent",
        "profit_factor",
        "win_rate_percent",
        "trade_count",
        "winning_trades",
        "losing_trades",
        "total_fees",
        "gross_profit",
        "gross_loss",
    ):
        assert getattr(detector_only, field) == getattr(baseline, field)
    assert detector_only.blocked_entries == 0


def test_detector_only_full_backtest_result_equals_baseline() -> None:
    data = market_data(periods=500)
    config = small_config(max_windows=1)
    window = build_windows(data, config)[0]
    train = data[
        (data.datetime >= window.train_start)
        & (data.datetime < window.train_end)
    ]
    test = data[
        (data.datetime >= window.test_start)
        & (data.datetime < window.test_end)
    ]
    history = dataframe_to_candles(pd.concat([train, test]))
    cache = CausalRegimeCache(MarketRegimeDetector(2, 4))

    baseline = _run_variant(
        history,
        trade_start_index=len(train),
        window=window,
        variant="baseline",
        config=config,
        cache=cache,
    )
    detector_only = _run_variant(
        history,
        trade_start_index=len(train),
        window=window,
        variant="detector_only",
        config=config,
        cache=cache,
    )

    assert detector_only[1] == baseline[1]
    assert detector_only[1].trades == baseline[1].trades


def test_filtered_preserves_exit_and_stop_loss() -> None:
    class StopStrategy:
        def generate_signal(self, candles, index):
            if index == 0:
                return TradeSignal(
                    action=TradeAction.OPEN_LONG,
                    stop_loss=95,
                )
            return TradeAction.HOLD

    detector = Mock()
    detector.detect.return_value = MarketRegime(
        MarketTrend.TREND_UP, MarketVolatility.NORMAL, 1
    )
    strategy = RegimeFilteredStrategy(
        StopStrategy(), detector, TradingFilter()
    )
    candles = [
        Candle(1, 100, 101, 99, 100),
        Candle(2, 100, 101, 94, 96),
    ]

    result = BacktestEngine().run(candles, strategy)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason is ExitReason.STOP_LOSS


def test_future_change_cannot_change_past_decisions_or_trades() -> None:
    original = dataframe_to_candles(market_data(periods=80))
    changed = list(original)
    changed[60] = Candle(
        changed[60].timestamp,
        changed[60].open * 2,
        changed[60].high * 2,
        changed[60].low * 2,
        changed[60].close * 2,
        changed[60].volume,
    )

    def decisions(candles):
        class RecordingDetector:
            def __init__(self):
                self.detector = MarketRegimeDetector(2, 4)
                self.regimes = []

            def detect(self, prefix):
                regime = self.detector.detect(prefix)
                self.regimes.append(regime)
                return regime

        detector = RecordingDetector()
        strategy = RegimeFilteredStrategy(
            EMACrossStrategy(2, 4),
            detector,
            TradingFilter(),
        )
        signals = []
        statistics = []
        for index in range(60):
            signals.append(strategy.generate_signal(candles, index))
            statistics.append(strategy.statistics)
        execution_detector = RecordingDetector()
        execution_strategy = RegimeFilteredStrategy(
            EMACrossStrategy(2, 4),
            execution_detector,
            TradingFilter(),
        )
        result = BacktestEngine().run(candles[:60], execution_strategy)
        return signals, statistics, detector.regimes, result

    assert decisions(original) == decisions(changed)


def test_blocked_reason_sum_is_exact() -> None:
    baseline, detector_only, filtered = run_walk_forward(
        market_data(periods=500),
        small_config(max_windows=1),
    )

    assert filtered.blocked_entries == sum(
        (
            filtered.blocked_range,
            filtered.blocked_downtrend,
            filtered.blocked_high_volatility,
            filtered.blocked_low_confidence,
            filtered.blocked_unknown,
        )
    )
    assert baseline.blocked_entries == 0
    assert detector_only.blocked_entries == 0
    assert (
        filtered.allowed_entries + filtered.blocked_entries
        == baseline.allowed_entries
        == detector_only.allowed_entries
    )


def test_cached_and_plain_detector_are_equivalent() -> None:
    data = market_data(periods=500)
    config = small_config(max_windows=1)
    window = build_windows(data, config)[0]
    train = data[
        (data.datetime >= window.train_start)
        & (data.datetime < window.train_end)
    ]
    test = data[
        (data.datetime >= window.test_start)
        & (data.datetime < window.test_end)
    ]
    history = dataframe_to_candles(pd.concat([train, test]))

    class PlainDetector:
        def __init__(self):
            self.detector = MarketRegimeDetector(2, 4)

        def detect_at(self, candles, index):
            return self.detector.detect(candles[: index + 1])

    cached = _run_variant(
        history,
        trade_start_index=len(train),
        window=window,
        variant="filtered",
        config=config,
        cache=CausalRegimeCache(MarketRegimeDetector(2, 4)),
    )
    plain = _run_variant(
        history,
        trade_start_index=len(train),
        window=window,
        variant="filtered",
        config=config,
        cache=PlainDetector(),
    )

    assert cached == plain


@pytest.mark.parametrize(
    "config",
    [
        small_config(train_months=0),
        small_config(test_months=0),
        small_config(step_months=0),
        small_config(fast_ema=5, slow_ema=4),
        small_config(fee_rate=-0.1),
        small_config(initial_balance=0),
    ],
)
def test_invalid_configuration_is_rejected(config) -> None:
    with pytest.raises(ValueError):
        config.validate()


def test_insufficient_data_is_clear() -> None:
    with pytest.raises(ValueError, match="not enough data"):
        build_windows(market_data(periods=30), small_config())


def test_json_and_csv_are_atomic_and_deterministic(tmp_path) -> None:
    data = market_data(periods=500)
    data_path = tmp_path / "market.csv"
    data.to_csv(data_path, index=False)
    json_path = tmp_path / "nested/report.json"
    csv_path = tmp_path / "nested/report.csv"
    arguments = [
        "--data",
        str(data_path),
        "--fast-period",
        "2",
        "--slow-period",
        "4",
        "--train-months",
        "6",
        "--test-months",
        "3",
        "--step-months",
        "3",
        "--max-windows",
        "1",
        "--output-json",
        str(json_path),
        "--output-csv",
        str(csv_path),
    ]

    assert script.main(arguments) == 0
    first_json = json_path.read_bytes()
    first_csv = csv_path.read_bytes()
    assert script.main(arguments) == 0

    report = json.loads(json_path.read_text())
    assert len(report["data_fingerprint_sha256"]) == 64
    assert json_path.read_bytes() == first_json
    assert csv_path.read_bytes() == first_csv
    assert not list(json_path.parent.glob("*.tmp"))


@pytest.mark.parametrize("writer", ["json", "csv"])
def test_atomic_output_failure_preserves_existing_file(
    tmp_path,
    monkeypatch,
    writer,
) -> None:
    output = tmp_path / f"report.{writer}"
    output.write_text("original\n", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        if writer == "json":
            script.save_json(output, {"result": 1})
        else:
            results = run_walk_forward(
                market_data(periods=500),
                small_config(max_windows=1),
            )
            script.save_csv(output, results)

    assert output.read_text(encoding="utf-8") == "original\n"
    assert not list(tmp_path.glob(f".{output.name}.*"))


def test_cli_works_from_another_cwd(tmp_path) -> None:
    data_path = tmp_path / "market.csv"
    market_data(periods=500).to_csv(data_path, index=False)
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(script.__file__).resolve()),
            "--data",
            str(data_path),
            "--fast-period",
            "2",
            "--slow-period",
            "4",
            "--train-months",
            "6",
            "--test-months",
            "3",
            "--max-windows",
            "1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Verdict:" in completed.stdout
    assert {path.name for path in tmp_path.iterdir()} == {"market.csv"}


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--fast-period", "50", "--slow-period", "20"], "fast EMA"),
        (["--train-months", "0"], "greater than zero"),
        (["--fee-rate", "1"], "between 0 and 1"),
        (["--initial-balance", "0"], "greater than zero"),
    ],
)
def test_cli_rejects_invalid_arguments(arguments, message, capsys) -> None:
    with pytest.raises(SystemExit) as captured:
        script.main(arguments)

    assert captured.value.code == 2
    assert message in capsys.readouterr().err


def test_verdict_uses_fixed_criteria_and_few_windows_inconclusive() -> None:
    baseline = {
        "windows": 2,
        "worst_return_percent": -2,
        "median_profit_factor": 1,
    }
    filtered = {
        "worst_return_percent": 1,
        "median_profit_factor": 2,
        "mean_trades_per_window": 5,
    }
    comparison = {
        "filtered_better_return": 2,
        "filtered_lower_drawdown": 2,
        "filtered_better_return_and_drawdown": 2,
    }

    assert research_verdict(baseline, filtered, comparison) == "INCONCLUSIVE"


def test_analysis_contains_summary_comparison_compounding_and_verdict() -> None:
    results = run_walk_forward(
        market_data(periods=500),
        small_config(max_windows=1),
    )

    analysis = build_analysis(results, 1000)

    assert set(analysis["summary"]) == {"baseline", "filtered"}
    assert "filtered_better_return" in analysis["comparison"]
    assert "baseline_compounded_final_balance" in analysis[
        "compounded_diagnostics"
    ]
    baseline = analysis["summary"]["baseline"]
    filtered = analysis["summary"]["filtered"]
    compounded = analysis["compounded_diagnostics"]
    assert baseline["compounded_return_percent"] == compounded[
        "baseline_compounded_return_percent"
    ]
    assert filtered["compounded_return_percent"] == compounded[
        "filtered_compounded_return_percent"
    ]
    assert sum(filtered["blocked_by_reason"].values()) == filtered[
        "total_blocked_entries"
    ]
    assert analysis["comparison"][
        "compounded_return_difference_points"
    ] == pytest.approx(
        filtered["compounded_return_percent"]
        - baseline["compounded_return_percent"]
    )
    assert analysis["verdict"] == "INCONCLUSIVE"


def test_compounding_multiplies_mixed_window_returns() -> None:
    template = run_walk_forward(
        market_data(periods=500),
        small_config(max_windows=1),
    )[0]
    results = [
        replace(
            template,
            window_number=1,
            variant="baseline",
            return_percent=10.0,
        ),
        replace(
            template,
            window_number=2,
            variant="baseline",
            return_percent=-20.0,
        ),
        replace(
            template,
            window_number=1,
            variant="filtered",
            return_percent=-10.0,
        ),
        replace(
            template,
            window_number=2,
            variant="filtered",
            return_percent=30.0,
        ),
    ]

    compounded = compounded_diagnostics(results, 1000.0)

    assert compounded["baseline_compounded_final_balance"] == pytest.approx(
        1000 * 1.10 * 0.80
    )
    assert compounded["baseline_compounded_return_percent"] == pytest.approx(
        -12.0
    )
    assert compounded["filtered_compounded_final_balance"] == pytest.approx(
        1000 * 0.90 * 1.30
    )
    assert compounded["filtered_compounded_return_percent"] == pytest.approx(
        17.0
    )


def test_summary_calculates_all_required_aggregates() -> None:
    template = run_walk_forward(
        market_data(periods=500),
        small_config(max_windows=1),
    )[0]
    rows = [
        replace(
            template,
            window_number=1,
            return_percent=10.0,
            maximum_drawdown_percent=5.0,
            profit_factor=2.0,
            trade_count=3,
            total_fees=4.0,
        ),
        replace(
            template,
            window_number=2,
            return_percent=-4.0,
            maximum_drawdown_percent=9.0,
            profit_factor=0.0,
            trade_count=1,
            total_fees=2.0,
        ),
    ]

    summary = summarize(rows, "baseline")

    assert summary["windows"] == 2
    assert summary["profitable_windows"] == 1
    assert summary["losing_windows"] == 1
    assert summary["mean_return_percent"] == 3.0
    assert summary["median_return_percent"] == 3.0
    assert summary["worst_return_percent"] == -4.0
    assert summary["best_return_percent"] == 10.0
    assert summary["mean_maximum_drawdown_percent"] == 7.0
    assert summary["worst_maximum_drawdown_percent"] == 9.0
    assert summary["mean_profit_factor"] == 1.0
    assert summary["total_trades"] == 4
    assert summary["total_fees"] == 6.0


def test_profit_factor_zero_and_infinity_are_preserved() -> None:
    template = run_walk_forward(
        market_data(periods=500),
        small_config(max_windows=1),
    )[0]
    no_trades = replace(template, profit_factor=0.0, trade_count=0)
    no_losses = replace(
        template,
        window_number=2,
        profit_factor=float("inf"),
    )

    assert summarize([no_trades], "baseline")["mean_profit_factor"] == 0.0
    assert summarize(
        [no_trades, no_losses],
        "baseline",
    )["mean_profit_factor"] == float("inf")
