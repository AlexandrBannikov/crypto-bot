"""Diagnostics dedicated to the optional threshold-60 shadow experiment."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.scored_candidate_diagnostics import summarize
from app.scored_threshold_experiment import MINIMUM_ENTRY_SCORE, STRATEGY_NAME


def summarize_threshold60(path: Path, *, days: int | None = None, now: datetime | None = None) -> dict:
    result = summarize(path, days=days, now=now)
    result["strategy_name"] = STRATEGY_NAME
    result["minimum_entry_score"] = MINIMUM_ENTRY_SCORE
    return result
