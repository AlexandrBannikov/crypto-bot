import pandas as pd
import pytest

from app.strategies import (
    Signal,
    ma_cross_signals,
    rsi_signals,
)


def make_data(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": prices})


def test_ma_cross_returns_valid_signals() -> None:
    data = make_data([
        10, 9, 8, 7, 8, 9, 10, 11,
        10, 9, 8, 7, 8, 9, 10, 11,
    ])

    signals = ma_cross_signals(
        data,
        fast_period=2,
        slow_period=4,
    )

    assert len(signals) == len(data)
    assert set(signals.unique()).issubset({
        Signal.SELL,
        Signal.HOLD,
        Signal.BUY,
    })
    assert Signal.BUY in signals.values
    assert Signal.SELL in signals.values


def test_ma_cross_invalid_periods() -> None:
    data = make_data([1, 2, 3, 4, 5])

    with pytest.raises(ValueError):
        ma_cross_signals(
            data,
            fast_period=5,
            slow_period=3,
        )


def test_rsi_returns_valid_signals() -> None:
    data = make_data(
        [100.0] * 20
        + [95, 90, 85, 80, 75]
        + [80, 85, 90, 95, 100, 105]
    )

    signals = rsi_signals(
        data,
        period=5,
        buy_level=30,
        sell_level=70,
    )

    assert len(signals) == len(data)
    assert set(signals.unique()).issubset({
        Signal.SELL,
        Signal.HOLD,
        Signal.BUY,
    })


def test_rsi_invalid_levels() -> None:
    data = make_data([100.0] * 30)

    with pytest.raises(ValueError):
        rsi_signals(
            data,
            buy_level=80,
            sell_level=20,
        )


def test_missing_close_column() -> None:
    data = pd.DataFrame({"price": [1, 2, 3]})

    with pytest.raises(ValueError):
        ma_cross_signals(
            data,
            fast_period=2,
            slow_period=3,
        )

