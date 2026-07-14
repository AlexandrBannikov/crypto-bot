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

