import json
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
    fingerprint_candles,
    research_verdict,
    run_walk_forward,
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
    assert (
        windows[1].train_start
        == windows[0].train_start + pd.DateOffset(months=3)
    )


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

    cache_one.detect(first)
    cache_one.detect(first)
    cache_one.detect(changed)
    cache_two.detect(first)

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
    filtered = run_walk_forward(
        market_data(periods=500),
        small_config(max_windows=1),
    )[2]

    assert filtered.blocked_entries == sum(
        (
            filtered.blocked_range,
            filtered.blocked_downtrend,
            filtered.blocked_high_volatility,
            filtered.blocked_low_confidence,
            filtered.blocked_unknown,
        )
    )


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
        "--fast-ema",
        "2",
        "--slow-ema",
        "4",
        "--train-months",
        "6",
        "--test-months",
        "3",
        "--step-months",
        "3",
        "--max-windows",
        "1",
        "--json-output",
        str(json_path),
        "--csv-output",
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


def test_cli_works_from_another_cwd(tmp_path) -> None:
    data_path = tmp_path / "market.csv"
    market_data(periods=500).to_csv(data_path, index=False)
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(script.__file__).resolve()),
            "--data",
            str(data_path),
            "--fast-ema",
            "2",
            "--slow-ema",
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
    assert analysis["verdict"] == "INCONCLUSIVE"
