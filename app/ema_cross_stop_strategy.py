from collections.abc import Sequence

from app.ema_cross_strategy import EMACrossStrategy
from app.engine import Candle, TradeSignal
from app.strategies import Signal
from app.trading_types import TradeAction
from app.strategy_diagnostics import PositionState, StrategyDecision


class EMACrossStopStrategy:
    def __init__(
        self,
        short_period: int = 40,
        long_period: int = 300,
        stop_loss_percent: float = 5.0,
        price_confirmation_percent: float = 0.0,
        minimum_trend_spread_percent: float = 0.0,
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
        if price_confirmation_percent < 0:
            raise ValueError(
                "price_confirmation_percent must not be negative"
            )
        if minimum_trend_spread_percent < 0:
            raise ValueError(
                "minimum_trend_spread_percent must not be negative"
            )
        self.price_confirmation_percent = price_confirmation_percent
        self.minimum_trend_spread_percent = (
            minimum_trend_spread_percent
        )

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
            fast = self._strategy._short_ema
            slow = self._strategy._long_ema
            if fast is not None and slow is not None:
                close = float(candles[index].close)
                price_confirmed = close >= slow * (
                    1 + self.price_confirmation_percent / 100
                )
                spread = abs(fast - slow) / slow * 100
                if (
                    not price_confirmed
                    or spread < self.minimum_trend_spread_percent
                ):
                    return TradeAction.HOLD

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

    @property
    def strategy_parameters(self) -> dict[str, float | int]:
        return {
            "short_period": self._strategy.short_period,
            "long_period": self._strategy.long_period,
            "stop_loss_percent": self.stop_loss_percent,
            "price_confirmation_percent": (
                self.price_confirmation_percent
            ),
            "minimum_trend_spread_percent": (
                self.minimum_trend_spread_percent
            ),
        }

    def evaluate_with_diagnostics(
        self,
        candles: Sequence[Candle],
        index: int,
        *,
        position_state: PositionState = PositionState.FLAT,
        price_confirmation_percent: float | None = None,
        minimum_trend_spread_percent: float | None = None,
    ) -> StrategyDecision:
        return self._strategy.evaluate_with_diagnostics(
            candles,
            index,
            position_state=position_state,
            price_confirmation_percent=(
                self.price_confirmation_percent
                if price_confirmation_percent is None
                else price_confirmation_percent
            ),
            minimum_trend_spread_percent=(
                self.minimum_trend_spread_percent
                if minimum_trend_spread_percent is None
                else minimum_trend_spread_percent
            ),
        )
