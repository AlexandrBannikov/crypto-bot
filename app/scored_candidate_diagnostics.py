"""Read-only quality diagnostics for scored-candidate shadow decisions."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.runtime_health import read_jsonl_safely

COMPONENTS = ("trend", "ema_alignment", "adx", "pullback", "momentum", "volatility", "cost")


def summarize(path: Path, *, days: int | None = None, now: datetime | None = None) -> dict:
    rows = read_jsonl_safely(path)[0] if path.exists() else []
    if days is not None:
        current = now or datetime.now(timezone.utc)
        cutoff = current.timestamp() - timedelta(days=days).total_seconds()
        rows = [row for row in rows if float(row.get("candle_close_timestamp", 0)) >= cutoff]
    scores = [float(row.get("signal_score", row.get("score", 0))) for row in rows]
    decisions = Counter(row.get("decision", row.get("action", "UNKNOWN")) for row in rows)
    averages = {
        name: (sum(float(row.get("components", {}).get(f"{name}_score", row.get("components", {}).get(name, 0))) for row in rows) / len(rows) if rows else None)
        for name in COMPONENTS
    }
    buckets = {}
    for low in range(0, 100, 10):
        selected = [row for row, score in zip(rows, scores) if low <= score < low + 10 or (low == 90 and score == 100)]
        actions = Counter(row.get("decision", row.get("action", "UNKNOWN")) for row in selected)
        buckets[f"{low}-{low + 10}"] = {
            "count": len(selected),
            "average_score": sum(float(row.get("signal_score", row.get("score", 0))) for row in selected) / len(selected) if selected else None,
            "average_risk_fraction": sum(float(row.get("risk_fraction", 0)) for row in selected) / len(selected) if selected else None,
            "enter": actions["ENTER_LONG"], "hold": actions["HOLD"],
        }
    limiters = Counter()
    for row in rows:
        components = row.get("components", {})
        ratios = {}
        maxima = {"trend": 25, "ema_alignment": 15, "adx": 20, "pullback": 20, "momentum": 10, "volatility": 5, "cost": 5}
        for name in COMPONENTS:
            ratios[name] = float(components.get(f"{name}_score", components.get(name, 0))) / maxima[name]
        if ratios:
            limiters[min(ratios, key=ratios.get)] += 1
    total = len(rows)
    return {
        "strategy_name": "scored_candidate_v1", "mode": "shadow", "days": days,
        "total_candles": total, "decisions": dict(decisions),
        "score": {"average": sum(scores) / len(scores) if scores else None, "minimum": min(scores) if scores else None, "maximum": max(scores) if scores else None},
        "average_components": averages,
        "hard_blocks": dict(Counter(block for row in rows for block in row.get("hard_blocks", []))),
        "score_distribution": buckets,
        "main_limiters": {name: {"count": count, "percent": count * 100 / total if total else 0} for name, count in limiters.most_common()},
        "last": rows[-1] if rows else None,
    }
