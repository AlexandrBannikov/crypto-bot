import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.runtime_health import (
    HealthStatus,
    candle_timing_diagnostics,
    overall_status,
    run_health_checks,
)


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


def test_open_age_over_90_minutes_can_have_fresh_close_and_zero_lag(tmp_path):
    now = datetime(2026, 1, 1, 12, 59, tzinfo=timezone.utc)
    latest_open = int(datetime(2026, 1, 1, 11, tzinfo=timezone.utc).timestamp())
    checks, context = run_health_checks(
        **make_runtime(tmp_path, candle=latest_open), now=now,
        market_fetcher=lambda: latest_open,
    )
    timing = next(item for item in checks if item.name == "last_candle")
    lag = next(item for item in checks if item.name == "market_lag")
    assert timing.status == HealthStatus.OK
    assert timing.details["candle_open_age_seconds"] == 119 * 60
    assert timing.details["candle_close_age_seconds"] == 59 * 60
    assert lag.details["lag_candles"] == 0
    assert context["market_candle"] == latest_open


def test_real_lag_and_exact_hour_boundary():
    boundary = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    expected = int(datetime(2026, 1, 1, 11, tzinfo=timezone.utc).timestamp())
    exact = candle_timing_diagnostics(
        expected, timeframe_minutes=60, now=boundary
    )
    stale = candle_timing_diagnostics(
        expected - 3600, timeframe_minutes=60, now=boundary
    )
    assert exact["candle_close_age_seconds"] == 0
    assert exact["expected_latest_closed_candle"] == expected
    assert exact["stale_state"] is False
    assert stale["market_lag_candles"] == 1
    assert stale["stale_state"] is True


def test_timezone_does_not_change_epoch_diagnostics():
    utc = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    plus_five = utc.astimezone(timezone(timedelta(hours=5)))
    timestamp = int(datetime(2026, 1, 1, 11, tzinfo=timezone.utc).timestamp())
    assert candle_timing_diagnostics(
        timestamp, timeframe_minutes=60, now=utc
    ) == candle_timing_diagnostics(
        timestamp, timeframe_minutes=60, now=plus_five
    )


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
