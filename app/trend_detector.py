from collections.abc import Sequence
from enum import Enum

from app.engine import Candle


class TrendState(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"


class TrendDetector:
    def __init__(
        self,
        fast_period: int = 50,
        slow_period: int = 200,
        slope_lookback: int = 5,
        min_separation_percent: float = 0.1,
    ) -> None:
        if fast_period <= 0:
            raise ValueError(
                "fast_period must be greater than zero"
            )

        if slow_period <= 0:
            raise ValueError(
                "slow_period must be greater than zero"
            )

        if fast_period >= slow_period:
            raise ValueError(
                "fast_period must be lower than slow_period"
            )

        if slope_lookback <= 0:
            raise ValueError(
                "slope_lookback must be greater than zero"
            )

        if min_separation_percent < 0:
            raise ValueError(
                "min_separation_percent must not be negative"
            )

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.slope_lookback = slope_lookback
        self.min_separation_percent = (
            min_separation_percent
        )

        self._fast_multiplier = (
            2 / (fast_period + 1)
        )
        self._slow_multiplier = (
            2 / (slow_period + 1)
        )

        self._fast_ema: float | None = None
        self._slow_ema: float | None = None

        self._fast_history: list[float] = []
        self._slow_history: list[float] = []

        self._last_index = -1

    def detect(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> TrendState:
        if index < 0 or index >= len(candles):
            raise IndexError(
                "candle index is out of range"
            )

        # Повторный проход или новый набор свечей.
        if index == 0 or index <= self._last_index:
            self._reset()

        while self._last_index < index:
            next_index = self._last_index + 1
            close = candles[next_index].close

            if close <= 0:
                raise ValueError(
                    "candle close must be greater than zero"
                )

            self._update(close)
            self._last_index = next_index

        minimum_index = max(
            self.slow_period - 1,
            self.slope_lookback,
        )

        if index < minimum_index:
            return TrendState.SIDEWAYS

        assert self._fast_ema is not None
        assert self._slow_ema is not None

        fast_reference = self._fast_history[
            -(self.slope_lookback + 1)
        ]

        slow_reference = self._slow_history[
            -(self.slope_lookback + 1)
        ]

        fast_is_rising = (
            self._fast_ema > fast_reference
        )
        slow_is_rising = (
            self._slow_ema > slow_reference
        )

        fast_is_falling = (
            self._fast_ema < fast_reference
        )
        slow_is_falling = (
            self._slow_ema < slow_reference
        )

        separation_percent = (
            abs(self._fast_ema - self._slow_ema)
            / self._slow_ema
            * 100
        )

        has_enough_separation = (
            separation_percent
            >= self.min_separation_percent
        )

        if (
            self._fast_ema > self._slow_ema
            and fast_is_rising
            and slow_is_rising
            and has_enough_separation
        ):
            return TrendState.UPTREND

        if (
            self._fast_ema < self._slow_ema
            and fast_is_falling
            and slow_is_falling
            and has_enough_separation
        ):
            return TrendState.DOWNTREND

        return TrendState.SIDEWAYS

    def _update(
        self,
        close: float,
    ) -> None:
        if (
            self._fast_ema is None
            or self._slow_ema is None
        ):
            self._fast_ema = close
            self._slow_ema = close
        else:
            self._fast_ema = (
                close * self._fast_multiplier
                + self._fast_ema
                * (1 - self._fast_multiplier)
            )

            self._slow_ema = (
                close * self._slow_multiplier
                + self._slow_ema
                * (1 - self._slow_multiplier)
            )

        self._fast_history.append(
            self._fast_ema
        )

        self._slow_history.append(
            self._slow_ema
        )

    def _reset(self) -> None:
        self._fast_ema = None
        self._slow_ema = None
        self._fast_history = []
        self._slow_history = []
        self._last_index = -1
