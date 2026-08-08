"""Read-only observability for scored-candidate 65 and threshold 62."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.scored_candidate_diagnostics import summarize
from app.scored_threshold62_experiment import (
    MINIMUM_ENTRY_SCORE,
    STRATEGY_NAME,
)


def _label(report: dict, *, name: str, threshold: float) -> dict:
    report["strategy_name"] = name
    report["minimum_entry_score"] = threshold
    decisions = report.get("decisions", {})
    report["counters"] = {
        "ENTER_LONG": int(decisions.get("ENTER_LONG", 0)),
        "EXIT_LONG": int(decisions.get("EXIT_LONG", 0)),
        "HOLD": int(decisions.get("HOLD", 0)),
    }
    return report


def summarize_threshold62(
    path: Path,
    *,
    days: int | None = None,
    now: datetime | None = None,
) -> dict:
    return _label(
        summarize(path, days=days, now=now),
        name=STRATEGY_NAME,
        threshold=MINIMUM_ENTRY_SCORE,
    )


def summarize_scored_65_62(
    threshold65_path: Path,
    threshold62_path: Path,
    *,
    days: int | None = None,
    now: datetime | None = None,
) -> dict[str, dict]:
    return {
        "scored_candidate_65": _label(
            summarize(threshold65_path, days=days, now=now),
            name="scored_candidate_65",
            threshold=65.0,
        ),
        "scored_candidate_62": summarize_threshold62(
            threshold62_path,
            days=days,
            now=now,
        ),
    }

