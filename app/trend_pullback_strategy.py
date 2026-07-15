from collections.abc import Sequence

from app.engine import Candle
from app.strategies import Signal
from app.trend_detector import TrendDetector, TrendState


class TrendPullbackStrategy:
    def __init__(
        self,
        pullback_ema_period: int = 20,
        trend_fast_period: int = 50,
        trend_slow_period: int = 200,
        trend_slope_lookback: int = 5,
        trend_min_separation_percent: float = 0.1,
    ) -> None:
        if pullback_ema_period <= 0:
            raise ValueError(
                "pullback_ema_period must be greater than zero"
            )

        self.pullback_ema_period = pullback_ema_period
        self._ema_multiplier = 2 / (pullback_ema_period + 1)

        self._trend_detector = TrendDetector(
            fast_period=trend_fast_period,
            slow_period=trend_slow_period,
            slope_lookback=trend_slope_lookback,
            min_separation_percent=(
                trend_min_separation_percent
            ),
        )

        self._ema: float | None = None
        self._previous_ema: float | None = None
        self._current_close: float | None = None
        self._previous_close: float | None = None
        self._last_index = -1

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> Signal:
        if index < 0 or index >= len(candles):
            raise IndexError(
                "candle index is out of range"
            )

        if index == 0 or index <= self._last_index:
            self._reset()

        while self._last_index < index:
            next_index = self._last_index + 1
            close = candles[next_index].close

            self._update_ema(close)
            self._last_index = next_index

        trend = self._trend_detector.detect(
            candles,
            index,
        )

        if index < self.pullback_ema_period:
            return Signal.HOLD

        if (
            self._ema is None
            or self._previous_ema is None
            or self._previous_close is None
        ):
            return Signal.HOLD

        current_close = candles[index].close

        crossed_above_pullback_ema = (
            self._previous_close <= self._previous_ema
            and current_close > self._ema
        )

        if (
            trend == TrendState.UPTREND
            and crossed_above_pullback_ema
        ):
            return Signal.BUY

        if trend != TrendState.UPTREND:
            return Signal.SELL

        return Signal.HOLD

    def _update_ema(
        self,
        close: float,
    ) -> None:
        if close <= 0:
            raise ValueError(
                "candle close must be greater than zero"
            )

        old_ema = self._ema
        old_close = self._current_close

        if self._ema is None:
            self._ema = close
        else:
            self._ema = (
                close * self._ema_multiplier
                + self._ema
                * (1 - self._ema_multiplier)
            )

        self._previous_ema = old_ema
        self._previous_close = old_close
        self._current_close = close

    def _reset(self) -> None:
        self._ema = None
        self._previous_ema = None
        self._current_close = None
        self._previous_close = None
        self._last_index = -1
