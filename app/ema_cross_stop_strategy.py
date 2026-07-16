from collections.abc import Sequence

from app.ema_cross_strategy import EMACrossStrategy
from app.engine import Candle, TradeSignal
from app.strategies import Signal
from app.trading_types import TradeAction


class EMACrossStopStrategy:
    def __init__(
        self,
        short_period: int = 40,
        long_period: int = 300,
        stop_loss_percent: float = 5.0,
    ) -> None:
        if stop_loss_percent <= 0:
            raise ValueError(
                "stop_loss_percent must be greater than zero"
            )

        if stop_loss_percent >= 100:
            raise ValueError(
                "stop_loss_percent must be lower than 100"
            )

        self.stop_loss_percent = stop_loss_percent

        self._strategy = EMACrossStrategy(
            short_period=short_period,
            long_period=long_period,
        )

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> TradeSignal | TradeAction:
        signal = self._strategy.generate_signal(
            candles,
            index,
        )

        if signal == Signal.BUY:
            close_price = float(candles[index].close)

            stop_loss = close_price * (
                1 - self.stop_loss_percent / 100
            )

            return TradeSignal(
                action=TradeAction.OPEN_LONG,
                stop_loss=stop_loss,
            )

        if signal == Signal.SELL:
            return TradeSignal(
                action=TradeAction.CLOSE_LONG,
            )

        return TradeAction.HOLD
