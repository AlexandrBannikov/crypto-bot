from enum import Enum

from app.market_regime import (
    MarketRegime,
    MarketTrend,
    MarketVolatility,
)
from app.trading_filter import TradingFilter


class TradeSignal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalGenerator:
    def __init__(self, trading_filter: TradingFilter | None = None) -> None:
        self.trading_filter = trading_filter or TradingFilter()

    def market_ready(self, regime: MarketRegime) -> bool:
        return self.trading_filter.allow_entry(regime)

    def generate(self, regime: MarketRegime) -> TradeSignal:
        if (
            regime.trend is MarketTrend.TREND_DOWN
            and regime.volatility is not MarketVolatility.HIGH
            and regime.confidence >= self.trading_filter.minimum_confidence
        ):
            return TradeSignal.SELL

        if self.market_ready(regime):
            return TradeSignal.BUY

        return TradeSignal.HOLD
