"""Strict closed-candle ordering and continuity validation."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from app.candle import Candle


class MarketContinuityError(ValueError):
    """Market history cannot be processed causally without missing candles."""


@dataclass(frozen=True, slots=True)
class CandleContinuity:
    candles: tuple[Candle, ...]
    first_timestamp: int | None
    last_timestamp: int | None
    unresolved_gap: bool


def validate_candle_continuity(
    candles: Sequence[Candle],
    *,
    timeframe_seconds: int,
    last_processed_timestamp: int | None = None,
) -> CandleContinuity:
    if timeframe_seconds <= 0:
        raise ValueError("timeframe_seconds must be positive")

    by_timestamp: dict[int, Candle] = {}
    previous_timestamp: int | None = None
    for candle in candles:
        timestamp = candle.timestamp
        if isinstance(timestamp, bool) or not isinstance(timestamp, int):
            raise MarketContinuityError("candle timestamp must be an integer")
        if timestamp < 0 or timestamp % timeframe_seconds:
            raise MarketContinuityError("candle timestamp is not timeframe-aligned")
        if timestamp in by_timestamp:
            raise MarketContinuityError(f"duplicate candle timestamp: {timestamp}")
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise MarketContinuityError(
                f"out-of-order candle timestamp: {previous_timestamp} -> {timestamp}"
            )
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(math.isfinite(float(value)) and float(value) > 0 for value in prices):
            raise MarketContinuityError("candle prices must be finite and positive")
        if not math.isfinite(float(candle.volume)) or candle.volume < 0:
            raise MarketContinuityError("candle volume must be finite and non-negative")
        if candle.high < max(candle.open, candle.low, candle.close):
            raise MarketContinuityError("invalid candle high")
        if candle.low > min(candle.open, candle.high, candle.close):
            raise MarketContinuityError("invalid candle low")
        by_timestamp[timestamp] = candle
        previous_timestamp = timestamp

    ordered = tuple(by_timestamp[key] for key in sorted(by_timestamp))
    for left, right in zip(ordered, ordered[1:]):
        if right.timestamp - left.timestamp != timeframe_seconds:
            raise MarketContinuityError(
                f"candle gap: {left.timestamp} -> {right.timestamp}"
            )

    unresolved_gap = False
    if last_processed_timestamp is not None:
        if last_processed_timestamp < 0:
            raise ValueError("last_processed_timestamp must not be negative")
        new_candles = tuple(
            candle for candle in ordered
            if candle.timestamp > last_processed_timestamp
        )
        if new_candles:
            unresolved_gap = (
                new_candles[0].timestamp
                != last_processed_timestamp + timeframe_seconds
            )

    return CandleContinuity(
        candles=ordered,
        first_timestamp=ordered[0].timestamp if ordered else None,
        last_timestamp=ordered[-1].timestamp if ordered else None,
        unresolved_gap=unresolved_gap,
    )
