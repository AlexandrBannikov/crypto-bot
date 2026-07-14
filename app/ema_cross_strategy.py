from collections.abc import Sequence

from app.engine import Candle
from app.strategies import Signal


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

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> Signal:
        if index < self.long_period:
            return Signal.HOLD

        closes = [
            candle.close
            for candle in candles[: index + 1]
        ]

        short_ema = self._calculate_ema(
            closes,
            self.short_period,
        )
        long_ema = self._calculate_ema(
            closes,
            self.long_period,
        )

        previous_closes = closes[:-1]

        previous_short_ema = self._calculate_ema(
            previous_closes,
            self.short_period,
        )
        previous_long_ema = self._calculate_ema(
            previous_closes,
            self.long_period,
        )

        crossed_up = (
            previous_short_ema <= previous_long_ema
            and short_ema > long_ema
        )

        crossed_down = (
            previous_short_ema >= previous_long_ema
            and short_ema < long_ema
        )

        if crossed_up:
            return Signal.BUY

        if crossed_down:
            return Signal.SELL

        return Signal.HOLD

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

