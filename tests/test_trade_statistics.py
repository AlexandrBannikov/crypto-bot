from dataclasses import replace
from decimal import Decimal

import pytest

from app.trade_statistics import calculate_trade_statistics
from tests.test_trade_journal import make_entry


D = Decimal


def entry(
    net_pnl: str,
    balance: str,
    *,
    record_id: str = "trade",
    gross_pnl: str | None = None,
    fee: str = "0",
    opened_at: str = "2026-07-27T10:00:00+00:00",
    closed_at: str = "2026-07-27T11:00:00+00:00",
):
    base = make_entry(record_id=record_id, net_pnl=D(net_pnl))
    return replace(
        base,
        gross_pnl=D(gross_pnl if gross_pnl is not None else net_pnl),
        total_fee=D(fee),
        virtual_balance_after=D(balance),
        opened_at=opened_at,
        closed_at=closed_at,
    )


def test_empty_statistics_have_consistent_zero_values() -> None:
    stats = calculate_trade_statistics([])

    assert stats.total_trades == 0
    assert stats.winning_trades == 0
    assert stats.losing_trades == 0
    assert stats.breakeven_trades == 0
    assert stats.win_rate == D("0")
    assert stats.gross_profit == D("0")
    assert stats.gross_loss == D("0")
    assert stats.net_pnl == D("0")
    assert stats.average_net_pnl == D("0")
    assert stats.average_win == D("0")
    assert stats.average_loss == D("0")
    assert stats.largest_win == D("0")
    assert stats.largest_loss == D("0")
    assert stats.profit_factor is None
    assert stats.expectancy == D("0")
    assert stats.max_drawdown_absolute == D("0")
    assert stats.max_drawdown_percent == D("0")
    assert stats.recovery_factor is None
    assert stats.average_holding_seconds == D("0")
    assert stats.starting_balance == D("0")
    assert stats.ending_balance == D("0")
    assert stats.equity_curve == ()


@pytest.mark.parametrize(
    ("net_pnl", "winning", "losing", "breakeven"),
    [
        ("10", 1, 0, 0),
        ("-10", 0, 1, 0),
        ("0", 0, 0, 1),
    ],
)
def test_classifies_single_trade(
    net_pnl: str,
    winning: int,
    losing: int,
    breakeven: int,
) -> None:
    stats = calculate_trade_statistics([entry(net_pnl, "100")])

    assert stats.winning_trades == winning
    assert stats.losing_trades == losing
    assert stats.breakeven_trades == breakeven


def test_calculates_mixed_pnl_fees_averages_and_factors() -> None:
    entries = [
        entry("10", "110", gross_pnl="12", fee="2"),
        entry("-4", "106", gross_pnl="-3", fee="1"),
        entry("0", "106", gross_pnl="1", fee="1"),
        entry("6", "112", gross_pnl="7", fee="1"),
    ]

    stats = calculate_trade_statistics(entries)

    assert stats.total_trades == 4
    assert stats.win_rate == D("50")
    assert stats.gross_profit == D("16")
    assert stats.gross_loss == D("4")
    assert stats.gross_pnl == D("17")
    assert stats.total_fees == D("5")
    assert stats.net_pnl == D("12")
    assert stats.average_net_pnl == D("3")
    assert stats.average_win == D("8")
    assert stats.average_loss == D("-4")
    assert stats.largest_win == D("10")
    assert stats.largest_loss == D("-4")
    assert stats.profit_factor == D("4")
    assert stats.expectancy == stats.average_net_pnl


def test_profit_factor_without_losses_is_undefined() -> None:
    stats = calculate_trade_statistics(
        [entry("2", "102"), entry("3", "105")]
    )

    assert stats.profit_factor is None
    assert stats.average_loss == D("0")


def test_no_winning_trades_has_zero_profit_factor() -> None:
    stats = calculate_trade_statistics(
        [entry("-2", "98"), entry("0", "98")]
    )

    assert stats.gross_profit == D("0")
    assert stats.average_win == D("0")
    assert stats.profit_factor == D("0")


def test_equity_drawdown_and_recovery_use_journal_order() -> None:
    entries = [
        entry("10", "110"),
        entry("-20", "90"),
        entry("30", "120"),
        entry("-12", "108"),
    ]

    stats = calculate_trade_statistics(entries)

    assert stats.starting_balance == D("100")
    assert stats.ending_balance == D("108")
    assert stats.equity_curve == (D("110"), D("90"), D("120"), D("108"))
    assert stats.max_drawdown_absolute == D("20")
    assert stats.max_drawdown_percent == D("20") / D("110") * D("100")
    assert stats.recovery_factor == D("8") / D("20")


def test_no_drawdown_has_undefined_recovery_factor() -> None:
    stats = calculate_trade_statistics(
        [entry("5", "105"), entry("4", "109")]
    )

    assert stats.max_drawdown_absolute == D("0")
    assert stats.max_drawdown_percent == D("0")
    assert stats.recovery_factor is None


def test_zero_peak_skips_percentage_until_positive_peak() -> None:
    stats = calculate_trade_statistics(
        [entry("-5", "-5"), entry("15", "10"), entry("-5", "5")]
    )

    assert stats.starting_balance == D("0")
    assert stats.max_drawdown_absolute == D("5")
    assert stats.max_drawdown_percent == D("50")


def test_streaks_and_breakeven_reset() -> None:
    entries = [
        entry("1", "101"),
        entry("2", "103"),
        entry("0", "103"),
        entry("3", "106"),
        entry("-1", "105"),
        entry("-2", "103"),
        entry("0", "103"),
        entry("-3", "100"),
    ]

    stats = calculate_trade_statistics(entries)

    assert stats.longest_win_streak == 2
    assert stats.longest_loss_streak == 2


def test_holding_time_statistics() -> None:
    entries = [
        entry(
            "1",
            "101",
            closed_at="2026-07-27T10:01:00+00:00",
        ),
        entry(
            "1",
            "102",
            closed_at="2026-07-27T10:03:00+00:00",
        ),
    ]

    stats = calculate_trade_statistics(entries)

    assert stats.average_holding_seconds == D("120")
    assert stats.min_holding_seconds == D("60")
    assert stats.max_holding_seconds == D("180")


@pytest.mark.parametrize("field_name", ["opened_at", "closed_at"])
def test_invalid_timestamp_has_clear_field_name(field_name: str) -> None:
    invalid = replace(entry("1", "101"), **{field_name: "not-a-time"})

    with pytest.raises(ValueError, match=field_name):
        calculate_trade_statistics([invalid])


def test_partial_closes_are_separate_records() -> None:
    stats = calculate_trade_statistics(
        [
            entry("2", "102", record_id="position:partial:1"),
            entry("3", "105", record_id="position:partial:2"),
        ]
    )

    assert stats.total_trades == 2
    assert stats.winning_trades == 2
    assert stats.net_pnl == D("5")
