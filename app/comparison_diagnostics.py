"""Compatibility assessment for analytical strategy comparisons."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

STATUSES = {"COMPATIBLE", "PARTIAL", "INSUFFICIENT", "INCOMPATIBLE", "ERROR"}


def _number(value: Any) -> Decimal | None:
    if value in (None, "N/A", ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise TypeError("comparison metric is not numeric") from None
    if not result.is_finite():
        raise TypeError("comparison metric is not finite")
    return result


def assess_comparison(
    production: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    *, matched_candles: int = 0,
    production_only: int = 0,
    candidate_only: int = 0,
) -> dict[str, Any]:
    if not isinstance(production, dict) or not isinstance(candidate, dict):
        return {"comparison_status": "INCOMPATIBLE", "comparison_error_code": "COMPARISON_SCHEMA_MISMATCH", "reason": "metrics schema mismatch"}
    try:
        for metrics in (production, candidate):
            for field in ("equity", "return_percent", "profit_factor", "win_rate"):
                _number(metrics.get(field))
    except TypeError:
        return {"comparison_status": "ERROR", "comparison_error_code": "COMPARISON_NUMERIC_TYPE_ERROR", "reason": "invalid numeric metric"}
    if matched_candles <= 0:
        return {"comparison_status": "INSUFFICIENT", "comparison_error_code": "COMPARISON_HISTORY_INSUFFICIENT", "reason": "недостаточно сопоставимой истории"}
    partial = production_only > 0 or candidate_only > 0
    return {"comparison_status": "PARTIAL" if partial else "COMPATIBLE", "comparison_error_code": None, "reason": "partial overlap" if partial else None}
