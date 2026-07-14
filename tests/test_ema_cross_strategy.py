import pytest

from app.engine import Candle, Signal
from app.ema_cross_strategy import EMACrossStrategy


def make_candles(*prices: float) -> list[Candle]:
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


def test_strategy_returns_hold_before_enough_data():
    strategy = EMACrossStrategy(
        short_period=2,
        long_period=3,
    )

    candles = make_candles(100, 101, 102)

    assert strategy.generate_signal(
        candles,
        0,
    ) == Signal.HOLD

    assert strategy.generate_signal(
        candles,
        1,
    ) == Signal.HOLD

    assert strategy.generate_signal(
        candles,
        2,
    ) == Signal.HOLD


def test_strategy_generates_buy_signal_on_upward_cross():
    strategy = EMACrossStrategy(
        short_period=2,
        long_period=3,
    )

    candles = make_candles(
        100,
        99,
        98,
        97,
        110,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal == Signal.BUY


def test_strategy_generates_sell_signal_on_downward_cross():
    strategy = EMACrossStrategy(
        short_period=2,
        long_period=3,
    )

    candles = make_candles(
        100,
        101,
        102,
        103,
        90,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal == Signal.SELL


def test_strategy_returns_hold_without_cross():
    strategy = EMACrossStrategy(
        short_period=2,
        long_period=3,
    )

    candles = make_candles(
        100,
        101,
        102,
        103,
        104,
    )

    signal = strategy.generate_signal(
        candles,
        len(candles) - 1,
    )

    assert signal == Signal.HOLD


def test_calculate_ema_for_constant_prices():
    result = EMACrossStrategy._calculate_ema(
        [100, 100, 100, 100],
        period=3,
    )

    assert result == pytest.approx(100)


def test_calculate_ema_for_rising_prices():
    result = EMACrossStrategy._calculate_ema(
        [100, 110, 120],
        period=3,
    )

    assert result == pytest.approx(112.5)


@pytest.mark.parametrize(
    ("short_period", "long_period"),
    [
        (0, 20),
        (-1, 20),
        (10, 0),
        (10, -1),
        (20, 20),
        (30, 20),
    ],
)
def test_strategy_rejects_invalid_periods(
    short_period,
    long_period,
):
    with pytest.raises(ValueError):
        EMACrossStrategy(
            short_period=short_period,
            long_period=long_period,
        )


def test_calculate_ema_rejects_empty_values():
    with pytest.raises(
        ValueError,
        match="values must not be empty",
    ):
        EMACrossStrategy._calculate_ema(
            [],
            period=3,
        )

