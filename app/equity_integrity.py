"""Read-only integrity, duplicate and gap diagnostics for equity history."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.equity_history import SnapshotStorage, _snapshots_equivalent

FINANCIAL_FIELDS = (
    "cash_balance", "asset_quantity", "position_value", "equity",
    "realized_pnl", "unrealized_pnl", "total_pnl", "return_pct",
    "position_side", "entry_price", "closed_trades", "cumulative_fees",
)
EXPECTED_REASON_PAIRS = {
    frozenset(("cycle", "trade_open")),
    frozenset(("cycle", "trade_close")),
    frozenset(("cycle", "daily_close")),
    frozenset(("cycle", "startup_recovery")),
}


def _stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _financial_equal(left: Any, right: Any) -> bool:
    return all(getattr(left, name) == getattr(right, name) for name in FINANCIAL_FIELDS)


def _safe_row(row: Any) -> dict[str, Any]:
    return {
        "id": row.id, "environment": row.environment,
        "strategy_name": row.strategy_name,
        "candle_close_timestamp": row.candle_close_timestamp,
        "snapshot_reason": row.snapshot_reason,
        "source_cycle_id_present": bool(row.source_cycle_id),
        "state_hash": row.state_hash,
        "created_at": row.created_at_utc,
    }


def _classify_group(items: list[Any]) -> tuple[str, bool]:
    financial = all(_financial_equal(items[0], item) for item in items[1:])
    reasons = {item.snapshot_reason for item in items}
    if not financial:
        return "conflict", False
    if len(reasons) == 1:
        return "exact_duplicate", True
    if any(item.snapshot_reason == "manual_backfill" for item in items):
        return "backfill_overlap", True
    if len(items) == 2 and frozenset(reasons) in EXPECTED_REASON_PAIRS:
        return "expected_multi_reason", True
    return "semantic_duplicate", True


def check_equity_history(
    path: Path, *, mode: str | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    if mode is not None and mode not in {"production", "candidate"}:
        raise ValueError("mode must be production or candidate")
    rows = SnapshotStorage(path).query(environment=mode) if path.exists() else []
    groups: dict[tuple[str, str, int | None], list[Any]] = defaultdict(list)
    for row in rows:
        groups[(row.environment, row.strategy_name, row.candle_close_timestamp)].append(row)

    counts = defaultdict(int)
    duplicate_groups: list[dict[str, Any]] = []
    conflicts = 0
    for _, items in groups.items():
        if len(items) < 2:
            continue
        classification, financial = _classify_group(items)
        amount = len(items) - 1
        counts[classification] += amount
        conflicts += amount if classification == "conflict" else 0
        duplicate_groups.append({
            "classification": classification,
            "type": "exact" if classification == "exact_duplicate" else classification,
            "environment": items[0].environment,
            "strategy_name": items[0].strategy_name,
            "candle_close_timestamp": items[0].candle_close_timestamp,
            "financial_equality": financial,
            "state_hash_equality": len({item.state_hash for item in items}) == 1,
            "records": [_safe_row(item) for item in items],
            "ids": [item.id for item in items],
        })

    invalid_values = missing_fields = negative_equity = 0
    by_series: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in rows:
        if any(getattr(row, field, None) is None for field in
               ("snapshot_at_utc", "environment", "equity", "cash_balance", "total_pnl")):
            missing_fields += 1
        if any(not value.is_finite() for value in
               (row.equity, row.cash_balance, row.total_pnl, row.drawdown_pct)):
            invalid_values += 1
        negative_equity += int(row.equity < 0)
        by_series[(row.environment, row.strategy_name)].append(row)

    runtime_gaps: list[dict[str, Any]] = []
    historical_boundaries: list[dict[str, Any]] = []
    for series, values in by_series.items():
        # Multiple reasons on one candle are a single point for continuity.
        unique = {}
        for row in sorted(values, key=lambda item: (item.candle_close_timestamp or -1, item.id or -1)):
            unique.setdefault(row.candle_close_timestamp, row)
        ordered = [row for timestamp, row in unique.items() if timestamp is not None]
        for index, (previous, row) in enumerate(zip(ordered, ordered[1:])):
            interval = max(1, int(previous.timeframe or row.timeframe or 60)) * 60
            delta = row.candle_close_timestamp - previous.candle_close_timestamp
            if delta <= interval * 1.5:
                continue
            gap = {
                "environment": series[0], "strategy_name": series[1],
                "start": previous.candle_close_timestamp,
                "end": row.candle_close_timestamp,
                "duration_seconds": delta,
                "expected_interval_seconds": interval,
                "actual_interval_seconds": delta,
                "estimated_missing_snapshots": max(0, round(delta / interval) - 1),
            }
            # The first transition is the deployment/backfill boundary: there
            # is no earlier established cadence against which runtime loss can
            # be asserted. Later discontinuities are runtime gaps.
            if index == 0:
                historical_boundaries.append({**gap, "classification": "HISTORICAL_BOUNDARY"})
            else:
                runtime_gaps.append({**gap, "classification": "RUNTIME_CANDLE_GAP"})

    cross_mode = sum(row.environment not in {"production", "candidate"} for row in rows)
    exact = counts["exact_duplicate"]
    semantic = counts["semantic_duplicate"] + counts["backfill_overlap"]
    if not rows:
        status = "INSUFFICIENT_DATA"
    elif conflicts or invalid_values or missing_fields or negative_equity or cross_mode:
        status = "ERROR"
    elif exact or runtime_gaps:
        status = "WARNING"
    elif historical_boundaries or semantic or counts["expected_multi_reason"]:
        status = "INFO"
    else:
        status = "OK"
    current = now or datetime.now(timezone.utc)
    age = (max(0, int((current - _stamp(max(rows, key=lambda r: _stamp(r.snapshot_at_utc)).snapshot_at_utc)).total_seconds() / 60)) if rows else None)
    return {
        "status": status, "snapshots": len(rows), "environment": mode or "all",
        "exact_duplicates": exact, "semantic_duplicates": semantic,
        "expected_multi_reason_snapshots": counts["expected_multi_reason"],
        "backfill_overlaps": counts["backfill_overlap"],
        "timestamp_duplicates": exact + semantic,
        "timestamp_conflicts": conflicts, "duplicates": exact + semantic,
        "runtime_gaps": runtime_gaps, "historical_boundaries": historical_boundaries,
        "gaps": runtime_gaps + historical_boundaries, "large_gaps": len(runtime_gaps),
        "duplicate_groups": duplicate_groups, "invalid_values": invalid_values,
        "missing_fields": missing_fields, "negative_equity": negative_equity,
        "cross_mode_collisions": cross_mode, "out_of_order": 0,
        "last_snapshot_age_minutes": age,
    }
