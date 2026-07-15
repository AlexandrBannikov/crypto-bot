import pytest

from app.engine import Candle
from app.strategies import Signal
from app.trend_pullback_strategy import (
    TrendPullbackStrategy,
)


def make_candles(
    *prices: float,
) -> list[Candle]:
    return [
        Candle(
            timestamp=index,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1.0,
        )
        for index, price in enumerate(prices)
    ]


def make_strategy() -> TrendPullbackStrategy:
    return TrendPullbackStrategy(
        pullback_ema_period=2,
        trend_fast_period=2,
        trend_slow_period=4,
        trend_slope_lookback=1,
        trend_min_separation_percent=0,
    )


def test_returns_hold_during_warmup() -> None:
    strategy = make_strategy()

    candles = make_candles(
        100,
        101,
    )

    assert strategy.generate_signal(
        candles,
        0,
    ) == Signal.HOLD

    assert strategy.generate_signal(
        candles,
        1,
    ) == Signal.HOLD


def test_generates_buy_after_pullback_in_uptrend() -> None:
    strategy = make_strategy()

    candles = make_candles(
        100,
        102,
        104,
        106,
        108,
        104,
        109,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal == Signal.BUY


def test_does_not_buy_pullback_in_downtrend() -> None:
    strategy = make_strategy()

    candles = make_candles(
        110,
        108,
        106,
        104,
        102,
        105,
        101,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal != Signal.BUY


def test_generates_sell_when_uptrend_is_lost() -> None:
    strategy = make_strategy()

    candles = make_candles(
        100,
        102,
        104,
        106,
        108,
        100,
        95,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal == Signal.SELL


def test_returns_hold_without_pullback_cross() -> None:
    strategy = make_strategy()

    candles = make_candles(
        100,
        102,
        104,
        106,
        108,
        110,
        112,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal == Signal.HOLD


def test_strategy_can_be_reused() -> None:
    strategy = make_strategy()

    first = make_candles(
        100,
        102,
        104,
        106,
        108,
        104,
        109,
    )

    second = make_candles(
        110,
        108,
        106,
        104,
        102,
        100,
    )

    assert strategy.generate_signal(
        first,
        len(first) - 1,
    ) == Signal.BUY

    assert strategy.generate_signal(
        second,
        0,
    ) == Signal.HOLD

    assert strategy.generate_signal(
        second,
        len(second) - 1,
    ) == Signal.SELL


def test_rejects_invalid_pullback_period() -> None:
    with pytest.raises(ValueError):
        TrendPullbackStrategy(
            pullback_ema_period=0,
        )


def test_rejects_invalid_index() -> None:
    strategy = make_strategy()
    candles = make_candles(100, 101)

    with pytest.raises(IndexError):
        strategy.generate_signal(
            candles,
            index=10,
        )
