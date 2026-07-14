import pandas as pd
import pytest

from app.backtester import run_backtest
from app.models import TradeSide
from app.strategies import Signal


def make_data(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.date_range(
                start="2026-01-01",
                periods=len(prices),
                freq="h",
                tz="UTC",
            ),
            "close": prices,
        }
    )


def test_profitable_trade() -> None:
    data = make_data([100.0, 110.0, 120.0])
    signals = pd.Series([
        Signal.BUY,
        Signal.HOLD,
        Signal.SELL,
    ])

    result = run_backtest(
        data,
        signals,
        start_balance=1000.0,
        fee_rate=0.001,
    )

    assert result.final_balance > 1000.0
    assert result.completed_trades == 1
    assert result.winning_trades == 1
    assert result.operations == 2
    assert result.trades[0].side == TradeSide.BUY
    assert result.trades[1].side == TradeSide.SELL


def test_losing_trade() -> None:
    data = make_data([100.0, 90.0])
    signals = pd.Series([
        Signal.BUY,
        Signal.SELL,
    ])

    result = run_backtest(
        data,
        signals,
        start_balance=1000.0,
        fee_rate=0.001,
    )

    assert result.final_balance < 1000.0
    assert result.completed_trades == 1
    assert result.winning_trades == 0


def test_open_position_is_closed_at_end() -> None:
    data = make_data([100.0, 105.0, 110.0])
    signals = pd.Series([
        Signal.BUY,
        Signal.HOLD,
        Signal.HOLD,
    ])

    result = run_backtest(data, signals)

    assert result.completed_trades == 1
    assert result.operations == 2
    assert result.trades[-1].side == TradeSide.SELL


def test_signal_length_must_match_data() -> None:
    data = make_data([100.0, 101.0])

    with pytest.raises(ValueError):
        run_backtest(
            data,
            pd.Series([Signal.HOLD]),
        )


def test_missing_columns() -> None:
    data = pd.DataFrame({"price": [100.0]})

    with pytest.raises(ValueError):
        run_backtest(
            data,
            pd.Series([Signal.HOLD]),
        )


def test_invalid_balance() -> None:
    data = make_data([100.0])

    with pytest.raises(ValueError):
        run_backtest(
            data,
            pd.Series([Signal.HOLD]),
            start_balance=0,
        )

