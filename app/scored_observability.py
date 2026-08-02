"""Explain an already calculated entry score without changing trading logic."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from statistics import median
from typing import Any

from app.runtime_health import read_jsonl_safely
from app.signal_scoring import SignalScore


COMPONENT_ORDER = ("trend", "ema_alignment", "adx", "pullback", "momentum", "volatility", "cost")
CALCULATION_VERSION = "score_breakdown_v1"


@dataclass(frozen=True, slots=True)
class ScoredReportingConfig:
    strong_entry_threshold: float = 80.0
    max_limiters: int = 3
    limiter_min_deficit_pct: float = 10.0
    max_positive_factors: int = 3
    positive_factor_min_pct: float = 60.0
    score_reconciliation_tolerance: float = 0.000001


def load_reporting_config(path: Path | None = None) -> ScoredReportingConfig:
    target = path or Path(__file__).resolve().parents[1] / "config/scored_reporting.json"
    if not target.exists():
        return ScoredReportingConfig()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return ScoredReportingConfig(**payload)
    except (OSError, ValueError, TypeError):
        return ScoredReportingConfig()


@dataclass(frozen=True, slots=True)
class ScoreComponentDetails:
    raw_value: float | None
    normalized_score: float | None
    weight: float
    weighted_score: float
    max_weighted_score: float
    completion_pct: float | None
    status: str
    reason: str
    deficit: float


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    total_score: float
    max_score: float
    entry_threshold: float
    strong_entry_threshold: float | None
    distance_to_entry: float
    distance_to_strong_entry: float | None
    decision: str
    risk_allocation_pct: float
    risk_allocation_amount: float | None
    baseline_position_amount: float | None
    score_band: str
    allocation_rule_id: str
    allocation_reason: str
    score_components: dict[str, ScoreComponentDetails]
    main_limiters: tuple[dict[str, Any], ...]
    positive_factors: tuple[dict[str, Any], ...]
    blocking_factors: tuple[str, ...]
    score_consistent: bool
    reconciliation_difference: float
    reconciliation_warning: str | None
    calculation_version: str
    calculated_at: str
    candle_timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _status(completion: float | None) -> str:
    if completion is None:
        return "unavailable"
    if completion < 40:
        return "weak"
    if completion < 70:
        return "neutral"
    return "strong"


def build_score_breakdown(
    score: SignalScore, *, decision: str, entry_threshold: float,
    strong_entry_threshold: float | None, risk_fraction: float,
    risk_allocation_amount: float | None, baseline_position_amount: float | None,
    blocking_factors: list[str] | tuple[str, ...], candle_timestamp: int,
    allocation_rule_id: str, calculated_at: str | None = None,
    reporting: ScoredReportingConfig = ScoredReportingConfig(),
) -> ScoreBreakdown:
    contributions = {item.name: item for item in score.contributions}
    components: dict[str, ScoreComponentDetails] = {}
    for name in COMPONENT_ORDER:
        item = contributions.get(name)
        if item is None:
            components[name] = ScoreComponentDetails(None, None, 0.0, 0.0, 0.0, None, "unavailable", "component unavailable", 0.0)
            continue
        if item.normalized_score is None:
            components[name] = ScoreComponentDetails(item.raw_value, None, item.maximum, item.value, item.maximum, None, "unavailable", item.detail, max(0.0, item.maximum - item.value))
            continue
        completion = item.value * 100 / item.maximum if item.maximum else None
        components[name] = ScoreComponentDetails(
            item.raw_value, item.normalized_score, item.maximum, item.value,
            item.maximum, completion, _status(completion), item.detail,
            max(0.0, item.maximum - item.value),
        )
    available = [(index, name, item) for index, (name, item) in enumerate(components.items()) if item.status != "unavailable"]
    limiters = [
        {"component": name, "deficit": item.deficit, "deficit_pct": item.deficit * 100 / item.max_weighted_score,
         "completion_pct": item.completion_pct, "reason": item.reason}
        for _, name, item in sorted(available, key=lambda row: (-row[2].deficit, row[0]))
        if item.max_weighted_score and item.deficit * 100 / item.max_weighted_score >= reporting.limiter_min_deficit_pct
    ][:reporting.max_limiters]
    positives = [
        {"component": name, "completion_pct": item.completion_pct, "weighted_score": item.weighted_score, "reason": item.reason}
        for _, name, item in sorted(available, key=lambda row: (-float(row[2].completion_pct or 0), row[0]))
        if item.weighted_score > 0 and float(item.completion_pct or 0) >= reporting.positive_factor_min_pct
    ][:reporting.max_positive_factors]
    component_total = sum(item.weighted_score for item in components.values())
    difference = component_total - score.total_score
    consistent = abs(difference) <= reporting.score_reconciliation_tolerance
    strong_distance = score.total_score - strong_entry_threshold if strong_entry_threshold is not None else None
    band = "below_entry" if score.total_score < entry_threshold else "strong" if strong_entry_threshold is not None and score.total_score >= strong_entry_threshold else "reduced"
    reason = f"score below {entry_threshold:g}" if band == "below_entry" else (
        f"allocation not applied: {', '.join(blocking_factors)}" if risk_fraction <= 0 and blocking_factors
        else f"score {score.total_score:.6g} in {band} band"
    )
    return ScoreBreakdown(
        score.total_score, 100.0, entry_threshold, strong_entry_threshold,
        score.total_score - entry_threshold, strong_distance, decision,
        risk_fraction * 100, risk_allocation_amount, baseline_position_amount,
        band, allocation_rule_id, reason, components, tuple(limiters),
        tuple(positives), tuple(blocking_factors), consistent, difference,
        None if consistent else f"component sum differs from total by {difference:.9f}",
        CALCULATION_VERSION, calculated_at or datetime.now(timezone.utc).isoformat(), candle_timestamp,
    )


def breakdown_from_record(row: dict[str, Any]) -> dict[str, Any] | None:
    value = row.get("score_breakdown")
    if not isinstance(value, dict) or not isinstance(value.get("score_components"), dict):
        return None
    if not all(isinstance(value.get(key), (int, float)) for key in ("total_score", "max_score", "entry_threshold", "distance_to_entry")):
        return None
    return value


def display_name(name: str) -> str:
    return name.replace("_", " ").title()


def threshold_distance_text(value: float) -> str:
    if value < 0:
        return f"До минимального входа: {abs(value):.2f} балла"
    return f"Выше минимального порога на: {value:.2f} балла"


def format_breakdown(row: dict[str, Any], *, component_limit: int = 5) -> str:
    detail = breakdown_from_record(row)
    if detail is None:
        return "🧪 Scored Candidate — shadow\nStatus: initialized\nScore breakdown: N/A\nreason: unavailable or legacy record"
    components = detail.get("score_components", {})
    shown = list(components.items())[:component_limit]
    lines = [
        "🧪 Scored Candidate — shadow", "Status: initialized",
        f"Decision: {detail.get('decision', row.get('decision', 'N/A'))}",
        f"Score: {float(detail['total_score']):.2f} / {float(detail['max_score']):g}",
        f"Entry threshold: {float(detail['entry_threshold']):g}",
        f"Strong threshold: {float(detail['strong_entry_threshold']):g}" if detail.get("strong_entry_threshold") is not None else "Strong threshold: N/A",
        threshold_distance_text(float(detail["distance_to_entry"])),
        f"Risk allocation: {float(detail.get('risk_allocation_pct', 0)):.1f}% / " + (f"{float(detail['risk_allocation_amount']):.2f} USDT" if detail.get("risk_allocation_amount") is not None else "N/A"),
        "Baseline position: " + (f"{float(detail['baseline_position_amount']):.2f} USDT" if detail.get("baseline_position_amount") is not None else "N/A"),
        f"Allocation rule: {detail.get('score_band', 'N/A')} / {detail.get('allocation_rule_id', 'N/A')} — {detail.get('allocation_reason', 'N/A')}",
        f"Candle timestamp: {detail.get('candle_timestamp', 'N/A')}",
        f"Consistency: {'PASS' if detail.get('score_consistent', False) else 'WARN'}",
        "Компоненты:",
    ]
    for name, item in shown:
        completion = item.get("completion_pct")
        pct = "N/A" if completion is None else f"{float(completion):.0f}%"
        lines.append(f"- {display_name(name)}: {float(item.get('weighted_score', 0)):.2f} / {float(item.get('max_weighted_score', 0)):.2f} — {pct} — {item.get('status', 'unavailable')}")
        if component_limit > 5:
            lines.append(f"  reason: {item.get('reason', 'N/A')}")
    if len(components) > component_limit:
        lines.append(f"Ещё компонентов: {len(components) - component_limit}")
    lines.append("Главные ограничители:")
    limiters = detail.get("main_limiters") or []
    lines.extend(f"- {display_name(item['component'])}: дефицит {float(item['deficit']):.2f}" for item in limiters)
    if not limiters:
        lines.append("- отсутствуют")
    lines.append("Сильные факторы:")
    positives = detail.get("positive_factors") or []
    lines.extend(f"- {display_name(item['component'])}: {float(item['completion_pct']):.0f}%" for item in positives)
    if not positives:
        lines.append("- отсутствуют")
    if not detail.get("score_consistent", True):
        lines.append(f"WARN: {detail.get('reconciliation_warning', 'score breakdown inconsistent')}")
    return "\n".join(lines)


def aggregate(path: Path, *, hours: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    rows = read_jsonl_safely(path)[0] if path.exists() else []
    if hours is not None:
        cutoff = (now or datetime.now(timezone.utc)).timestamp() - timedelta(hours=hours).total_seconds()
        rows = [row for row in rows if float(row.get("candle_close_timestamp", 0)) >= cutoff]
    scores = [float(row.get("score_total", row.get("signal_score", row.get("score", 0)))) for row in rows]
    allocations = [float(row.get("risk_allocation_pct", float(row.get("risk_fraction", 0)) * 100)) for row in rows]
    thresholds = [float(row.get("entry_threshold", 65)) for row in rows]
    decisions = Counter(str(row.get("decision", row.get("action", "UNKNOWN"))) for row in rows)
    bands = Counter("below_entry" if s < 65 else "strong" if s >= 80 else "reduced" for s in scores)
    limiters = Counter(item.get("component") for row in rows for item in row.get("main_limiters", []) if isinstance(item, dict) and item.get("component"))
    component_values: dict[str, list[float]] = {}
    for row in rows:
        for name, item in row.get("score_components", {}).items():
            if isinstance(item, dict) and isinstance(item.get("weighted_score"), (int, float)):
                component_values.setdefault(name, []).append(float(item["weighted_score"]))
    total = len(rows)
    return {
        "period_hours": hours, "decisions_total": total,
        "score": {"average": sum(scores) / total if total else None, "median": median(scores) if scores else None,
                  "minimum": min(scores) if scores else None, "maximum": max(scores) if scores else None},
        "score_bands": {"below_65_pct": sum(s < 65 for s in scores) * 100 / total if total else None,
                        "65_to_79_pct": sum(65 <= s < 80 for s in scores) * 100 / total if total else None,
                        "at_least_80_pct": sum(s >= 80 for s in scores) * 100 / total if total else None},
        "average_distance_to_entry": sum(s - t for s, t in zip(scores, thresholds)) / total if total else None,
        "frequent_limiters": dict(limiters.most_common()),
        "average_components": {name: sum(values) / len(values) for name, values in component_values.items()},
        "decisions": dict(decisions), "average_allocation_pct": sum(allocations) / total if total else None,
        "allocation_bands": dict(bands),
    }
