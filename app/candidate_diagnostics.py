"""Read-only diagnostics for the paper candidate decision journal."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from app.runtime_health import read_jsonl_safely
from app.trade_journal import TradeJournalEntry

REASONS = (
    "adx_below_threshold", "trend_not_confirmed", "pullback_not_detected",
    "hybrid_score_too_low", "regime_not_allowed", "risk_rejected",
    "position_already_open", "cooldown", "insufficient_history",
    "invalid_indicator", "no_signal", "entry_allowed", "exit_signal",
    "other",
)


def _reason(row: dict[str, Any]) -> str:
    value = str(row.get("reason_code") or "").strip().lower()
    if value in REASONS:
        return value
    text = str(row.get("reason") or "").lower()
    if "adx" in text and ("below" in text or "threshold" in text):
        return "adx_below_threshold"
    if "pullback" in text:
        return "pullback_not_detected"
    if "trend" in text or "ema" in text and "valid" in text:
        return "trend_not_confirmed"
    if str(row.get("action", "")).lower() in {"open_long", "open_short"}:
        return "entry_allowed" if row.get("entry_allowed") else "risk_rejected"
    if str(row.get("action", "")).lower().startswith("close"):
        return "exit_signal"
    return "no_signal"


def summarize_candidate(
    decision_path: Path,
    trade_path: Path | None = None,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    if decision_path.exists():
        raw, ignored = read_jsonl_safely(decision_path)
        rows = [item for item in raw if isinstance(item, dict)]
        if ignored:
            warnings.append("incomplete final decision line ignored")
    if start or end:
        lo = int((start or datetime.min.replace(tzinfo=timezone.utc)).timestamp())
        hi = int((end or datetime.max.replace(tzinfo=timezone.utc)).timestamp())
        rows = [r for r in rows if lo <= int(r.get("candle_timestamp", -1)) < hi]
    trades: list[Any] = []
    if trade_path and trade_path.exists():
        trades, ignored = read_jsonl_safely(trade_path, parser=TradeJournalEntry.from_dict)
        if ignored:
            warnings.append("incomplete final trade line ignored")
    reasons = Counter(_reason(row) for row in rows)
    adx = [float(row["adx"]) for row in rows if row.get("adx") is not None]
    score = [float(row["hybrid_score"]) for row in rows if row.get("hybrid_score") is not None]
    entries = sum(_reason(row) == "entry_allowed" for row in rows)
    no_signal = reasons.get("no_signal", 0)
    factor_fields = {
        "trend": ("trend", "trend_ok"),
        "ema_alignment": ("ema_alignment", "ema_aligned"),
        "adx": ("adx",), "pullback": ("pullback", "pullback_detected"),
        "momentum": ("momentum",), "cost": ("cost", "cost_ok"),
        "regime": ("regime", "market_regime"),
    }
    distributions: dict[str, dict[str, int]] = {}
    for label, fields in factor_fields.items():
        values = Counter()
        for row in rows:
            value = next((row.get(field) for field in fields if row.get(field) is not None), None)
            if value is not None:
                values[str(value)] += 1
        distributions[label] = dict(values)
    observable = any(distributions.values())
    subreasons = Counter(
        str(row["no_signal_subreason"]) for row in rows
        if row.get("no_signal_subreason")
    )
    return {
        "candidate": "ADX + HYBRID Pullback",
        "decisions": len(rows), "trades": len(trades),
        "entry_rate_percent": entries / len(rows) * 100 if rows else None,
        "rejection_reasons": dict(sorted(reasons.items())),
        "no_signal_count": no_signal,
        "no_signal_percentage": no_signal / len(rows) * 100 if rows else None,
        "no_signal_subreasons": dict(subreasons) if subreasons else None,
        "factor_distributions": distributions,
        "observability_status": "AVAILABLE" if observable else "LEGACY_FIELDS_UNAVAILABLE",
        "near_miss_conditions": None if not observable else {
            key: sum(value for name, value in values.items() if name.lower() in {"false", "0", "failed"})
            for key, values in distributions.items()
        },
        "adx": {"min": min(adx) if adx else None, "avg": sum(adx) / len(adx) if adx else None, "max": max(adx) if adx else None},
        "hybrid_score": {"min": min(score) if score else None, "avg": sum(score) / len(score) if score else None, "max": max(score) if score else None},
        "warnings": warnings,
        "conclusion": (
            "No trades observed; diagnostics are read-only and do not infer strategy changes." if rows and not trades
            else "No candidate decisions available." if not rows
            else "Candidate has recorded entries."
        ),
    }


def render_candidate_diagnostics(report: dict[str, Any]) -> str:
    lines = [f"Candidate: {report['candidate']}", f"Decisions: {report['decisions']}", f"Trades: {report['trades']}"]
    rate = report["entry_rate_percent"]
    lines.append(f"Entry rate: {'N/A' if rate is None else f'{rate:.1f}%'}")
    lines.append("\nRejection reasons:")
    for key, value in report["rejection_reasons"].items():
        lines.append(f"{key}: {value}")
    for label, values in (("ADX", report["adx"]), ("Hybrid score", report["hybrid_score"])):
        if values["min"] is not None:
            lines.append(f"{label} min/avg/max: {values['min']:.3f}/{values['avg']:.3f}/{values['max']:.3f}")
    lines.extend(["", "Conclusion:", report["conclusion"]])
    return "\n".join(lines)
