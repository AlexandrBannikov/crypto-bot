import json

import pytest

from app.ema_cross_strategy import EMACrossStrategy
from app.engine import Candle
from app.strategy_diagnostics import (
    Decision,
    DiagnosticJournal,
    DiagnosticRecord,
    PositionState,
    ReasonCode,
    format_diagnostic_summary,
    summarize_diagnostics,
)


def candles(*prices: float, step: int = 3600) -> list[Candle]:
    return [
        Candle(index * step, price, price, price, price, 1)
        for index, price in enumerate(prices)
    ]


def test_reason_codes_are_stable_strings() -> None:
    assert ReasonCode.INSUFFICIENT_HISTORY.value == "insufficient_history"
    assert ReasonCode.NO_BULLISH_EMA_CROSS.value == "no_bullish_ema_cross"
    assert ReasonCode.POSITION_ALREADY_OPEN.value == "position_already_open"
    assert ReasonCode.RISK_FILTER_BLOCKED.value == "risk_filter_blocked"


def test_buy_diagnostics_and_old_interface_are_compatible() -> None:
    values = candles(100, 99, 98, 97, 110)
    old_strategy = EMACrossStrategy(2, 3)
    diagnostic_strategy = EMACrossStrategy(2, 3)

    old_signal = old_strategy.generate_signal(values, 4)
    result = diagnostic_strategy.evaluate_with_diagnostics(values, 4)

    assert old_signal.value == 1
    assert result.decision is Decision.BUY
    assert result.primary_reason is ReasonCode.BUY_SIGNAL
    assert result.failed_conditions == ()
    assert result.indicators["fast_ema"] is not None


def test_sell_diagnostics_requires_a_position() -> None:
    result = EMACrossStrategy(2, 3).evaluate_with_diagnostics(
        candles(100, 101, 102, 103, 90),
        4,
        position_state=PositionState.LONG,
    )

    assert result.decision is Decision.SELL
    assert result.primary_reason is ReasonCode.SELL_SIGNAL


def test_hold_diagnostics_before_history() -> None:
    result = EMACrossStrategy(2, 3).evaluate_with_diagnostics(
        candles(100), 0
    )

    assert result.decision is Decision.HOLD
    assert result.failed_conditions == (
        ReasonCode.INSUFFICIENT_HISTORY,
    )


def test_multiple_failed_conditions_and_primary_reason() -> None:
    result = EMACrossStrategy(2, 3).evaluate_with_diagnostics(
        candles(100, 99, 98, 97, 110),
        4,
        position_state=PositionState.LONG,
        price_confirmation_percent=50,
        minimum_trend_spread_percent=50,
    )

    assert result.decision is Decision.HOLD
    assert result.failed_conditions == (
        ReasonCode.POSITION_ALREADY_OPEN,
        ReasonCode.PRICE_TREND_NOT_CONFIRMED,
        ReasonCode.TREND_STRENGTH_TOO_LOW,
    )
    assert result.primary_reason is ReasonCode.POSITION_ALREADY_OPEN


def record(
    timestamp: int,
    decision: str = "hold",
    reasons: tuple[str, ...] = ("no_bullish_ema_cross",),
) -> DiagnosticRecord:
    return DiagnosticRecord(
        timestamp=timestamp,
        symbol="ETHUSDT",
        timeframe="60",
        strategy_name="ema",
        strategy_parameters={"short_period": 20},
        position_state="flat",
        decision=decision,
        primary_reason=reasons[0] if reasons else f"{decision}_signal",
        reason_codes=reasons,
        passed_conditions=(),
        indicators={"fast_ema": 100.0},
        close_price=100,
        session_id="test",
    )


def test_journal_save_read_and_duplicate_protection(tmp_path) -> None:
    path = tmp_path / "diagnostics.jsonl"
    journal = DiagnosticJournal(path)

    assert journal.append(record(1)) is True
    assert journal.append(record(1)) is False
    assert DiagnosticJournal(path).read_all() == [record(1)]


def test_aggregated_statistics_percentages_and_signal_gaps() -> None:
    records = [
        record(0, reasons=("insufficient_history",)),
        record(3600),
        record(7200, "buy", ()),
        record(10800),
        record(14400),
        record(18000, "sell", ()),
    ]

    summary = summarize_diagnostics(records)

    assert summary.total_candles == 6
    assert summary.decisions == {"buy": 1, "sell": 1, "hold": 4}
    assert summary.position_openings == 1
    assert summary.position_closings == 1
    assert summary.insufficient_history == 1
    assert summary.reason_percentages["insufficient_history"] == pytest.approx(
        100 / 6
    )
    assert summary.max_candles_without_signal == 2
    assert summary.max_seconds_without_signal == 10800
    assert summary.average_seconds_between_signals == 10800
    assert "Processed candles: 6" in format_diagnostic_summary(summary)


def test_empty_report_can_be_serialized() -> None:
    payload = summarize_diagnostics([]).to_dict()

    assert payload["total_candles"] == 0
    json.dumps(payload)


def test_maximum_period_without_any_signal_spans_the_journal() -> None:
    summary = summarize_diagnostics(
        [record(0), record(3600), record(7200)]
    )

    assert summary.max_candles_without_signal == 3
    assert summary.max_seconds_without_signal == 7200
