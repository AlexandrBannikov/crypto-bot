import pytest

from app.ema_trend_strategy import EMATrendStrategy
from app.engine import Candle
from app.trading_types import TradeAction


def make_candles(
    prices: list[float],
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


def test_returns_hold_during_warmup() -> None:
    strategy = EMATrendStrategy(
        fast_period=2,
        slow_period=4,
        trend_period=4,
        trend_slope_lookback=2,
    )

    candles = make_candles(
        [100, 101, 102, 103, 104]
    )

    assert strategy.generate_signal(
        candles,
        4,
    ) == TradeAction.HOLD


def test_rejects_invalid_periods() -> None:
    with pytest.raises(ValueError):
        EMATrendStrategy(
            fast_period=0,
            slow_period=10,
        )

    with pytest.raises(ValueError):
        EMATrendStrategy(
            fast_period=10,
            slow_period=10,
        )

    with pytest.raises(ValueError):
        EMATrendStrategy(
            fast_period=10,
            slow_period=20,
            trend_slope_lookback=0,
        )


def test_rejects_invalid_index() -> None:
    strategy = EMATrendStrategy(
        fast_period=2,
        slow_period=4,
    )

    candles = make_candles(
        [100, 101, 102]
    )

    with pytest.raises(IndexError):
        strategy.generate_signal(
            candles,
            5,
        )


