from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from app.candle import Candle
from app.indicators import ema


class MarketTrend(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


class MarketVolatility(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


@dataclass(frozen=True, slots=True)
class MarketRegime:
    trend: MarketTrend
    volatility: MarketVolatility
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


class MarketRegimeDetector:
    def __init__(
        self,
        fast_ema_period: int = 20,
        slow_ema_period: int = 50,
    ) -> None:
        if fast_ema_period <= 0:
            raise ValueError("fast_ema_period must be greater than zero")

        if slow_ema_period <= 0:
            raise ValueError("slow_ema_period must be greater than zero")

        if fast_ema_period >= slow_ema_period:
            raise ValueError(
                "fast_ema_period must be less than slow_ema_period"
            )

        self.fast_ema_period = fast_ema_period
        self.slow_ema_period = slow_ema_period

    def detect(self, candles: Sequence[Candle]) -> MarketRegime:
        if len(candles) < 2:
            return MarketRegime(
                trend=MarketTrend.UNKNOWN,
                volatility=MarketVolatility.NORMAL,
                confidence=0.0,
            )

        if len(candles) >= self.slow_ema_period:
            trend = self._detect_ema_trend(candles)
        else:
            trend = self._detect_simple_trend(candles)

        return MarketRegime(
            trend=trend,
            volatility=MarketVolatility.NORMAL,
            confidence=1.0,
        )

    def _detect_ema_trend(
        self,
        candles: Sequence[Candle],
    ) -> MarketTrend:
        close_prices = pd.Series(
            [candle.close for candle in candles],
            dtype=float,
        )

        fast_value = ema(
            close_prices,
            self.fast_ema_period,
        ).iloc[-1]

        slow_value = ema(
            close_prices,
            self.slow_ema_period,
        ).iloc[-1]

        if fast_value > slow_value:
            return MarketTrend.TREND_UP

        if fast_value < slow_value:
            return MarketTrend.TREND_DOWN

        return MarketTrend.RANGE

    @staticmethod
    def _detect_simple_trend(
        candles: Sequence[Candle],
    ) -> MarketTrend:
        first_close = candles[0].close
        last_close = candles[-1].close

        if last_close > first_close:
            return MarketTrend.TREND_UP

        if last_close < first_close:
            return MarketTrend.TREND_DOWN

        return MarketTrend.RANGE
