"""Isolated threshold-60 variant of the scored-candidate shadow runtime."""
from __future__ import annotations

from dataclasses import replace

from app.risk_allocation import RiskAllocationConfig
from app.scored_candidate import ScoredCandidateConfig


STRATEGY_NAME = "scored_candidate_v1_score60"
MINIMUM_ENTRY_SCORE = 60.0


def experiment_config(base: ScoredCandidateConfig | None = None) -> ScoredCandidateConfig:
    """Clone the baseline config, changing only the entry threshold."""
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
    fields = baseline.__dataclass_fields__
    return {
        name: (getattr(baseline, name), getattr(experiment, name))
        for name in fields
        if getattr(baseline, name) != getattr(experiment, name)
    }
