"""Read-only integrity and gap diagnostics for SQLite equity history."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.equity_history import SnapshotStorage, _snapshots_equivalent


def _stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _group_key(row: Any) -> tuple[str, str, int | None]:
    return row.environment, row.strategy_name, row.candle_close_timestamp


def check_equity_history(
    path: Path, *, mode: str | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    if mode is not None and mode not in {"production", "candidate"}:
        raise ValueError("mode must be production or candidate")
    storage = SnapshotStorage(path)
    rows = storage.query(environment=mode) if path.exists() else []
    groups: dict[tuple[str, str, int | None], list[Any]] = defaultdict(list)
    for row in rows:
        groups[_group_key(row)].append(row)
    exact_duplicates = timestamp_duplicates = timestamp_conflicts = 0
    duplicate_groups: list[dict[str, Any]] = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        equivalent = all(_snapshots_equivalent(items[0], item) for item in items[1:])
        if equivalent:
            timestamp_duplicates += len(items) - 1
            exact = all(
                all(getattr(item, name) == getattr(items[0], name) for name in (
                    "cash_balance", "asset_quantity", "position_value", "equity",
                    "realized_pnl", "unrealized_pnl", "total_pnl", "return_pct",
                    "position_side", "entry_price", "closed_trades", "cumulative_fees",
                )) for item in items[1:]
            )
            if exact:
                exact_duplicates += len(items) - 1
            duplicate_groups.append({
                "environment": key[0], "strategy": key[1],
                "snapshot_timestamp": key[2], "type": "exact" if exact else "equivalent",
                "ids": [item.id for item in items],
            })
        else:
            timestamp_conflicts += len(items) - 1
            duplicate_groups.append({
                "environment": key[0], "strategy": key[1],
                "snapshot_timestamp": key[2], "type": "conflict",
                "ids": [item.id for item in items],
                "values": [{"id": item.id, "equity": str(item.equity), "cash": str(item.cash_balance), "created_at": item.created_at_utc} for item in items],
            })

    # A valid schema enforces environment separation. Any row outside the two
    # namespaces is reported as a cross-mode/namespace error.
    cross_mode_collisions = sum(
        1 for row in rows if row.environment not in {"production", "candidate"}
    )
    invalid_values = 0
    missing_fields = 0
    negative_equity = 0
    out_of_order = 0
    gaps: list[dict[str, Any]] = []
    by_series: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in rows:
        if any(getattr(row, field, None) is None for field in ("snapshot_at_utc", "environment", "equity", "cash_balance", "total_pnl")):
            missing_fields += 1
        if any(not value.is_finite() for value in (row.equity, row.cash_balance, row.total_pnl, row.drawdown_pct)):
            invalid_values += 1
        if row.equity < 0:
            negative_equity += 1
        by_series[(row.environment, row.strategy_name)].append(row)
    for series, series_rows in by_series.items():
        ordered = sorted(series_rows, key=lambda item: (item.candle_close_timestamp or -1, item.id or -1))
        previous = None
        for row in ordered:
            if previous is not None:
                if row.candle_close_timestamp is not None and previous.candle_close_timestamp is not None:
                    delta = row.candle_close_timestamp - previous.candle_close_timestamp
                    if delta < 0:
                        out_of_order += 1
                    timeframe = max(1, int(previous.timeframe or row.timeframe or 60)) * 60
                    if delta > timeframe * 1.5:
                        estimated = max(0, round(delta / timeframe) - 1)
                        gaps.append({
                            "mode": series[0], "strategy": series[1],
                            "previous_timestamp": previous.candle_close_timestamp,
                            "next_timestamp": row.candle_close_timestamp,
                            "duration_seconds": delta,
                            "expected_interval_seconds": timeframe,
                            "estimated_missing_snapshots": estimated,
                            "classification": "UNKNOWN",
                        })
            previous = row
    last_age = None
    if rows:
        current = now or datetime.now(timezone.utc)
        last_age = max(0, int((current - _stamp(max(rows, key=lambda item: _stamp(item.snapshot_at_utc)).snapshot_at_utc)).total_seconds() / 60))
    if not rows:
        status = "INSUFFICIENT_DATA"
    elif timestamp_conflicts or invalid_values or missing_fields or negative_equity or out_of_order or cross_mode_collisions:
        status = "ERROR"
    elif timestamp_duplicates or gaps:
        status = "WARNING"
    else:
        status = "OK"
    return {
        "status": status, "snapshots": len(rows),
        "exact_duplicates": exact_duplicates,
        "timestamp_duplicates": timestamp_duplicates,
        "timestamp_conflicts": timestamp_conflicts,
        "cross_mode_collisions": cross_mode_collisions,
        "duplicates": timestamp_duplicates,
        "invalid_values": invalid_values, "missing_fields": missing_fields,
        "negative_equity": negative_equity, "out_of_order": out_of_order,
        "gaps": gaps, "large_gaps": len(gaps),
        "duplicate_groups": duplicate_groups,
        "last_snapshot_age_minutes": last_age, "environment": mode or "all",
    }
