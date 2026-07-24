import pytest

from app.engine import Trade
from app.paper_statistics import calculate_statistics
from app.trading_types import PositionSide


def make_trade(profit: float) -> Trade:
    return Trade(
        entry_timestamp=1,
        exit_timestamp=2,
        entry_price=100.0,
        exit_price=100.0,
        quantity=1.0,
        entry_fee=0.0,
        exit_fee=0.0,
        profit=profit,
        profit_percent=profit,
        side=PositionSide.LONG,
    )


def test_returns_empty_statistics() -> None:
    stats = calculate_statistics(
        start_balance=1000.0,
        trades=[],
    )

    assert stats.start_balance == pytest.approx(1000.0)
    assert stats.current_balance == pytest.approx(1000.0)
    assert stats.net_profit == pytest.approx(0.0)
    assert stats.return_percent == pytest.approx(0.0)
    assert stats.total_trades == 0
    assert stats.winning_trades == 0
    assert stats.losing_trades == 0
    assert stats.win_rate_percent == pytest.approx(0.0)


def test_calculates_basic_statistics() -> None:
    trades = [
        make_trade(100.0),
        make_trade(-40.0),
        make_trade(20.0),
        make_trade(0.0),
    ]

    stats = calculate_statistics(
        start_balance=1000.0,
        trades=trades,
    )

    assert stats.current_balance == pytest.approx(1080.0)
    assert stats.net_profit == pytest.approx(80.0)
    assert stats.return_percent == pytest.approx(8.0)
    assert stats.total_trades == 4
    assert stats.winning_trades == 2
    assert stats.losing_trades == 1
    assert stats.win_rate_percent == pytest.approx(50.0)


def test_calculates_profit_factor_and_averages() -> None:
    trades = [
        make_trade(100.0),
        make_trade(50.0),
        make_trade(-30.0),
        make_trade(-20.0),
        make_trade(0.0),
    ]

    stats = calculate_statistics(
        start_balance=1000.0,
        trades=trades,
    )

    assert stats.gross_profit == pytest.approx(150.0)
    assert stats.gross_loss == pytest.approx(-50.0)
    assert stats.profit_factor == pytest.approx(3.0)
    assert stats.average_win == pytest.approx(75.0)
    assert stats.average_loss == pytest.approx(-25.0)


def test_profit_factor_is_zero_without_losses() -> None:
    stats = calculate_statistics(
        start_balance=1000.0,
        trades=[
            make_trade(100.0),
            make_trade(50.0),
        ],
    )

    assert stats.gross_profit == pytest.approx(150.0)
    assert stats.gross_loss == pytest.approx(0.0)
    assert stats.profit_factor == pytest.approx(0.0)
    assert stats.average_win == pytest.approx(75.0)
    assert stats.average_loss == pytest.approx(0.0)
