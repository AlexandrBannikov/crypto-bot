from collections import deque
from collections.abc import Sequence
from app.engine import Candle
from app.trading_types import TradeAction


class EMATrendStrategy:
    def __init__(
        self,
        fast_period: int = 40,
        slow_period: int = 300,
        trend_period: int = 300,
        trend_slope_lookback: int = 24,
    ) -> None:
        if fast_period <= 0:
            raise ValueError(
                "fast_period must be greater than zero"
            )

        if slow_period <= 0:
            raise ValueError(
                "slow_period must be greater than zero"
            )

        if trend_period <= 0:
            raise ValueError(
                "trend_period must be greater than zero"
            )

        if trend_slope_lookback <= 0:
            raise ValueError(
                "trend_slope_lookback must be greater than zero"
            )

        if fast_period >= slow_period:
            raise ValueError(
                "fast_period must be lower than slow_period"
            )

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trend_period = trend_period
        self.trend_slope_lookback = trend_slope_lookback

        self._fast_multiplier = 2 / (fast_period + 1)
        self._slow_multiplier = 2 / (slow_period + 1)
        self._trend_multiplier = 2 / (trend_period + 1)

        self._fast_ema: float | None = None
        self._slow_ema: float | None = None
        self._trend_ema: float | None = None

        self._previous_fast_ema: float | None = None
        self._previous_slow_ema: float | None = None

        self._trend_history: deque[float] = deque(
            maxlen=trend_slope_lookback + 1
        )

        self._last_index = -1
        self._virtual_position_open = False

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> TradeAction:
        if index < 0 or index >= len(candles):
            raise IndexError(
                "candle index is out of range"
            )

        if index == 0 or index <= self._last_index:
            self._reset()

        while self._last_index < index:
            next_index = self._last_index + 1
            close = float(candles[next_index].close)

            if close <= 0:
                raise ValueError(
                    "candle close must be greater than zero"
                )

            self._update_emas(close)
            self._last_index = next_index

        warmup = max(
            self.slow_period,
            self.trend_period
            + self.trend_slope_lookback,
        )

        if index < warmup:
            return TradeAction.HOLD

        if (
            self._previous_fast_ema is None
            or self._previous_slow_ema is None
            or self._fast_ema is None
            or self._slow_ema is None
            or len(self._trend_history)
            < self.trend_slope_lookback + 1
        ):
            return TradeAction.HOLD

        crossed_up = (
            self._previous_fast_ema
            <= self._previous_slow_ema
            and self._fast_ema > self._slow_ema
        )

        crossed_down = (
            self._previous_fast_ema
            >= self._previous_slow_ema
            and self._fast_ema < self._slow_ema
        )

        trend_current = self._trend_history[-1]
        trend_past = self._trend_history[0]

        trend_is_rising = trend_current > trend_past

        if (
            self._virtual_position_open
            and crossed_down
        ):
            self._virtual_position_open = False
            return TradeAction.CLOSE_LONG

        if (
            not self._virtual_position_open
            and crossed_up
            and trend_is_rising
        ):
            self._virtual_position_open = True
            return TradeAction.OPEN_LONG

        return TradeAction.HOLD

    def _update_emas(
        self,
        close: float,
    ) -> None:
        if (
            self._fast_ema is None
            or self._slow_ema is None
            or self._trend_ema is None
        ):
            self._fast_ema = close
            self._slow_ema = close
            self._trend_ema = close
            self._trend_history.append(close)
            return

        self._previous_fast_ema = self._fast_ema
        self._previous_slow_ema = self._slow_ema

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

        self._trend_ema = (
            close * self._trend_multiplier
            + self._trend_ema
            * (1 - self._trend_multiplier)
        )

        self._trend_history.append(
            self._trend_ema
        )

    def _reset(self) -> None:
        self._fast_ema = None
        self._slow_ema = None
        self._trend_ema = None

        self._previous_fast_ema = None
        self._previous_slow_ema = None

        self._trend_history.clear()

        self._last_index = -1
        self._virtual_position_open = False
