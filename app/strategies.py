from enum import IntEnum

import pandas as pd

from app.indicators import rsi, sma


class Signal(IntEnum):
    SELL = -1
    HOLD = 0
    BUY = 1


def ma_cross_signals(
    data: pd.DataFrame,
    fast_period: int,
    slow_period: int,
) -> pd.Series:
    if fast_period <= 0 or slow_period <= 0:
        raise ValueError("Периоды средних должны быть больше нуля")

    if fast_period >= slow_period:
        raise ValueError(
            "Быстрый период должен быть меньше медленного"
        )

    if "close" not in data.columns:
        raise ValueError("Нет колонки close")

    fast = sma(data["close"], fast_period)
    slow = sma(data["close"], slow_period)

    signals = pd.Series(
        Signal.HOLD,
        index=data.index,
        dtype="int8",
    )

    buy_mask = (
        (fast.shift(1) <= slow.shift(1))
        & (fast > slow)
    )

    sell_mask = (
        (fast.shift(1) >= slow.shift(1))
        & (fast < slow)
    )

    signals.loc[buy_mask] = Signal.BUY
    signals.loc[sell_mask] = Signal.SELL

    return signals


def rsi_signals(
    data: pd.DataFrame,
    period: int = 14,
    buy_level: float = 30.0,
    sell_level: float = 70.0,
) -> pd.Series:
    if "close" not in data.columns:
        raise ValueError("Нет колонки close")

    if not 0 < buy_level < sell_level < 100:
        raise ValueError("Некорректные уровни RSI")

    values = rsi(data["close"], period)

    signals = pd.Series(
        Signal.HOLD,
        index=data.index,
        dtype="int8",
    )

    buy_mask = (
        (values.shift(1) >= buy_level)
        & (values < buy_level)
    )

    sell_mask = (
        (values.shift(1) <= sell_level)
        & (values > sell_level)
    )

    signals.loc[buy_mask] = Signal.BUY
    signals.loc[sell_mask] = Signal.SELL

    return signals

