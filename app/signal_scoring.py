"""Deterministic continuous scoring for the isolated scored candidate.

This module ranks setup quality; it is deliberately not a probability model.
It consumes only candles up to and including the evaluated closed candle.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import pandas as pd

from app.candle import Candle
from app.indicators import adx, atr


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _smooth(value: float, low: float, high: float) -> float:
    if not all(math.isfinite(item) for item in (value, low, high)) or high <= low:
        return 0.0
    return _clamp((value - low) / (high - low))


@dataclass(frozen=True, slots=True)
class ScoreContribution:
    name: str
    value: float
    maximum: float
    detail: str
    raw_value: float | None = None
    normalized_score: float | None = None


@dataclass(frozen=True, slots=True)
class SignalScoreConfig:
    fast_ema_period: int = 20
    slow_ema_period: int = 50
    adx_period: int = 14
    adx_low: float = 15.0
    adx_full: float = 35.0
    pullback_tolerance: float = 0.0075
    pullback_retrace: float = 0.0075
    volatility_low: float = 0.001
    volatility_full: float = 0.025
    fee_rate: float = 0.001
    stop_distance_pct: float = 0.02
    trend_weight: float = 25.0
    ema_alignment_weight: float = 15.0
    adx_weight: float = 20.0
    pullback_weight: float = 20.0
    momentum_weight: float = 10.0
    volatility_weight: float = 5.0
    cost_weight: float = 5.0
    version: str = "score_v1"

    def __post_init__(self) -> None:
        for name in ("fast_ema_period", "slow_ema_period", "adx_period"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.fast_ema_period >= self.slow_ema_period:
            raise ValueError("fast_ema_period must be below slow_ema_period")
        if self.adx_low < 0 or self.adx_full <= self.adx_low:
            raise ValueError("ADX bounds are invalid")
        if self.pullback_tolerance <= 0 or self.pullback_retrace <= 0:
            raise ValueError("pullback bounds must be positive")
        if self.volatility_low < 0 or self.volatility_full <= self.volatility_low:
            raise ValueError("volatility bounds are invalid")
        if self.fee_rate < 0 or self.stop_distance_pct <= 0:
            raise ValueError("cost/stop parameters are invalid")
        weights = self.maxima
        if any(not math.isfinite(value) or value < 0 for value in weights.values()):
            raise ValueError("score weights must be finite and non-negative")
        if abs(sum(weights.values()) - 100.0) > 1e-9:
            raise ValueError("score contributions must sum to 100")

    @property
    def maxima(self) -> dict[str, float]:
        return {
            "trend": self.trend_weight,
            "ema_alignment": self.ema_alignment_weight,
            "adx": self.adx_weight,
            "pullback": self.pullback_weight,
            "momentum": self.momentum_weight,
            "volatility": self.volatility_weight,
            "cost": self.cost_weight,
        }


@dataclass(frozen=True, slots=True)
class SignalScore:
    total_score: float
    trend_score: float
    ema_alignment_score: float
    adx_score: float
    pullback_score: float
    momentum_score: float
    volatility_score: float
    cost_score: float
    hard_blocks: tuple[str, ...]
    contributions: tuple[ScoreContribution, ...]
    version: str
    indicators: dict[str, float | None]

    def __post_init__(self) -> None:
        values = (self.total_score, self.trend_score, self.ema_alignment_score,
                  self.adx_score, self.pullback_score, self.momentum_score,
                  self.volatility_score, self.cost_score)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("signal score must be finite")
        if not 0.0 <= self.total_score <= 100.0:
            raise ValueError("signal score must be in 0..100")


def evaluate_signal(candles: Sequence[Candle], config: SignalScoreConfig = SignalScoreConfig()) -> SignalScore:
    """Score the last closed candle using only the supplied causal history."""
    if not candles:
        return _blocked_score(config, "insufficient_data")
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    required = config.slow_ema_period + config.adx_period + 2
    if len(ordered) < required:
        return _blocked_score(config, "insufficient_data")
    frame = pd.DataFrame({"high": [c.high for c in ordered], "low": [c.low for c in ordered], "close": [c.close for c in ordered]})
    close = frame["close"]
    fast = close.ewm(span=config.fast_ema_period, adjust=False).mean()
    slow = close.ewm(span=config.slow_ema_period, adjust=False).mean()
    adx_value = float(adx(frame, config.adx_period).iloc[-1])
    atr_relative = float((atr(frame, config.adx_period) / close).iloc[-1])
    values = (float(fast.iloc[-1]), float(slow.iloc[-1]), adx_value, atr_relative, ordered[-1].close, ordered[-1].open)
    if not all(math.isfinite(value) and value > 0 for value in values):
        return _blocked_score(config, "invalid_indicator")
    current = ordered[-1]
    previous_fast = float(fast.iloc[-2])
    previous_slow = float(slow.iloc[-2])
    trend_direction = 1.0 if fast.iloc[-1] > slow.iloc[-1] else 0.0
    trend_distance = abs(float(fast.iloc[-1] - slow.iloc[-1])) / current.close
    trend = _clamp(trend_direction * _smooth(trend_distance, 0.001, 0.03))
    alignment = _clamp(trend_direction * (0.5 + 0.5 * _smooth(trend_distance, 0.001, 0.02)))
    adx_quality = _smooth(adx_value, config.adx_low, config.adx_full)
    ema = float(fast.iloc[-1])
    touch = _clamp((ema - current.low) / (max(ema, 1e-12) * config.pullback_tolerance))
    near = _clamp(1.0 - abs(current.close - ema) / (max(ema, 1e-12) * config.pullback_tolerance))
    retrace = _clamp((float(fast.iloc[-1]) - current.close) / (max(float(fast.iloc[-1]), 1e-12) * config.pullback_retrace))
    pullback = _clamp(0.4 * touch + 0.4 * near + 0.2 * retrace)
    momentum = _clamp((current.close - current.open) / max(current.close * 0.01, 1e-12) + 0.5)
    volatility = 1.0 - abs(_smooth(atr_relative, config.volatility_low, config.volatility_full) - 0.5) * 2
    round_trip_cost = 2.0 * config.fee_rate
    cost = _clamp(1.0 - round_trip_cost / max(config.stop_distance_pct, 1e-12))
    maxima = config.maxima
    components = {
        "trend": trend * maxima["trend"], "ema_alignment": alignment * maxima["ema_alignment"],
        "adx": adx_quality * maxima["adx"], "pullback": pullback * maxima["pullback"],
        "momentum": momentum * maxima["momentum"], "volatility": volatility * maxima["volatility"],
        "cost": cost * maxima["cost"],
    }
    normalized = {
        "trend": trend, "ema_alignment": alignment, "adx": adx_quality,
        "pullback": pullback, "momentum": momentum,
        "volatility": volatility, "cost": cost,
    }
    raw = {
        "trend": trend_distance if trend_direction else 0.0,
        "ema_alignment": trend_distance if trend_direction else 0.0,
        "adx": adx_value, "pullback": current.close - ema,
        "momentum": (current.close - current.open) / current.close,
        "volatility": atr_relative, "cost": round_trip_cost,
    }
    details = {
        "trend": "EMA trend direction and distance",
        "ema_alignment": "fast EMA alignment above slow EMA",
        "adx": "ADX trend strength",
        "pullback": "distance and retrace around fast EMA",
        "momentum": "current candle return",
        "volatility": "ATR relative to price",
        "cost": "round-trip fees relative to stop distance",
    }
    contributions = tuple(
        ScoreContribution(name, value, maxima[name], details[name], raw[name], normalized[name])
        for name, value in components.items()
    )
    total = max(0.0, min(100.0, sum(components.values())))
    hard_blocks: list[str] = []
    if current.close <= 0:
        hard_blocks.append("invalid_market_data")
    return SignalScore(total, components["trend"], components["ema_alignment"], components["adx"], components["pullback"], components["momentum"], components["volatility"], components["cost"], tuple(hard_blocks), contributions, config.version, {"ema_fast": float(fast.iloc[-1]), "ema_slow": float(slow.iloc[-1]), "adx": adx_value, "atr_relative": atr_relative, "previous_ema_fast": previous_fast, "previous_ema_slow": previous_slow})


def _blocked_score(config: SignalScoreConfig, reason: str) -> SignalScore:
    contributions = tuple(
        ScoreContribution(name, 0.0, maximum, reason, None, None)
        for name, maximum in config.maxima.items()
    )
    return SignalScore(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, (reason,), contributions, config.version, {})
