from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import json

from app.candidate_diagnostics import summarize_candidate
from app.equity_integrity import check_equity_history
from app.performance_guard import PerformanceGuardConfig, evaluate_performance_guard


def test_candidate_reasons_are_aggregated(tmp_path: Path):
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text("\n".join(json.dumps({"candle_timestamp": i, "reason_code": code, "adx": 10 + i}) for i, code in enumerate(("adx_below_threshold", "pullback_not_detected", "trend_not_confirmed"))) + "\n")
    report = summarize_candidate(decisions)
    assert report["decisions"] == 3
    assert report["rejection_reasons"]["adx_below_threshold"] == 1


def test_empty_equity_history_is_insufficient(tmp_path: Path):
    result = check_equity_history(tmp_path / "missing.db", mode="production")
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["snapshots"] == 0


def test_performance_guard_distinguishes_insufficient_and_drawdown():
    stamp = datetime.now(timezone.utc).isoformat()
    item = type("Snapshot", (), {"snapshot_at_utc": stamp, "drawdown_pct": Decimal("6"), "closed_trades": 20, "realized_pnl": Decimal("0"), "unrealized_pnl": Decimal("0"), "total_pnl": Decimal("0")})()
    result = evaluate_performance_guard([item], config=PerformanceGuardConfig())
    assert result["status"] == "WARNING"
