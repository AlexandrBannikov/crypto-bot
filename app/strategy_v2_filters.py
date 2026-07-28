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
    WAITING_PULLBACK = "waiting_pullback"
    PULLBACK_CONFIRMED = "pullback_confirmed"
    PULLBACK_TIMEOUT = "pullback_timeout"
    PULLBACK_CANCELLED = "pullback_cancelled"


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


class PullbackTouchMode(str, Enum):
    LOW_TOUCH = "LOW_TOUCH"
    CLOSE_TOUCH = "CLOSE_TOUCH"


@dataclass(frozen=True, slots=True)
class PullbackFilterConfig:
    enabled: bool = False
    max_wait_bars: int = 5
    touch_mode: PullbackTouchMode = PullbackTouchMode.LOW_TOUCH

    def __post_init__(self) -> None:
        if self.max_wait_bars <= 0:
            raise ValueError(
                "pullback max wait bars must be greater than zero"
            )
        if not isinstance(self.touch_mode, PullbackTouchMode):
            raise ValueError("invalid pullback touch mode")


@dataclass(slots=True)
class PullbackEvent:
    cross_index: int
    cross_price: float
    resolution_index: int | None = None
    wait_bars: int | None = None
    reason: EntryFilterReason = EntryFilterReason.WAITING_PULLBACK
    entry_allowed: bool = False


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


