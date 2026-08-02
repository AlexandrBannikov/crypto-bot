from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import json

from app.candidate_diagnostics import summarize_candidate
from app.equity_integrity import check_equity_history
from app.performance_guard import PerformanceGuardConfig, evaluate_performance_guard
from app.equity_history import SnapshotConflictError, SnapshotStorage
from dataclasses import replace
from tests.test_equity_history import snapshot
import sqlite3
from dataclasses import fields
from app.equity_history import EquitySnapshot
from scripts import repair_equity_history


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


def test_storage_deduplicates_different_snapshot_reasons(tmp_path: Path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    first, created = storage.insert(snapshot(snapshot_reason="cycle"))
    second, duplicate = storage.insert(snapshot(snapshot_reason="trade_open"))
    assert created is True
    assert duplicate is False
    assert first.id == second.id


def test_storage_rejects_canonical_conflict(tmp_path: Path):
    storage = SnapshotStorage(tmp_path / "equity.db")
    storage.insert(snapshot())
    with __import__("pytest").raises(SnapshotConflictError):
        storage.insert(replace(snapshot(), equity=Decimal("999")))


def test_expected_multi_reason_rows_are_not_repaired_as_duplicates(tmp_path: Path):
    database = tmp_path / "equity.db"
    storage = SnapshotStorage(database)
    storage.insert(snapshot(environment="production", strategy_name="production"))
    storage.insert(snapshot(environment="candidate", strategy_name="candidate_adx_hybrid"))
    columns = [field.name for field in fields(EquitySnapshot) if field.name != "id"]
    with sqlite3.connect(database) as connection:
        names = ",".join(columns)
        production_select = ",".join(
            "'trade_open'" if field == "snapshot_reason" else
            "NULL" if field == "source_cycle_id" else field
            for field in columns
        )
        connection.execute(
            f"INSERT INTO equity_snapshots ({names}) SELECT {production_select} FROM equity_snapshots WHERE environment='production' AND strategy_name='production'"
        )
        candidate_select = ",".join(
            "'daily_close'" if field == "snapshot_reason" else
            "NULL" if field == "source_cycle_id" else field
            for field in columns
        )
        connection.execute(
            f"INSERT INTO equity_snapshots ({names}) SELECT {candidate_select} FROM equity_snapshots WHERE environment='candidate' AND strategy_name='candidate_adx_hybrid'"
        )
    assert repair_equity_history.main(["--mode", "production", "--database", str(database), "--deduplicate-exact", "--dry-run"]) == 0
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM equity_snapshots").fetchone()[0] == 4
    result = check_equity_history(database)
    assert result["exact_duplicates"] == 0
    assert result["expected_multi_reason_snapshots"] == 2
