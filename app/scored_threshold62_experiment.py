"""Isolated threshold-62 variant of the scored-candidate shadow runtime."""
from __future__ import annotations

from dataclasses import replace

from app.risk_allocation import RiskAllocationConfig
from app.scored_candidate import ScoredCandidateConfig


STRATEGY_NAME = "scored_candidate_62"
MINIMUM_ENTRY_SCORE = 62.0


def experiment_config(
    base: ScoredCandidateConfig | None = None,
) -> ScoredCandidateConfig:
    """Clone baseline configuration, changing only its entry threshold."""
    baseline = base or ScoredCandidateConfig()
    allocation = replace(
        baseline.allocation,
        minimum_entry_score=MINIMUM_ENTRY_SCORE,
    )
    return replace(baseline, allocation=allocation)


def configuration_delta(
    baseline: RiskAllocationConfig,
    experiment: RiskAllocationConfig,
) -> dict[str, tuple[object, object]]:
    return {
        name: (getattr(baseline, name), getattr(experiment, name))
        for name in baseline.__dataclass_fields__
        if getattr(baseline, name) != getattr(experiment, name)
    }

