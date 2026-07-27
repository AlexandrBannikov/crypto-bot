import json
from datetime import datetime, timezone
from pathlib import Path

from app.runtime_health import HealthStatus, overall_status, run_health_checks


NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def make_runtime(tmp_path: Path, *, candle: int | None = None) -> dict:
    state = tmp_path / "trading_controller.json"
    state.write_text(json.dumps({
        "position_quantity": "0", "entry_price": None, "stop_loss": None,
        "virtual_balance": "1000", "total_fees": "0", "realized_pnl": "0",
        "closed_trades": 0, "entry_fee": "0",
    }))
    stamp = tmp_path / "trading_controller_last_candle.txt"
    stamp.write_text(str(candle or int(NOW.timestamp()) - 3600))
    journal = tmp_path / "journal.jsonl"
    journal.write_text("")
    shadow = tmp_path / "shadow.jsonl"
    shadow.write_text("")
    return {"state_path": state, "candle_path": stamp, "journal_path": journal, "shadow_path": shadow, "lock_path": tmp_path / "lock"}


def test_valid_state_is_ok_without_network(tmp_path):
    checks, _ = run_health_checks(**make_runtime(tmp_path), now=NOW, no_network=True)
    assert overall_status(checks) == HealthStatus.OK


def test_missing_and_damaged_state_are_critical(tmp_path):
    paths = make_runtime(tmp_path)
    paths["state_path"].unlink()
    checks, _ = run_health_checks(**paths, now=NOW, no_network=True)
    assert overall_status(checks) == HealthStatus.CRITICAL
    paths["state_path"].write_text("{")
    checks, _ = run_health_checks(**paths, now=NOW, no_network=True)
    assert overall_status(checks) == HealthStatus.CRITICAL


def test_stale_candle_and_aggregation(tmp_path):
    paths = make_runtime(tmp_path, candle=int(NOW.timestamp()) - 200 * 60)
    checks, _ = run_health_checks(**paths, now=NOW, no_network=True, max_candle_age_minutes=90)
    assert overall_status(checks) == HealthStatus.CRITICAL


def test_bybit_unavailable_is_captured(tmp_path):
    def fail():
        raise ConnectionError("offline")
    checks, _ = run_health_checks(**make_runtime(tmp_path), now=NOW, market_fetcher=fail)
    assert next(c for c in checks if c.name == "bybit_api").status == HealthStatus.CRITICAL


def test_incomplete_final_jsonl_is_safe(tmp_path):
    paths = make_runtime(tmp_path)
    paths["shadow_path"].write_bytes(b'{"candle_timestamp":1}\n{"bad"')
    checks, context = run_health_checks(**paths, now=NOW, no_network=True)
    assert len(context["shadow_diagnostics"]) == 1
    assert next(c for c in checks if c.name == "shadow_diagnostics").status == HealthStatus.WARNING


def test_invalid_balance_and_position_are_critical(tmp_path):
    paths = make_runtime(tmp_path)
    payload = json.loads(paths["state_path"].read_text())
    payload["virtual_balance"] = "-1"
    paths["state_path"].write_text(json.dumps(payload))
    checks, _ = run_health_checks(**paths, now=NOW, no_network=True)
    assert overall_status(checks) == HealthStatus.CRITICAL
