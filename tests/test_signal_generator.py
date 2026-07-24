from app.market_regime import (
    MarketRegime,
    MarketTrend,
    MarketVolatility,
)
from app.signal_generator import SignalGenerator, TradeSignal
from app.trading_filter import TradingFilter


def test_market_ready_when_filter_allows() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.NORMAL,
        confidence=0.8,
    )

    generator = SignalGenerator()

    assert generator.market_ready(regime)


def test_market_not_ready_when_filter_rejects() -> None:
    regime = MarketRegime(
        trend=MarketTrend.RANGE,
        volatility=MarketVolatility.NORMAL,
        confidence=0.8,
    )

    generator = SignalGenerator()

    assert not generator.market_ready(regime)


class RejectAllFilter:
    def allow_entry(self, regime: MarketRegime) -> bool:
        return False


def test_market_ready_uses_injected_filter() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.NORMAL,
        confidence=1.0,
    )

    generator = SignalGenerator(trading_filter=RejectAllFilter())

    assert not generator.market_ready(regime)


def test_generate_returns_buy_when_market_is_ready() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.NORMAL,
        confidence=0.8,
    )

    generator = SignalGenerator()

    assert generator.generate(regime) == "BUY"


def test_generate_returns_hold_when_market_is_not_ready() -> None:
    regime = MarketRegime(
        trend=MarketTrend.RANGE,
        volatility=MarketVolatility.NORMAL,
        confidence=0.8,
    )

    generator = SignalGenerator()

    assert generator.generate(regime) == "HOLD"


def test_generate_returns_trade_signal_enum() -> None:
    from app.signal_generator import TradeSignal

    regime = MarketRegime(
        trend=MarketTrend.TREND_UP,
        volatility=MarketVolatility.NORMAL,
        confidence=0.8,
    )

    generator = SignalGenerator()

    assert generator.generate(regime) is TradeSignal.BUY


def test_generate_returns_sell_for_downtrend() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_DOWN,
        volatility=MarketVolatility.NORMAL,
        confidence=0.8,
    )

    generator = SignalGenerator()

    assert generator.generate(regime) is TradeSignal.SELL


def test_generate_returns_hold_for_downtrend_with_high_volatility() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_DOWN,
        volatility=MarketVolatility.HIGH,
        confidence=0.8,
    )

    generator = SignalGenerator()

    assert generator.generate(regime) is TradeSignal.HOLD


def test_generate_returns_hold_for_downtrend_with_low_confidence() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_DOWN,
        volatility=MarketVolatility.NORMAL,
        confidence=0.1,
    )

    generator = SignalGenerator(
        trading_filter=TradingFilter(minimum_confidence=0.5)
    )

    assert generator.generate(regime) is TradeSignal.HOLD


def test_generate_returns_sell_when_confidence_equals_minimum() -> None:
    regime = MarketRegime(
        trend=MarketTrend.TREND_DOWN,
        volatility=MarketVolatility.NORMAL,
        confidence=0.5,
    )

    generator = SignalGenerator(
        trading_filter=TradingFilter(minimum_confidence=0.5)
    )

    assert generator.generate(regime) is TradeSignal.SELL
