"""Read-only integrity checks for the SQLite equity history."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any

from app.equity_history import SnapshotStorage


def check_equity_history(path: Path, *, mode: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    if mode is not None and mode not in {"production", "candidate"}:
        raise ValueError("mode must be production or candidate")
    storage = SnapshotStorage(path)
    rows = storage.query(environment=mode) if path.exists() else []
    duplicates = sum(v - 1 for v in Counter((r.environment, r.snapshot_at_utc) for r in rows).values() if v > 1)
    invalid_values = 0
    missing_fields = 0
    negative_equity = 0
    out_of_order = 0
    gaps = 0
    previous = None
    required = ("snapshot_at_utc", "environment", "equity", "cash_balance", "total_pnl")
    for row in rows:
        if any(getattr(row, field, None) is None for field in required):
            missing_fields += 1
        values = (row.equity, row.cash_balance, row.total_pnl, row.drawdown_pct)
        if any(not value.is_finite() for value in values):
            invalid_values += 1
        if row.equity < 0:
            negative_equity += 1
        stamp = datetime.fromisoformat(row.snapshot_at_utc.replace("Z", "+00:00"))
        if previous is not None:
            delta = (stamp - previous).total_seconds()
            if delta < 0:
                out_of_order += 1
            if delta > 7200:
                gaps += 1
        previous = stamp
    last_age = None
    if rows:
        current = now or datetime.now(timezone.utc)
        last_age = max(0, int((current - datetime.fromisoformat(rows[-1].snapshot_at_utc.replace("Z", "+00:00"))).total_seconds() / 60))
    issues = duplicates + invalid_values + missing_fields + negative_equity + out_of_order
    status = "INSUFFICIENT_DATA" if not rows else "OK" if issues == 0 else "WARNING"
    return {"status": status, "snapshots": len(rows), "duplicates": duplicates, "invalid_values": invalid_values, "missing_fields": missing_fields, "negative_equity": negative_equity, "out_of_order": out_of_order, "large_gaps": gaps, "last_snapshot_age_minutes": last_age, "environment": mode or "all"}
