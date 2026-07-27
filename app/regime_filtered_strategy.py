from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from app.candle import Candle
from app.market_regime import (
    MarketRegime,
    MarketRegimeDetector,
    MarketTrend,
    MarketVolatility,
)
from app.signal_normalizer import normalize_signal
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_filter import TradingFilter
from app.trading_types import PositionSide, TradeAction


StrategySignal = Signal | TradeSignal | TradeAction


class Strategy(Protocol):
    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> StrategySignal:
        ...


class EntryBlockReason(str, Enum):
    RANGE = "range"
    DOWNTREND = "downtrend"
    HIGH_VOLATILITY = "high_volatility"
    LOW_CONFIDENCE = "low_confidence"
    UNKNOWN_REGIME = "unknown_regime"


@dataclass(frozen=True, slots=True)
class EntryFilterStatistics:
    allowed_entries: int
    blocked_entries: int
    blocked_by_reason: dict[str, int]


class RegimeFilteredStrategy:
    """Apply a market-regime filter only to new position entries."""

    def __init__(
        self,
        base_strategy: Strategy,
        regime_detector: MarketRegimeDetector,
        trading_filter: TradingFilter,
        *,
        apply_filter: bool = True,
    ) -> None:
        self.base_strategy = base_strategy
        self.regime_detector = regime_detector
        self.trading_filter = trading_filter
        self.apply_filter = apply_filter
        self._position_side: PositionSide | None = None
        self._allowed_entries = 0
        self._blocked_entries = 0
        self._blocked_by_reason: Counter[str] = Counter()

    @property
    def statistics(self) -> EntryFilterStatistics:
        reasons = {
            reason.value: self._blocked_by_reason[reason.value]
            for reason in EntryBlockReason
        }
        assert sum(reasons.values()) == self._blocked_entries
        return EntryFilterStatistics(
            allowed_entries=self._allowed_entries,
            blocked_entries=self._blocked_entries,
            blocked_by_reason=reasons,
        )

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> StrategySignal:
        raw_signal = self.base_strategy.generate_signal(candles, index)
        action = normalize_signal(raw_signal).action

        if action in {
            TradeAction.CLOSE_LONG,
            TradeAction.CLOSE_SHORT,
        }:
            self._register_exit(action)
            return raw_signal

        if action not in {
            TradeAction.OPEN_LONG,
            TradeAction.OPEN_SHORT,
        }:
            return raw_signal

        if self._position_side is not None:
            return raw_signal

        regime = self.regime_detector.detect(candles[: index + 1])
        if (
            self.apply_filter
            and not self.trading_filter.allow_entry(regime)
        ):
            self._blocked_entries += 1
            reason = self._block_reason(regime)
            self._blocked_by_reason[reason.value] += 1
            return TradeAction.HOLD

        self._allowed_entries += 1
        self._position_side = (
            PositionSide.LONG
            if action is TradeAction.OPEN_LONG
            else PositionSide.SHORT
        )
        return raw_signal

    def _register_exit(self, action: TradeAction) -> None:
        if (
            action is TradeAction.CLOSE_LONG
            and self._position_side is PositionSide.LONG
        ) or (
            action is TradeAction.CLOSE_SHORT
            and self._position_side is PositionSide.SHORT
        ):
            self._position_side = None

    def _block_reason(
        self,
        regime: MarketRegime,
    ) -> EntryBlockReason:
        if regime.trend is MarketTrend.UNKNOWN:
            return EntryBlockReason.UNKNOWN_REGIME
        if regime.trend is MarketTrend.RANGE:
            return EntryBlockReason.RANGE
        if regime.trend is MarketTrend.TREND_DOWN:
            return EntryBlockReason.DOWNTREND
        if regime.volatility is MarketVolatility.HIGH:
            return EntryBlockReason.HIGH_VOLATILITY
        return EntryBlockReason.LOW_CONFIDENCE
