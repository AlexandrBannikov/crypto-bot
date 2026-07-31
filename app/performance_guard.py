"""Non-invasive production performance guard; reports only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import os
from typing import Any, Sequence


@dataclass(frozen=True, slots=True)
class PerformanceGuardConfig:
    enabled: bool = True
    min_closed_trades: int = 20
    warning_drawdown_pct: Decimal = Decimal("5")
    critical_drawdown_pct: Decimal = Decimal("10")
    max_hours_without_snapshot: int = 3

    @classmethod
    def from_env(cls) -> "PerformanceGuardConfig":
        return cls(
            enabled=os.environ.get("PERFORMANCE_GUARD_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
            min_closed_trades=int(os.environ.get("PERFORMANCE_MIN_CLOSED_TRADES", "20")),
            warning_drawdown_pct=Decimal(os.environ.get("PERFORMANCE_WARNING_DRAWDOWN_PCT", "5")),
            critical_drawdown_pct=Decimal(os.environ.get("PERFORMANCE_CRITICAL_DRAWDOWN_PCT", "10")),
            max_hours_without_snapshot=int(os.environ.get("PERFORMANCE_MAX_HOURS_WITHOUT_SNAPSHOT", "3")),
        )


def evaluate_performance_guard(
    snapshots: Sequence[Any], *, config: PerformanceGuardConfig | None = None,
    now: datetime | None = None,
    integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or PerformanceGuardConfig.from_env()
    if not cfg.enabled:
        return {"status": "INSUFFICIENT_DATA", "reason": "disabled"}
    if integrity and integrity.get("status") == "ERROR":
        return {"status": "DATA_QUALITY_ERROR", "reason": "equity history integrity error"}
    if not snapshots:
        return {"status": "INSUFFICIENT_DATA", "reason": "no snapshots"}
    latest = snapshots[-1]
    drawdown = Decimal(str(getattr(latest, "drawdown_pct", 0)))
    closed = int(getattr(latest, "closed_trades", 0))
    current = now or datetime.now(timezone.utc)
    stamp = datetime.fromisoformat(str(latest.snapshot_at_utc).replace("Z", "+00:00"))
    age_hours = max(0, (current - stamp).total_seconds() / 3600)
    if age_hours > cfg.max_hours_without_snapshot:
        status, reason = "DEGRADED", "stale snapshot"
    elif drawdown >= cfg.critical_drawdown_pct:
        status, reason = "DEGRADED", "drawdown exceeds critical threshold"
    elif drawdown >= cfg.warning_drawdown_pct:
        status, reason = "WARNING", "drawdown exceeds warning threshold"
    elif closed < cfg.min_closed_trades:
        status, reason = "INSUFFICIENT_DATA", "not enough closed trades"
    else:
        status, reason = "HEALTHY", "within configured limits"
    return {"status": status, "reason": reason, "drawdown_pct": str(drawdown), "closed_trades": closed, "snapshot_age_hours": round(age_hours, 3), "realized_pnl": str(getattr(latest, "realized_pnl", "N/A")), "unrealized_pnl": str(getattr(latest, "unrealized_pnl", "N/A")), "total_pnl": str(getattr(latest, "total_pnl", "N/A"))}
