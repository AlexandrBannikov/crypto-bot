from collections.abc import Sequence

from app.engine import Candle
from app.strategies import Signal
from app.strategy_diagnostics import (
    Decision,
    PositionState,
    ReasonCode,
    StrategyDecision,
)


class EMACrossStrategy:
    def __init__(
        self,
        short_period: int = 20,
        long_period: int = 50,
    ) -> None:
        if short_period <= 0:
            raise ValueError(
                "short_period must be greater than zero"
            )

        if long_period <= 0:
            raise ValueError(
                "long_period must be greater than zero"
            )

        if short_period >= long_period:
            raise ValueError(
                "short_period must be lower than long_period"
            )

        self.short_period = short_period
        self.long_period = long_period

        self._short_multiplier = 2 / (short_period + 1)
        self._long_multiplier = 2 / (long_period + 1)

        self._short_ema: float | None = None
        self._long_ema: float | None = None
        self._previous_short_ema: float | None = None
        self._previous_long_ema: float | None = None
        self._last_index = -1

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> Signal:
        if index < 0 or index >= len(candles):
            raise IndexError("candle index is out of range")

        if index == 0 or index <= self._last_index:
            self._reset()

        while self._last_index < index:
            next_index = self._last_index + 1
            close = candles[next_index].close

            self._update_ema(close)
            self._last_index = next_index

        if index < self.long_period:
            return Signal.HOLD

        if (
            self._previous_short_ema is None
            or self._previous_long_ema is None
            or self._short_ema is None
            or self._long_ema is None
        ):
            return Signal.HOLD

        crossed_up = (
            self._previous_short_ema <= self._previous_long_ema
            and self._short_ema > self._long_ema
        )

        crossed_down = (
            self._previous_short_ema >= self._previous_long_ema
            and self._short_ema < self._long_ema
        )

        if crossed_up:
            return Signal.BUY

        if crossed_down:
            return Signal.SELL

        return Signal.HOLD

    def evaluate_with_diagnostics(
        self,
        candles: Sequence[Candle],
        index: int,
        *,
        position_state: PositionState = PositionState.FLAT,
        price_confirmation_percent: float = 0.0,
        minimum_trend_spread_percent: float = 0.0,
    ) -> StrategyDecision:
        if price_confirmation_percent < 0:
            raise ValueError(
                "price_confirmation_percent must not be negative"
            )
        if minimum_trend_spread_percent < 0:
            raise ValueError(
                "minimum_trend_spread_percent must not be negative"
            )
        signal = self.generate_signal(candles, index)
        candle = candles[index]
        indicators = {
            "fast_ema": self._short_ema,
            "slow_ema": self._long_ema,
            "previous_fast_ema": self._previous_short_ema,
            "previous_slow_ema": self._previous_long_ema,
        }
        if (
            index < self.long_period
            or self._previous_short_ema is None
            or self._previous_long_ema is None
            or self._short_ema is None
            or self._long_ema is None
        ):
            return StrategyDecision(
                timestamp=candle.timestamp,
                close_price=float(candle.close),
                indicators=indicators,
                position_state=position_state,
                decision=Decision.HOLD,
                passed_conditions=(),
                failed_conditions=(ReasonCode.INSUFFICIENT_HISTORY,),
                primary_reason=ReasonCode.INSUFFICIENT_HISTORY,
            )

        spread_percent = (
            abs(self._short_ema - self._long_ema)
            / self._long_ema
            * 100
        )
        indicators["ema_spread_percent"] = spread_percent
        bullish = self._short_ema > self._long_ema
        bearish = self._short_ema < self._long_ema
        bullish_price = float(candle.close) >= self._long_ema * (
            1 + price_confirmation_percent / 100
        )
        bearish_price = float(candle.close) <= self._long_ema * (
            1 - price_confirmation_percent / 100
        )
        strong_enough = spread_percent >= minimum_trend_spread_percent

        if signal == Signal.BUY:
            failed: list[ReasonCode] = []
            if position_state != PositionState.FLAT:
                failed.append(ReasonCode.POSITION_ALREADY_OPEN)
            if not bullish_price:
                failed.append(ReasonCode.PRICE_TREND_NOT_CONFIRMED)
            if not strong_enough:
                failed.append(ReasonCode.TREND_STRENGTH_TOO_LOW)
            if failed:
                return StrategyDecision(
                    candle.timestamp,
                    float(candle.close),
                    indicators,
                    position_state,
                    Decision.HOLD,
                    (ReasonCode.BUY_SIGNAL,),
                    tuple(failed),
                    failed[0],
                )
            return StrategyDecision(
                candle.timestamp,
                float(candle.close),
                indicators,
                position_state,
                Decision.BUY,
                (ReasonCode.BUY_SIGNAL,),
                (),
                ReasonCode.BUY_SIGNAL,
            )

        if signal == Signal.SELL:
            if position_state == PositionState.FLAT:
                return StrategyDecision(
                    candle.timestamp,
                    float(candle.close),
                    indicators,
                    position_state,
                    Decision.HOLD,
                    (ReasonCode.SELL_SIGNAL,),
                    (ReasonCode.POSITION_ABSENT,),
                    ReasonCode.POSITION_ABSENT,
                )
            return StrategyDecision(
                candle.timestamp,
                float(candle.close),
                indicators,
                position_state,
                Decision.SELL,
                (ReasonCode.SELL_SIGNAL,),
                (),
                ReasonCode.SELL_SIGNAL,
            )

        failed = [
            (
                ReasonCode.FAST_EMA_NOT_ABOVE_SLOW
                if not bullish
                else ReasonCode.NO_BULLISH_EMA_CROSS
            )
        ]
        if position_state == PositionState.FLAT:
            if not bullish_price:
                failed.append(ReasonCode.PRICE_TREND_NOT_CONFIRMED)
            if not strong_enough:
                failed.append(ReasonCode.TREND_STRENGTH_TOO_LOW)
            primary = ReasonCode.NO_ENTRY_SIGNAL
        else:
            failed.append(
                ReasonCode.NO_BEARISH_EMA_CROSS
                if not bearish
                else ReasonCode.FAST_EMA_NOT_BELOW_SLOW
            )
            failed.append(ReasonCode.STOP_LOSS_NOT_REACHED)
            primary = ReasonCode.NO_EXIT_SIGNAL
        return StrategyDecision(
            candle.timestamp,
            float(candle.close),
            indicators,
            position_state,
            Decision.HOLD,
            (),
            tuple(failed),
            primary,
        )

    def _update_ema(self, close: float) -> None:
        if self._short_ema is None or self._long_ema is None:
            self._short_ema = close
            self._long_ema = close
            return

        self._previous_short_ema = self._short_ema
        self._previous_long_ema = self._long_ema

        self._short_ema = (
            close * self._short_multiplier
            + self._short_ema * (1 - self._short_multiplier)
        )

        self._long_ema = (
            close * self._long_multiplier
            + self._long_ema * (1 - self._long_multiplier)
        )

    def _reset(self) -> None:
        self._short_ema = None
        self._long_ema = None
        self._previous_short_ema = None
        self._previous_long_ema = None
        self._last_index = -1

    @staticmethod
    def _calculate_ema(
        values: Sequence[float],
        period: int,
    ) -> float:
        if not values:
            raise ValueError("values must not be empty")

        multiplier = 2 / (period + 1)
        ema = values[0]

        for value in values[1:]:
            ema = (
                value * multiplier
                + ema * (1 - multiplier)
            )

        return ema
