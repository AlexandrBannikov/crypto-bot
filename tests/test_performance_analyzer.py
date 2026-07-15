import pytest

from app.engine import Trade
from app.performance_analyzer import PerformanceAnalyzer
from app.trading_types import PositionSide


def make_trade(
    *,
    profit: float,
    profit_percent: float,
    side: PositionSide = PositionSide.LONG,
) -> Trade:
    return Trade(
        entry_timestamp=1,
        exit_timestamp=2,
        entry_price=100.0,
        exit_price=100.0,
        quantity=1.0,
        entry_fee=0.0,
        exit_fee=0.0,
        profit=profit,
        profit_percent=profit_percent,
        side=side,
    )


def test_returns_empty_analysis() -> None:
    result = PerformanceAnalyzer().analyze([])

    assert result.trades == 0
    assert result.total_profit == pytest.approx(0)
    assert result.maximum_winning_streak == 0
    assert result.maximum_losing_streak == 0
    assert result.long.trades == 0
    assert result.short.trades == 0


def test_calculates_general_statistics() -> None:
    trades = [
        make_trade(
            profit=10,
            profit_percent=10,
        ),
        make_trade(
            profit=-5,
            profit_percent=-5,
        ),
        make_trade(
            profit=20,
            profit_percent=20,
        ),
        make_trade(
            profit=0,
            profit_percent=0,
        ),
    ]

    result = PerformanceAnalyzer().analyze(trades)

    assert result.trades == 4
    assert result.winning_trades == 2
    assert result.losing_trades == 1
    assert result.break_even_trades == 1

    assert result.total_profit == pytest.approx(25)
    assert result.average_profit == pytest.approx(6.25)
    assert result.median_profit == pytest.approx(5)

    assert result.average_profit_percent == pytest.approx(6.25)
    assert result.median_profit_percent == pytest.approx(5)

    assert result.best_trade_percent == pytest.approx(20)
    assert result.worst_trade_percent == pytest.approx(-5)


def test_calculates_winning_and_losing_streaks() -> None:
    trades = [
        make_trade(profit=1, profit_percent=1),
        make_trade(profit=2, profit_percent=2),
        make_trade(profit=-1, profit_percent=-1),
        make_trade(profit=-2, profit_percent=-2),
        make_trade(profit=-3, profit_percent=-3),
        make_trade(profit=4, profit_percent=4),
    ]

    result = PerformanceAnalyzer().analyze(trades)

    assert result.maximum_winning_streak == 2
    assert result.maximum_losing_streak == 3


def test_calculates_long_and_short_statistics() -> None:
    trades = [
        make_trade(
            profit=10,
            profit_percent=10,
            side=PositionSide.LONG,
        ),
        make_trade(
            profit=-5,
            profit_percent=-5,
            side=PositionSide.LONG,
        ),
        make_trade(
            profit=8,
            profit_percent=8,
            side=PositionSide.SHORT,
        ),
    ]

    result = PerformanceAnalyzer().analyze(trades)

    assert result.long.trades == 2
    assert result.long.winning_trades == 1
    assert result.long.losing_trades == 1
    assert result.long.total_profit == pytest.approx(5)
    assert result.long.win_rate_percent == pytest.approx(50)

    assert result.short.trades == 1
    assert result.short.winning_trades == 1
    assert result.short.losing_trades == 0
    assert result.short.total_profit == pytest.approx(8)
    assert result.short.win_rate_percent == pytest.approx(100)


def test_break_even_trade_breaks_streak() -> None:
    trades = [
        make_trade(profit=1, profit_percent=1),
        make_trade(profit=0, profit_percent=0),
        make_trade(profit=2, profit_percent=2),
    ]

    result = PerformanceAnalyzer().analyze(trades)

    assert result.maximum_winning_streak == 1
