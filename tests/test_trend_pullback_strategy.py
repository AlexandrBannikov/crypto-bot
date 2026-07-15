import pytest

from app.engine import Candle
from app.trading_types import TradeAction
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
        adx_period=2,
        minimum_adx=0,
    )


def test_returns_hold_during_warmup() -> None:
    strategy = make_strategy()
    candles = make_candles(100, 101)

    assert strategy.generate_signal(
        candles,
        0,
    ) == TradeAction.HOLD

    assert strategy.generate_signal(
        candles,
        1,
    ) == TradeAction.HOLD


def test_opens_long_after_pullback_in_uptrend() -> None:
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

    assert signal == TradeAction.OPEN_LONG


def test_opens_short_after_rebound_in_downtrend() -> None:
    strategy = make_strategy()

    candles = make_candles(
        110,
        108,
        106,
        104,
        102,
        106,
        101,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal == TradeAction.OPEN_SHORT


def test_does_not_open_long_in_downtrend() -> None:
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

    assert signal != TradeAction.OPEN_LONG


def test_does_not_open_short_in_uptrend() -> None:
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

    assert signal != TradeAction.OPEN_SHORT


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

    assert signal == TradeAction.HOLD


def test_strategy_can_be_reused() -> None:
    strategy = make_strategy()

    rising = make_candles(
        100,
        102,
        104,
        106,
        108,
        104,
        109,
    )

    falling = make_candles(
        110,
        108,
        106,
        104,
        102,
        106,
        101,
    )

    assert strategy.generate_signal(
        rising,
        len(rising) - 1,
    ) == TradeAction.OPEN_LONG

    assert strategy.generate_signal(
        falling,
        0,
    ) == TradeAction.HOLD

    assert strategy.generate_signal(
        falling,
        len(falling) - 1,
    ) == TradeAction.OPEN_SHORT


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


def test_adx_filter_blocks_entry_when_threshold_is_too_high() -> None:
    strategy = TrendPullbackStrategy(
        pullback_ema_period=2,
        trend_fast_period=2,
        trend_slow_period=4,
        trend_slope_lookback=1,
        trend_min_separation_percent=0,
        adx_period=2,
        minimum_adx=101,
    )

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

    assert signal == TradeAction.HOLD


@pytest.mark.parametrize(
    ("adx_period", "minimum_adx"),
    [
        (0, 25),
        (-1, 25),
        (14, -1),
    ],
)
def test_rejects_invalid_adx_configuration(
    adx_period,
    minimum_adx,
) -> None:
    with pytest.raises(ValueError):
        TrendPullbackStrategy(
            adx_period=adx_period,
            minimum_adx=minimum_adx,
        )


def test_short_entry_can_be_disabled() -> None:
    strategy = TrendPullbackStrategy(
        pullback_ema_period=2,
        trend_fast_period=2,
        trend_slow_period=4,
        trend_slope_lookback=1,
        trend_min_separation_percent=0,
        adx_period=2,
        minimum_adx=0,
        allow_short=False,
    )

    candles = make_candles(
        110,
        108,
        106,
        104,
        102,
        106,
        101,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal == TradeAction.HOLD
