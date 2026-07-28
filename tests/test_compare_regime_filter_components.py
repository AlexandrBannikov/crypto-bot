import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from app.candle import Candle
from app.market_regime import (
    MarketRegime,
    MarketTrend,
    MarketVolatility,
)
from app.regime_filter_research import (
    ResearchConfig,
    build_component_analysis,
    run_policy_walk_forward,
    run_walk_forward,
)
from app.regime_filtered_strategy import (
    EntryBlockPolicy,
    EntryBlockReason,
    RegimeFilteredStrategy,
)
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_filter import TradingFilter
from app.trading_types import TradeAction
from scripts import compare_regime_filter_components as script


def market_data(
    start: str = "2020-01-01",
    periods: int = 500,
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="D", tz="UTC")
    closes = [
        100 + index * 0.02 + ((index % 16) - 8) * 0.5
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


def small_config() -> ResearchConfig:
    return ResearchConfig(
        fast_ema=2,
        slow_ema=4,
        train_months=6,
        test_months=3,
        step_months=3,
        max_windows=1,
    )


class OneSignalStrategy:
    def __init__(self, signal) -> None:
        self.signal = signal

    def generate_signal(self, candles, index):
        return self.signal


def wrapped(signal, regime, policy):
    detector = Mock()
    detector.detect.return_value = regime
    return RegimeFilteredStrategy(
        OneSignalStrategy(signal),
        detector,
        TradingFilter(),
        block_policy=policy,
    )


def detected(
    trend: MarketTrend,
    volatility: MarketVolatility = MarketVolatility.NORMAL,
) -> MarketRegime:
    return MarketRegime(trend, volatility, 1.0)


def candle() -> list[Candle]:
    return [Candle(1, 100, 101, 99, 100, 1)]


def test_policy_is_immutable_and_validates_names() -> None:
    source = {EntryBlockReason.RANGE}
    policy = EntryBlockPolicy(source)
    source.add(EntryBlockReason.HIGH_VOLATILITY)

    assert policy.blocked_reasons == frozenset({EntryBlockReason.RANGE})
    with pytest.raises(FrozenInstanceError):
        policy.blocked_reasons = frozenset()
    with pytest.raises(ValueError, match="unknown block reason"):
        script.policy("not-a-reason")


def test_range_only_blocks_range() -> None:
    strategy = wrapped(
        Signal.BUY,
        detected(MarketTrend.RANGE),
        script.VARIANT_POLICIES["range_only"],
    )

    assert strategy.generate_signal(candle(), 0) is TradeAction.HOLD
    assert strategy.statistics.blocked_by_reason["range"] == 1


def test_range_only_does_not_block_high_volatility() -> None:
    strategy = wrapped(
        Signal.BUY,
        detected(MarketTrend.TREND_UP, MarketVolatility.HIGH),
        script.VARIANT_POLICIES["range_only"],
    )

    assert strategy.generate_signal(candle(), 0) is Signal.BUY
    assert strategy.statistics.blocked_entries == 0


def test_high_volatility_only_does_not_block_range() -> None:
    strategy = wrapped(
        Signal.BUY,
        detected(MarketTrend.RANGE, MarketVolatility.HIGH),
        script.VARIANT_POLICIES["high_volatility_only"],
    )

    assert strategy.generate_signal(candle(), 0) is Signal.BUY
    assert strategy.statistics.blocked_entries == 0


def test_primary_reason_priority_controls_policy() -> None:
    strategy = wrapped(
        Signal.BUY,
        detected(MarketTrend.RANGE, MarketVolatility.HIGH),
        script.VARIANT_POLICIES["range_only"],
    )

    strategy.generate_signal(candle(), 0)

    assert strategy.statistics.blocked_by_reason["range"] == 1
    assert strategy.statistics.blocked_by_reason["high_volatility"] == 0


def test_full_policy_matches_default_filter() -> None:
    regime = detected(MarketTrend.RANGE)
    explicit = wrapped(
        Signal.BUY,
        regime,
        EntryBlockPolicy.full(),
    )
    default = wrapped(Signal.BUY, regime, None)

    assert explicit.generate_signal(candle(), 0) == (
        default.generate_signal(candle(), 0)
    )
    assert explicit.statistics == default.statistics


def test_empty_policy_matches_detector_only() -> None:
    regime = detected(MarketTrend.RANGE)
    empty = wrapped(Signal.BUY, regime, EntryBlockPolicy.empty())
    detector_only = RegimeFilteredStrategy(
        OneSignalStrategy(Signal.BUY),
        Mock(detect=Mock(return_value=regime)),
        TradingFilter(),
        apply_filter=False,
    )

    assert empty.generate_signal(candle(), 0) == (
        detector_only.generate_signal(candle(), 0)
    )
    assert empty.statistics == detector_only.statistics


@pytest.mark.parametrize(
    "signal",
    [Signal.HOLD, TradeAction.CLOSE_LONG, TradeAction.CLOSE_SHORT],
)
def test_non_entries_are_never_blocked(signal) -> None:
    strategy = wrapped(
        signal,
        detected(MarketTrend.RANGE),
        EntryBlockPolicy.full(),
    )

    assert strategy.generate_signal(candle(), 0) is signal
    assert strategy.statistics.blocked_entries == 0


def test_trade_signal_is_not_mutated() -> None:
    signal = TradeSignal(
        action=TradeAction.OPEN_LONG,
        stop_loss=95,
        trailing_stop_percent=0.05,
        break_even_r_multiple=1.5,
    )
    strategy = wrapped(
        signal,
        detected(MarketTrend.TREND_UP),
        EntryBlockPolicy.full(),
    )

    returned = strategy.generate_signal(candle(), 0)

    assert returned is signal
    assert returned == signal


@pytest.fixture
def component_results():
    return run_policy_walk_forward(
        market_data(),
        small_config(),
        script.VARIANT_POLICIES,
    )


def test_all_variants_have_independent_results_and_invariants(
    component_results,
) -> None:
    assert {item.variant for item in component_results} == set(
        script.VARIANT_POLICIES
    )
    baseline = next(
        item for item in component_results if item.variant == "baseline"
    )
    detector_only = next(
        item
        for item in component_results
        if item.variant == "detector_only"
    )
    assert detector_only.final_balance == baseline.final_balance
    assert detector_only.return_percent == baseline.return_percent
    assert detector_only.blocked_entries == baseline.blocked_entries == 0
    for item in component_results:
        reasons = (
            item.blocked_range
            + item.blocked_downtrend
            + item.blocked_high_volatility
            + item.blocked_low_confidence
            + item.blocked_unknown
        )
        assert reasons == item.blocked_entries
        assert (
            item.allowed_entries + item.blocked_entries
            == baseline.allowed_entries
        )
        assert item.initial_balance == 1000


def test_component_reasons_match_each_policy(component_results) -> None:
    for item in component_results:
        configured = script.VARIANT_POLICIES[item.variant]
        if configured is None:
            assert item.blocked_entries == 0
            continue
        nonzero_reasons = {
            reason
            for reason, count in {
                EntryBlockReason.RANGE: item.blocked_range,
                EntryBlockReason.DOWNTREND: item.blocked_downtrend,
                EntryBlockReason.HIGH_VOLATILITY: (
                    item.blocked_high_volatility
                ),
                EntryBlockReason.LOW_CONFIDENCE: (
                    item.blocked_low_confidence
                ),
                EntryBlockReason.UNKNOWN_REGIME: item.blocked_unknown,
            }.items()
            if count
        }
        assert nonzero_reasons <= configured.blocked_reasons


def test_no_lookahead() -> None:
    original = market_data()
    changed = original.copy()
    first_window_end = pd.Timestamp("2020-10-01", tz="UTC")
    changed.loc[
        changed.datetime >= first_window_end,
        ["open", "high", "low", "close"],
    ] *= 2

    original_results = run_policy_walk_forward(
        original,
        small_config(),
        script.VARIANT_POLICIES,
    )
    changed_results = run_policy_walk_forward(
        changed,
        small_config(),
        script.VARIANT_POLICIES,
    )

    assert original_results == changed_results


def test_full_filtered_reproduces_committed_five_windows() -> None:
    data = script.load_market_data(script.DEFAULT_DATA_PATH)
    results = run_walk_forward(data, ResearchConfig())
    filtered = [
        item.return_percent
        for item in results
        if item.variant == "filtered"
    ]

    assert filtered == pytest.approx(
        [15.70, 25.04, 4.84, -9.33, -4.42],
        abs=0.01,
    )


def test_component_aggregates_and_compounding(component_results) -> None:
    analysis = build_component_analysis(
        component_results,
        tuple(script.VARIANT_POLICIES),
        1000,
    )

    assert set(analysis["summary"]) == set(script.VARIANT_POLICIES)
    assert set(analysis["comparison_to_baseline"]) == (
        set(script.VARIANT_POLICIES) - {"baseline"}
    )
    for summary in analysis["summary"].values():
        assert summary["windows"] == 1
        assert sum(summary["blocked_by_reason"].values()) == (
            summary["total_blocked_entries"]
        )
        assert summary["compounded_balance"] == pytest.approx(
            1000 * (1 + summary["compounded_return_percent"] / 100)
        )


def test_mixed_compounding_is_multiplicative(component_results) -> None:
    template = component_results[0]
    rows = [
        replace(template, window_number=1, return_percent=10),
        replace(template, window_number=2, return_percent=-20),
    ]

    analysis = build_component_analysis(rows, ("baseline",), 1000)

    assert analysis["summary"]["baseline"][
        "compounded_balance"
    ] == pytest.approx(880)
    assert analysis["summary"]["baseline"][
        "compounded_return_percent"
    ] == pytest.approx(-12)


def test_json_csv_are_atomic_and_deterministic(tmp_path) -> None:
    data_path = tmp_path / "market.csv"
    market_data().to_csv(data_path, index=False)
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
        "--output-json",
        str(json_path),
        "--output-csv",
        str(csv_path),
    ]

    assert script.main(arguments) == 0
    first_json = json_path.read_bytes()
    first_csv = csv_path.read_bytes()
    assert script.main(arguments) == 0

    assert json.loads(json_path.read_text())["window_results"]
    assert json_path.read_bytes() == first_json
    assert csv_path.read_bytes() == first_csv
    assert not list(json_path.parent.glob("*.tmp"))


def test_cli_works_from_any_cwd_without_default_reports(tmp_path) -> None:
    data_path = tmp_path / "market.csv"
    market_data().to_csv(data_path, index=False)
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
            "--step-months",
            "3",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Component aggregates" in completed.stdout
    assert {path.name for path in tmp_path.iterdir()} == {"market.csv"}


@pytest.mark.parametrize(
    "arguments",
    [
        ["--train-months", "0"],
        ["--fast-period", "50", "--slow-period", "20"],
        ["--fee-rate", "1"],
        ["--initial-balance", "0"],
    ],
)
def test_invalid_arguments(arguments, capsys) -> None:
    with pytest.raises(SystemExit) as captured:
        script.main(arguments)

    assert captured.value.code == 2
    assert capsys.readouterr().err


def test_empty_and_short_datasets_are_rejected() -> None:
    empty = market_data(periods=0)
    with pytest.raises(ValueError, match="empty"):
        run_policy_walk_forward(
            empty,
            small_config(),
            script.VARIANT_POLICIES,
        )
    with pytest.raises(ValueError, match="not enough data"):
        run_policy_walk_forward(
            market_data(periods=30),
            small_config(),
            script.VARIANT_POLICIES,
        )
