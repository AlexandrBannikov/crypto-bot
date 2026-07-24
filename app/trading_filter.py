from app.market_regime import (
    MarketRegime,
    MarketTrend,
    MarketVolatility,
)


class TradingFilter:
    def __init__(self, minimum_confidence: float = 0.0) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(
                "Minimum confidence must be between 0.0 and 1.0"
            )

        self.minimum_confidence = minimum_confidence

    def allow_entry(self, regime: MarketRegime) -> bool:
        if regime.trend is not MarketTrend.TREND_UP:
            return False

        if regime.volatility is MarketVolatility.HIGH:
            return False

        if regime.confidence < self.minimum_confidence:
            return False

        return True
