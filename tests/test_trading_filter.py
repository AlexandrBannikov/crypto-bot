from app.market_regime import (
    MarketRegime,
    MarketTrend,
    MarketVolatility,
)
from app.trading_filter import TradingFilter


def test_allow_uptrend_low_volatility() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.LOW,
        confidence=1.0,
    )

    assert TradingFilter().allow_entry(regime)


def test_allow_uptrend_normal_volatility() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.NORMAL,
        confidence=1.0,
    )

    assert TradingFilter().allow_entry(regime)


def test_reject_high_volatility() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.HIGH,
        confidence=1.0,
    )

    assert not TradingFilter().allow_entry(regime)


def test_reject_range_market() -> None:
    regime = MarketRegime(
        trend=MarketTrend.RANGE,
        volatility=MarketVolatility.NORMAL,
        confidence=1.0,
    )

    assert not TradingFilter().allow_entry(regime)


def test_reject_downtrend() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_DOWN,
        volatility=MarketVolatility.NORMAL,
        confidence=1.0,
    )

    assert not TradingFilter().allow_entry(regime)


def test_reject_low_confidence() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.NORMAL,
        confidence=0.4,
    )

    trading_filter = TradingFilter(
        minimum_confidence=0.6,
    )

    assert not trading_filter.allow_entry(regime)


def test_allow_confidence_equal_to_minimum() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.NORMAL,
        confidence=0.6,
    )

    trading_filter = TradingFilter(
        minimum_confidence=0.6,
    )

    assert trading_filter.allow_entry(regime)


def test_reject_negative_minimum_confidence() -> None:
    import pytest

    with pytest.raises(ValueError):
        TradingFilter(minimum_confidence=-0.1)


def test_reject_minimum_confidence_above_one() -> None:
    import pytest

    with pytest.raises(ValueError):
        TradingFilter(minimum_confidence=1.1)
