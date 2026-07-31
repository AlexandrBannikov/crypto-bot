"""Continuous score-to-risk allocation and stop-aware position sizing."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os

from app.risk import PositionSize, RiskConfig, RiskManager
from app.trading_types import PositionSide


@dataclass(frozen=True, slots=True)
class RiskAllocationConfig:
    minimum_entry_score: float = 65.0
    full_risk_score: float = 93.0
    minimum_risk_fraction: float = 0.10
    maximum_risk_fraction: float = 1.00
    curve: str = "power"
    curve_exponent: float = 2.0
    version: str = "risk_curve_v1"

    @classmethod
    def from_env(cls) -> "RiskAllocationConfig":
        return cls(
            minimum_entry_score=float(os.environ.get("SCORED_MINIMUM_ENTRY_SCORE", "65")),
            full_risk_score=float(os.environ.get("SCORED_FULL_RISK_SCORE", "93")),
            minimum_risk_fraction=float(os.environ.get("SCORED_MINIMUM_RISK_FRACTION", "0.10")),
            maximum_risk_fraction=float(os.environ.get("SCORED_MAXIMUM_RISK_FRACTION", "1.0")),
            curve=os.environ.get("SCORED_ALLOCATION_CURVE", "power"),
            curve_exponent=float(os.environ.get("SCORED_CURVE_EXPONENT", "2.0")),
            version=os.environ.get("SCORED_RISK_MODEL_VERSION", "risk_curve_v1"),
        )

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_entry_score < self.full_risk_score <= 100:
            raise ValueError("score bounds are invalid")
        if not 0 <= self.minimum_risk_fraction <= self.maximum_risk_fraction <= 1:
            raise ValueError("risk fractions must be in 0..1")
        if self.curve not in {"linear", "power"}:
            raise ValueError("curve must be linear or power")
        if self.curve_exponent <= 0 or not math.isfinite(self.curve_exponent):
            raise ValueError("curve_exponent must be positive and finite")


def risk_fraction(score: float, config: RiskAllocationConfig = RiskAllocationConfig()) -> float:
    if not math.isfinite(score):
        raise ValueError("score must be finite")
    if score < config.minimum_entry_score:
        return 0.0
    x = max(0.0, min(1.0, (score - config.minimum_entry_score) / (config.full_risk_score - config.minimum_entry_score)))
    curved = x if config.curve == "linear" else x ** config.curve_exponent
    return max(0.0, min(1.0, config.minimum_risk_fraction + (config.maximum_risk_fraction - config.minimum_risk_fraction) * curved))


@dataclass(frozen=True, slots=True)
class SizedRisk:
    score: float
    risk_fraction: float
    position: PositionSize | None
    hard_blocks: tuple[str, ...]
    risk_model_version: str


def size_for_score(*, score: float, balance: float, entry_price: float, stop_loss: float, side: PositionSide, base_risk_per_trade: float = 0.01, allocation: RiskAllocationConfig = RiskAllocationConfig(), minimum_position_value: float = 0.0) -> SizedRisk:
    fraction = risk_fraction(score, allocation)
    blocks: list[str] = []
    if fraction <= 0:
        blocks.append("risk_allocation_zero")
        return SizedRisk(score, fraction, None, tuple(blocks), allocation.version)
    try:
        manager = RiskManager(RiskConfig(risk_per_trade=base_risk_per_trade * fraction))
        position = manager.calculate_position_size(balance=balance, entry_price=entry_price, stop_loss=stop_loss, side=side)
    except (ValueError, ZeroDivisionError) as exc:
        blocks.append("invalid_stop_distance")
        return SizedRisk(score, fraction, None, tuple(blocks), allocation.version)
    if position.position_value < minimum_position_value:
        blocks.append("position_below_minimum")
        return SizedRisk(score, fraction, None, tuple(blocks), allocation.version)
    return SizedRisk(score, fraction, position, tuple(blocks), allocation.version)