class PullbackEntryFilter:
    """Defer LONG entries until an EMA-fast pullback is confirmed.

    LOW_TOUCH confirms when low <= fast EMA and close > fast EMA.
    CLOSE_TOUCH requires a close at/below fast EMA followed by a close back
    above it. The original cross bar is never eligible for confirmation.
    """

    name = "pullback"

    def __init__(
        self,
        config: PullbackFilterConfig,
        *,
        fast_ema_period: int = 20,
        slow_ema_period: int = 50,
    ) -> None:
        if fast_ema_period <= 0 or slow_ema_period <= 0:
            raise ValueError("pullback EMA periods must be positive")
        if fast_ema_period >= slow_ema_period:
            raise ValueError(
                "pullback fast EMA must be lower than slow EMA"
            )
        self.config = config
        self.enabled = config.enabled
        self.fast_ema_period = fast_ema_period
        self.slow_ema_period = slow_ema_period
        self._pending: PullbackEvent | None = None
        self.events: list[PullbackEvent] = []

    @property
    def pending(self) -> bool:
        return self._pending is not None

    def arm(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> EntryFilterDecision:
        if index < 0 or index >= len(candles):
            raise IndexError("candle index is out of range")
        event = PullbackEvent(
            cross_index=index,
            cross_price=float(candles[index].close),
        )
        self._pending = event
        self.events.append(event)
        return EntryFilterDecision(
            self.name,
            False,
            EntryFilterReason.WAITING_PULLBACK,
        )

    def cancel(self, index: int) -> EntryFilterDecision:
        if self._pending is not None:
            self._resolve(
                self._pending,
                index,
                EntryFilterReason.PULLBACK_CANCELLED,
            )
        return EntryFilterDecision(
            self.name,
            False,
            EntryFilterReason.PULLBACK_CANCELLED,
        )

    def evaluate(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> EntryFilterDecision:
        if not self.enabled:
            return EntryFilterDecision(
                self.name, True, EntryFilterReason.ALLOWED
            )
        if self._pending is None:
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.PULLBACK_CANCELLED,
            )
        event = self._pending
        if index <= event.cross_index:
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.WAITING_PULLBACK,
            )
        frame = _ohlc_frame(candles, index)
        fast_values = frame["close"].ewm(
            span=self.fast_ema_period,
            adjust=False,
            min_periods=self.fast_ema_period,
        ).mean()
        slow_values = frame["close"].ewm(
            span=self.slow_ema_period,
            adjust=False,
            min_periods=self.slow_ema_period,
        ).mean()
        fast = fast_values.iloc[-1]
        slow = slow_values.iloc[-1]
        if pd.isna(fast) or pd.isna(slow):
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.INSUFFICIENT_HISTORY,
            )
        fast_number = float(fast)
        slow_number = float(slow)
        close = float(frame["close"].iloc[-1])
        if not all(
            math.isfinite(value)
            for value in (fast_number, slow_number, close)
        ):
            self._resolve(
                event,
                index,
                EntryFilterReason.PULLBACK_CANCELLED,
            )
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.INVALID_INDICATOR_VALUE,
            )
        if fast_number <= slow_number:
            self._resolve(
                event,
                index,
                EntryFilterReason.PULLBACK_CANCELLED,
            )
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.PULLBACK_CANCELLED,
            )
        if self.config.touch_mode is PullbackTouchMode.LOW_TOUCH:
            touched = (
                float(frame["low"].iloc[-1]) <= fast_number
                and close > fast_number
            )
        else:
            previous_fast = float(fast_values.iloc[-2])
            previous_close = float(frame["close"].iloc[-2])
            touched = (
                math.isfinite(previous_fast)
                and previous_close <= previous_fast
                and close > fast_number
            )
        if touched:
            self._resolve(
                event,
                index,
                EntryFilterReason.PULLBACK_CONFIRMED,
            )
            return EntryFilterDecision(
                self.name,
                True,
                EntryFilterReason.PULLBACK_CONFIRMED,
                fast_number,
            )
        if index - event.cross_index >= self.config.max_wait_bars:
            self._resolve(
                event,
                index,
                EntryFilterReason.PULLBACK_TIMEOUT,
            )
            return EntryFilterDecision(
                self.name,
                False,
                EntryFilterReason.PULLBACK_TIMEOUT,
            )
        return EntryFilterDecision(
            self.name,
            False,
            EntryFilterReason.WAITING_PULLBACK,
            fast_number,
        )

    def mark_entry_allowed(self) -> None:
        if self.events:
            self.events[-1].entry_allowed = True

    def finish(self, final_index: int) -> None:
        if self._pending is not None:
            self._resolve(
                self._pending,
                final_index,
                EntryFilterReason.PULLBACK_CANCELLED,
            )

    def _resolve(
        self,
        event: PullbackEvent,
        index: int,
        reason: EntryFilterReason,
    ) -> None:
        event.resolution_index = index
        event.wait_bars = max(0, index - event.cross_index)
        event.reason = reason
        self._pending = None


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
        *,
        exclude: frozenset[str] = frozenset(),
    ) -> CompositeEntryDecision:
        decisions = tuple(
            item.evaluate(candles, index)
            for item in self.filters
            if item.name not in exclude
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
        pullbacks = [
            item
            for item in entry_filters.filters
            if isinstance(item, PullbackEntryFilter)
        ]
        if len(pullbacks) > 1:
            raise ValueError("only one pullback filter is supported")
        self.pullback = pullbacks[0] if pullbacks else None
        self._reason_counts: Counter[str] = Counter()
        self._entry_decisions = 0
        self._blocked_entries = 0

    @property
    def reason_counts(self) -> dict[str, int]:
        return {
            reason.value: self._reason_counts[reason.value]
            for reason in EntryFilterReason
        }

    @property
    def entry_decisions(self) -> int:
        return self._entry_decisions

    @property
    def blocked_entries(self) -> int:
        return self._blocked_entries

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> StrategySignal:
        raw_signal = self.base_strategy.generate_signal(candles, index)
        action = normalize_signal(raw_signal).action
        if self.pullback is not None:
            if action in {
                TradeAction.CLOSE_LONG,
                TradeAction.CLOSE_SHORT,
            }:
                if self.pullback.pending:
                    self._record(self.pullback.cancel(index))
                return raw_signal
            if action is TradeAction.OPEN_LONG:
                if self.pullback.pending:
                    self._record(self.pullback.cancel(index))
                self._entry_decisions += 1
                self._record(self.pullback.arm(candles, index))
                return TradeAction.HOLD
            if self.pullback.pending:
                pullback_decision = self.pullback.evaluate(
                    candles, index
                )
                if (
                    pullback_decision.reason
                    is not EntryFilterReason.WAITING_PULLBACK
                ):
                    self._record(pullback_decision)
                if (
                    pullback_decision.reason
                    is EntryFilterReason.PULLBACK_CONFIRMED
                ):
                    decision = self.entry_filters.evaluate(
                        candles,
                        index,
                        exclude=frozenset({self.pullback.name}),
                    )
                    for item in decision.decisions:
                        self._record(item)
                    if decision.allowed:
                        self.pullback.mark_entry_allowed()
                        return TradeAction.OPEN_LONG
                    self._blocked_entries += 1
                return raw_signal
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
            self._record(item)
        if decision.allowed:
            return raw_signal
        self._blocked_entries += 1
        return TradeAction.HOLD

    def finish(self, final_index: int) -> None:
        if self.pullback is not None and self.pullback.pending:
            self.pullback.finish(final_index)
            self._record(
                EntryFilterDecision(
                    self.pullback.name,
                    False,
                    EntryFilterReason.PULLBACK_CANCELLED,
                )
            )

    def _record(self, decision: EntryFilterDecision) -> None:
        self._reason_counts[decision.reason.value] += 1
