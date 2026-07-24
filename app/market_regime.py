from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from app.candle import Candle
from app.indicators import adx, atr, ema


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
        adx_period: int = 14,
        adx_threshold: float = 20.0,
        atr_period: int = 14,
        low_volatility_threshold: float = 0.005,
        high_volatility_threshold: float = 0.02,
    ) -> None:
        if fast_ema_period <= 0:
            raise ValueError("fast_ema_period must be greater than zero")

        if slow_ema_period <= 0:
            raise ValueError("slow_ema_period must be greater than zero")

        if fast_ema_period >= slow_ema_period:
            raise ValueError(
                "fast_ema_period must be less than slow_ema_period"
            )

        if adx_period <= 0:
            raise ValueError("adx_period must be greater than zero")

        if adx_threshold < 0:
            raise ValueError("adx_threshold must not be negative")

        if atr_period <= 0:
            raise ValueError("atr_period must be greater than zero")

        if low_volatility_threshold < 0:
            raise ValueError(
                "low_volatility_threshold must not be negative"
            )

        if high_volatility_threshold <= 0:
            raise ValueError(
                "high_volatility_threshold must be greater than zero"
            )

        if low_volatility_threshold >= high_volatility_threshold:
            raise ValueError(
                "low_volatility_threshold must be less than "
                "high_volatility_threshold"
            )

        self.fast_ema_period = fast_ema_period
        self.slow_ema_period = slow_ema_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.atr_period = atr_period
        self.low_volatility_threshold = low_volatility_threshold
        self.high_volatility_threshold = high_volatility_threshold

    def detect(self, candles: Sequence[Candle]) -> MarketRegime:
        if len(candles) < 2:
            return MarketRegime(
                trend=MarketTrend.UNKNOWN,
                volatility=MarketVolatility.NORMAL,
                confidence=0.0,
            )

        required_candles = max(
            self.slow_ema_period,
            self.adx_period * 2,
        )

        if len(candles) >= required_candles:
            trend = self._detect_trend_with_adx(candles)
        elif len(candles) >= self.slow_ema_period:
            trend = self._detect_ema_trend(candles)
        else:
            trend = self._detect_simple_trend(candles)

        volatility = self._detect_volatility(candles)

        return MarketRegime(
            trend=trend,
            volatility=volatility,
            confidence=1.0,
        )

    def _detect_trend_with_adx(
        self,
        candles: Sequence[Candle],
    ) -> MarketTrend:
        data = self._candles_to_dataframe(candles)

        adx_value = adx(
            data,
            period=self.adx_period,
        ).iloc[-1]

        if pd.isna(adx_value):
            return self._detect_ema_trend(candles)

        if adx_value < self.adx_threshold:
            return MarketTrend.RANGE

        return self._detect_ema_trend(candles)

    def _detect_volatility(
        self,
        candles: Sequence[Candle],
    ) -> MarketVolatility:
        if len(candles) < self.atr_period:
            return MarketVolatility.NORMAL

        data = self._candles_to_dataframe(candles)

        atr_value = atr(
            data,
            period=self.atr_period,
        ).iloc[-1]

        last_close = candles[-1].close

        if pd.isna(atr_value) or last_close == 0:
            return MarketVolatility.NORMAL

        relative_atr = float(atr_value) / abs(float(last_close))

        if relative_atr >= self.high_volatility_threshold:
            return MarketVolatility.HIGH

        if relative_atr <= self.low_volatility_threshold:
            return MarketVolatility.LOW

        return MarketVolatility.NORMAL

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
    def _candles_to_dataframe(
        candles: Sequence[Candle],
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "high": [candle.high for candle in candles],
                "low": [candle.low for candle in candles],
                "close": [candle.close for candle in candles],
            }
        )

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
