import pytest
from app.candle import Candle
from app.market_regime import (
    MarketRegime,
    MarketRegimeDetector,
    MarketTrend,
    MarketVolatility,
)

def test_market_regime_creation() -> None:
    regime = MarketRegime(
        trend=MarketTrend.UNKNOWN,
        volatility=MarketVolatility.NORMAL,
        confidence=0.0,
    )

    assert regime.trend is MarketTrend.UNKNOWN
    assert regime.volatility is MarketVolatility.NORMAL
    assert regime.confidence == 0.0

def test_market_regime_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        MarketRegime(
            trend=MarketTrend.UNKNOWN,
            volatility=MarketVolatility.NORMAL,
            confidence=1.1,
        )

def test_detector_returns_default_regime() -> None:
    detector = MarketRegimeDetector()

    regime = detector.detect([])

    assert regime.trend is MarketTrend.UNKNOWN
    assert regime.volatility is MarketVolatility.NORMAL
    assert regime.confidence == 0.0

def test_detector_returns_unknown_for_single_candle() -> None:
    detector = MarketRegimeDetector()

    candles = [
        Candle(
            timestamp=1,
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=10.0,
        )
    ]

    regime = detector.detect(candles)

    assert regime.trend is MarketTrend.UNKNOWN
    assert regime.volatility is MarketVolatility.NORMAL
    assert regime.confidence == 0.0

def test_detector_detects_uptrend() -> None:
    detector = MarketRegimeDetector()

    candles = [
        Candle(
            timestamp=1,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=10.0,
        ),
        Candle(
            timestamp=2,
            open=100.0,
            high=111.0,
            low=99.0,
            close=110.0,
            volume=12.0,
        ),
    ]

    regime = detector.detect(candles)

    assert regime.trend is MarketTrend.TREND_UP

def test_detector_detects_downtrend() -> None:
    detector = MarketRegimeDetector()

    candles = [
        Candle(
            timestamp=1,
            open=110.0,
            high=111.0,
            low=109.0,
            close=110.0,
            volume=10.0,
        ),
        Candle(
            timestamp=2,
            open=110.0,
            high=111.0,
            low=99.0,
            close=100.0,
            volume=12.0,
        ),
    ]

    regime = detector.detect(candles)

    assert regime.trend is MarketTrend.TREND_DOWN


def test_detector_detects_range() -> None:
    detector = MarketRegimeDetector()

    candles = [
        Candle(
            timestamp=1,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=10.0,
        ),
        Candle(
            timestamp=2,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=12.0,
        ),
    ]

    regime = detector.detect(candles)

    assert regime.trend is MarketTrend.RANGE


def test_detector_uses_adx_to_detect_range() -> None:
    detector = MarketRegimeDetector(
        fast_ema_period=3,
        slow_ema_period=5,
        adx_period=3,
        adx_threshold=20.0,
    )

    candles = [
        Candle(
            timestamp=index,
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.0 + index * 0.001,
            volume=10.0,
        )
        for index in range(20)
    ]

    regime = detector.detect(candles)

    assert regime.trend is MarketTrend.RANGE


def test_detector_uses_ema_direction_when_adx_is_strong() -> None:
    detector = MarketRegimeDetector(
        fast_ema_period=3,
        slow_ema_period=5,
        adx_period=3,
        adx_threshold=20.0,
    )

    candles = [
        Candle(
            timestamp=index,
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=10.0,
        )
        for index in range(20)
    ]

    regime = detector.detect(candles)

    assert regime.trend is MarketTrend.TREND_UP
