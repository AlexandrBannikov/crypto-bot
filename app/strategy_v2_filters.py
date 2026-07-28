from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
import math
from typing import Protocol

import pandas as pd

from app.candle import Candle
from app.indicators import adx, atr
from app.regime_filtered_strategy import StrategySignal
from app.signal_normalizer import normalize_signal
from app.trading_types import TradeAction


class EntryFilterReason(str, Enum):
    ALLOWED = "allowed"
    BLOCKED_BY_ATR = "blocked_by_atr"
    BLOCKED_BY_ADX = "blocked_by_adx"
    INSUFFICIENT_HISTORY = "insufficient_history"
    INVALID_INDICATOR_VALUE = "invalid_indicator_value"


@dataclass(frozen=True, slots=True)
class EntryFilterDecision:
    filter_name: str
    allowed: bool
    reason: EntryFilterReason
    indicator_value: float | None = None


class EntryFilter(Protocol):
    name: str
    enabled: bool

    def evaluate(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> EntryFilterDecision:
        ...


@dataclass(frozen=True, slots=True)
class ATRFilterConfig:
    enabled: bool = False
    period: int = 14
    minimum_relative_atr: float = 0.005
    maximum_relative_atr: float = 0.020

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("ATR period must be greater than zero")
        bounds = (
            self.minimum_relative_atr,
            self.maximum_relative_atr,
        )
        if not all(math.isfinite(value) for value in bounds):
            raise ValueError("ATR bounds must be finite")
        if self.minimum_relative_atr < 0:
            raise ValueError(
                "minimum relative ATR must not be negative"
            )
        if self.maximum_relative_atr <= 0:
            raise ValueError(
                "maximum relative ATR must be greater than zero"
            )
        if (
            self.minimum_relative_atr
            > self.maximum_relative_atr
        ):
            raise ValueError(
                "minimum relative ATR must not exceed maximum"
            )


@dataclass(frozen=True, slots=True)
class ADXFilterConfig:
    enabled: bool = False
    period: int = 14
    minimum_adx: float = 20.0

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("ADX period must be greater than zero")
        if not math.isfinite(self.minimum_adx):
            raise ValueError("minimum ADX must be finite")
        if self.minimum_adx < 0:
            raise ValueError("minimum ADX must not be negative")


def _ohlc_frame(
    candles: Sequence[Candle],
    index: int,
) -> pd.DataFrame:
    if index < 0 or index >= len(candles):
        raise IndexError("candle index is out of range")
    history = candles[: index + 1]
    return pd.DataFrame(
        {
            "high": [candle.high for candle in history],
            "low": [candle.low for candle in history],
            "close": [candle.close for candle in history],
        }
    )


class ATRVolatilityFilter:
    """Allow entries when relative ATR is inside an inclusive range."""

    name = "atr"

    def __init__(self, config: ATRFilterConfig) -> None:
        self.config = config
        self.enabled = config.enabled

    def evaluate(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> EntryFilterDecision:
        if not self.enabled:
            return EntryFilterDecision(
                self.name, True, EntryFilterReason.ALLOWED
            )
        frame = _ohlc_frame(candles, index)
        close = float(frame["close"].iloc[-1])
        if not math.isfinite(close) or close <= 0:
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.INVALID_INDICATOR_VALUE,
            )
        value = atr(frame, period=self.config.period).iloc[-1]
        if pd.isna(value):
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.INSUFFICIENT_HISTORY,
            )
        relative = float(value) / close
        if not math.isfinite(relative):
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.INVALID_INDICATOR_VALUE,
            )
        allowed = (
            self.config.minimum_relative_atr
            <= relative
            <= self.config.maximum_relative_atr
        )
        return EntryFilterDecision(
            self.name,
            allowed,
            (
                EntryFilterReason.ALLOWED
                if allowed
                else EntryFilterReason.BLOCKED_BY_ATR
            ),
            relative,
        )


class ADXStrengthFilter:
    """Allow entries when ADX is at or above the inclusive threshold."""

    name = "adx"

    def __init__(self, config: ADXFilterConfig) -> None:
        self.config = config
        self.enabled = config.enabled

    def evaluate(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> EntryFilterDecision:
        if not self.enabled:
            return EntryFilterDecision(
                self.name, True, EntryFilterReason.ALLOWED
            )
        frame = _ohlc_frame(candles, index)
        value = adx(frame, period=self.config.period).iloc[-1]
        if pd.isna(value):
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.INSUFFICIENT_HISTORY,
            )
        numeric = float(value)
        if not math.isfinite(numeric):
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.INVALID_INDICATOR_VALUE,
            )
        allowed = numeric >= self.config.minimum_adx
        return EntryFilterDecision(
            self.name,
            allowed,
            (
                EntryFilterReason.ALLOWED
                if allowed
                else EntryFilterReason.BLOCKED_BY_ADX
            ),
            numeric,
        )


@dataclass(frozen=True, slots=True)
class CompositeEntryDecision:
    allowed: bool
    decisions: tuple[EntryFilterDecision, ...]


class AllEntryFilters:
    """Evaluate every enabled filter and combine results with AND logic."""

    def __init__(self, filters: Sequence[EntryFilter]) -> None:
        self.filters = tuple(item for item in filters if item.enabled)

    def evaluate(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> CompositeEntryDecision:
        decisions = tuple(
            item.evaluate(candles, index) for item in self.filters
        )
        return CompositeEntryDecision(
            allowed=all(item.allowed for item in decisions),
            decisions=decisions,
        )


class ResearchEntryFilteredStrategy:
    """Research-only wrapper that filters entries and preserves all exits."""

    def __init__(
        self,
        base_strategy,
        entry_filters: AllEntryFilters,
    ) -> None:
        self.base_strategy = base_strategy
        self.entry_filters = entry_filters
        self._reason_counts: Counter[str] = Counter()
        self._entry_decisions = 0

    @property
    def reason_counts(self) -> dict[str, int]:
        return {
            reason.value: self._reason_counts[reason.value]
            for reason in EntryFilterReason
        }

    @property
    def entry_decisions(self) -> int:
        return self._entry_decisions

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> StrategySignal:
        raw_signal = self.base_strategy.generate_signal(candles, index)
        action = normalize_signal(raw_signal).action
        if action not in {
            TradeAction.OPEN_LONG,
            TradeAction.OPEN_SHORT,
        }:
            return raw_signal
        if not self.entry_filters.filters:
            return raw_signal
        self._entry_decisions += 1
        decision = self.entry_filters.evaluate(candles, index)
        for item in decision.decisions:
            self._reason_counts[item.reason.value] += 1
        if decision.allowed:
            return raw_signal
        return TradeAction.HOLD

