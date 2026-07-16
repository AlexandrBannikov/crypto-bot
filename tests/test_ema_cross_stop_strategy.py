import pytest

from app.ema_cross_stop_strategy import EMACrossStopStrategy
from app.engine import Candle, TradeSignal
from app.trading_types import TradeAction


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


def test_generates_long_entry_with_stop_loss() -> None:
    strategy = EMACrossStopStrategy(
        short_period=2,
        long_period=3,
        stop_loss_percent=5,
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

    assert isinstance(signal, TradeSignal)
    assert signal.action == TradeAction.OPEN_LONG
    assert signal.stop_loss == pytest.approx(104.5)


def test_generates_close_long_signal() -> None:
    strategy = EMACrossStopStrategy(
        short_period=2,
        long_period=3,
        stop_loss_percent=5,
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

    assert isinstance(signal, TradeSignal)
    assert signal.action == TradeAction.CLOSE_LONG
    assert signal.stop_loss is None


@pytest.mark.parametrize(
    "stop_loss_percent",
    [0, -1, 100, 150],
)
def test_rejects_invalid_stop_loss_percent(
    stop_loss_percent: float,
) -> None:
    with pytest.raises(ValueError):
        EMACrossStopStrategy(
            short_period=20,
            long_period=50,
            stop_loss_percent=stop_loss_percent,
        )
