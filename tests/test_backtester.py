import pandas as pd
import pytest

from app.backtester import run_backtest
from app.models import TradeSide
from app.strategies import Signal


def make_data(
    opens: list[float],
    closes: list[float] | None = None,
) -> pd.DataFrame:
    if closes is None:
        closes = opens

    return pd.DataFrame(
        {
            "datetime": pd.date_range(
                start="2026-01-01",
                periods=len(opens),
                freq="h",
                tz="UTC",
            ),
            "open": opens,
            "close": closes,
        }
    )


def test_profitable_trade() -> None:
    data = make_data(
        opens=[100.0, 100.0, 120.0, 130.0],
        closes=[100.0, 110.0, 125.0, 130.0],
    )

    signals = pd.Series([
        Signal.BUY,
        Signal.HOLD,
        Signal.SELL,
        Signal.HOLD,
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
    data = make_data(
        opens=[100.0, 100.0, 90.0],
        closes=[100.0, 95.0, 90.0],
    )

    signals = pd.Series([
        Signal.BUY,
        Signal.SELL,
        Signal.HOLD,
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


def test_signal_executes_on_next_candle_open() -> None:
    data = make_data(
        opens=[100.0, 105.0, 110.0],
        closes=[100.0, 108.0, 112.0],
    )

    signals = pd.Series([
        Signal.BUY,
        Signal.SELL,
        Signal.HOLD,
    ])

    result = run_backtest(
        data,
        signals,
        start_balance=1000.0,
        fee_rate=0.0,
    )

    assert result.trades[0].price == pytest.approx(105.0)
    assert result.trades[1].price == pytest.approx(110.0)


def test_open_position_is_closed_at_end() -> None:
    data = make_data(
        opens=[100.0, 105.0, 110.0],
        closes=[100.0, 108.0, 115.0],
    )

    signals = pd.Series([
        Signal.BUY,
        Signal.HOLD,
        Signal.HOLD,
    ])

    result = run_backtest(data, signals)

    assert result.completed_trades == 1
    assert result.operations == 2
    assert result.trades[-1].side == TradeSide.SELL
    assert result.trades[-1].price == pytest.approx(115.0)


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


def test_unknown_signal() -> None:
    data = make_data([100.0, 101.0])

    with pytest.raises(ValueError):
        run_backtest(
            data,
            pd.Series([99, Signal.HOLD]),
        )

