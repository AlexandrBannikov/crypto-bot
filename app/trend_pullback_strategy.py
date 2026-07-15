from collections.abc import Sequence

import pandas as pd

from app.engine import Candle
from app.indicators import adx
from app.trading_types import TradeAction
from app.trend_detector import (
    TrendDetector,
    TrendState,
)


class TrendPullbackStrategy:
    def __init__(
        self,
        pullback_ema_period: int = 20,
        trend_fast_period: int = 50,
        trend_slow_period: int = 200,
        trend_slope_lookback: int = 5,
        trend_min_separation_percent: float = 0.1,
        adx_period: int = 14,
        minimum_adx: float = 25.0,
        allow_short: bool = True,
    ) -> None:
        if pullback_ema_period <= 0:
            raise ValueError(
                "pullback_ema_period must be greater than zero"
            )

        if adx_period <= 0:
            raise ValueError(
                "adx_period must be greater than zero"
            )

        if minimum_adx < 0:
            raise ValueError(
                "minimum_adx must not be negative"
            )

        self.pullback_ema_period = pullback_ema_period
        self.adx_period = adx_period
        self.minimum_adx = minimum_adx
        self.allow_short = allow_short

        self._ema_multiplier = (
            2 / (pullback_ema_period + 1)
        )

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

        self._virtual_position: str | None = None

        self._adx_values: pd.Series | None = None
        self._cached_candles_id: int | None = None
        self._cached_candles_length = 0

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> TradeAction:
        if index < 0 or index >= len(candles):
            raise IndexError(
                "candle index is out of range"
            )

        self._ensure_adx_cache(candles)

        if index == 0 or index <= self._last_index:
            self._reset_runtime_state()

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
            return TradeAction.HOLD

        if (
            self._ema is None
            or self._previous_ema is None
            or self._previous_close is None
            or self._adx_values is None
        ):
            return TradeAction.HOLD

        current_adx = self._adx_values.iloc[index]

        adx_is_strong = (
            not pd.isna(current_adx)
            and float(current_adx) >= self.minimum_adx
        )

        current_close = candles[index].close

        crossed_above_ema = (
            self._previous_close <= self._previous_ema
            and current_close > self._ema
        )

        crossed_below_ema = (
            self._previous_close >= self._previous_ema
            and current_close < self._ema
        )

        # Уже открытую позицию закрываем при потере
        # соответствующего направления тренда.
        if (
            self._virtual_position == "long"
            and trend != TrendState.UPTREND
        ):
            self._virtual_position = None
            return TradeAction.CLOSE_LONG

        if (
            self._virtual_position == "short"
            and trend != TrendState.DOWNTREND
        ):
            self._virtual_position = None
            return TradeAction.CLOSE_SHORT

        # ADX фильтрует только новые входы.
        # Закрытию позиции он не препятствует.
        if not adx_is_strong:
            return TradeAction.HOLD

        if (
            self._virtual_position is None
            and trend == TrendState.UPTREND
            and crossed_above_ema
        ):
            self._virtual_position = "long"
            return TradeAction.OPEN_LONG

        if (
            self.allow_short
            and self._virtual_position is None
            and trend == TrendState.DOWNTREND
            and crossed_below_ema
        ):
            self._virtual_position = "short"
            return TradeAction.OPEN_SHORT

        return TradeAction.HOLD

    def _ensure_adx_cache(
        self,
        candles: Sequence[Candle],
    ) -> None:
        candles_id = id(candles)

        if (
            self._adx_values is not None
            and self._cached_candles_id == candles_id
            and self._cached_candles_length == len(candles)
        ):
            return

        frame = pd.DataFrame(
            {
                "high": [
                    candle.high
                    for candle in candles
                ],
                "low": [
                    candle.low
                    for candle in candles
                ],
                "close": [
                    candle.close
                    for candle in candles
                ],
            }
        )

        self._adx_values = adx(
            frame,
            period=self.adx_period,
        )

        self._cached_candles_id = candles_id
        self._cached_candles_length = len(candles)

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

    def _reset_runtime_state(self) -> None:
        self._ema = None
        self._previous_ema = None
        self._current_close = None
        self._previous_close = None
        self._last_index = -1
        self._virtual_position = None
