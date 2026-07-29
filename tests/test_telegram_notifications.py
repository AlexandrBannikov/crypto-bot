from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from urllib.error import URLError

import pytest

from app.runtime_health import HealthCheckResult, HealthStatus
from app.telegram_config import TelegramConfig
from app.telegram_notifications import (
    NotificationState,
    NotificationStateStore,
    RuntimeSnapshot,
    SystemdUnitStatus,
    TelegramClient,
    TelegramPaths,
    collect_snapshot,
    command_response,
    format_decision,
    format_evening_report,
    format_morning_report,
    format_status,
    format_trades,
    process_update,
    send_transition_alerts,
)


def paths(tmp_path: Path) -> TelegramPaths:
    state = tmp_path / "state"
    state.mkdir()
    return TelegramPaths(
        controller_state=state / "controller.json",
        runtime_state=state / "runtime.json",
        last_candle=state / "last_candle.txt",
        trade_journal=state / "trades.jsonl",
        decision_journal=state / "decisions.jsonl",
        notification_state=state / "telegram.json",
    )


def snapshot(**changes) -> RuntimeSnapshot:
    values = {
        "checked_at": "2026-07-28T04:00:00+00:00",
        "timer_state": "active",
        "service_state": "inactive",
        "execution_mode": "PAPER",
        "filter_mode": "shadow",
        "live_trading_enabled": False,
        "balance": "1000",
        "position": "FLAT",
        "position_quantity": "0",
        "last_candle": 1785207600,
        "candle_age_seconds": 1800.0,
        "market_lag_candles": 0.0,
        "api_status": "OK",
        "health_status": "OK",
        "active_halt_reason": None,
        "counters": {
            "signals_total": 2,
            "entries_allowed": 1,
            "entries_blocked": 0,
            "shadow_would_block": 1,
            "api_error_halts": 0,
            "stale_data_rejections": 0,
            "risk_limit_halts": 0,
        },
    }
    values.update(changes)
    return RuntimeSnapshot(**values)


def health(status: HealthStatus = HealthStatus.OK):
    return [
        HealthCheckResult(
            "bybit_api",
            status,
            "api",
            {},
            "2026-07-28T04:00:00+00:00",
        ),
        HealthCheckResult(
            "last_candle",
            status,
            "candle",
            {},
            "2026-07-28T04:00:00+00:00",
        ),
    ]


def write_decision(path: Path, *, timestamp: int = 1785207600) -> None:
    path.write_text(
        json.dumps(
            {
                "candle_timestamp": timestamp,
                "regime": "RANGE",
                "baseline_signal": "open_long",
                "execution_signal": "open_long",
                "filter_mode": "shadow",
                "blocked": True,
                "blocked_reason": "range",
                "shadow_would_block": True,
                "shadow_block_reason": "range",
                "baseline_trade_executed": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_format_morning_report(tmp_path) -> None:
    runtime_paths = paths(tmp_path)
    write_decision(runtime_paths.decision_journal)

    report = format_morning_report(
        snapshot(),
        runtime_paths,
        now=datetime(2026, 7, 28, 4, 0, tzinfo=timezone.utc),
    )

    assert "Утренний отчёт" in report
    assert "Реальная торговля: выключена" in report
    assert "REGIME_FILTER_MODE: shadow" in report
    assert "Shadow would block: 1" in report


def test_format_evening_report(tmp_path) -> None:
    runtime_paths = paths(tmp_path)
    runtime_paths.runtime_state.write_text(
        json.dumps(
            {
                "daily_starting_balance": "1000",
                "counters": {},
            }
        ),
        encoding="utf-8",
    )
    write_decision(runtime_paths.decision_journal)

    report = format_evening_report(
        snapshot(balance="1010"),
        runtime_paths,
        now=datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc),
    )

    assert "Вечерний отчёт" in report
    assert "Beginning/ending balance: 1000/1010" in report
    assert "Доходность: 1.00%" in report
    assert "Открытая позиция: FLAT" in report


def test_status_contains_safe_runtime_state() -> None:
    text = format_status(snapshot())

    assert "Runtime: PAPER" in text
    assert "Regime filter: shadow" in text
    assert "Реальная торговля: выключена" in text
    assert "Bybit API: OK" in text


def test_missing_trade_journal_has_clear_message(tmp_path) -> None:
    assert "сделок ещё не было" in format_trades(paths(tmp_path))


def test_last_decision_record(tmp_path) -> None:
    runtime_paths = paths(tmp_path)
    write_decision(runtime_paths.decision_journal)

    text = format_decision(runtime_paths)

    assert "Режим рынка: RANGE" in text
    assert "Baseline signal: open_long" in text
    assert "Regime filter would block: yes" in text
    assert "Baseline trade executed: yes" in text


def test_command_status_is_read_only(tmp_path) -> None:
    runtime_paths = paths(tmp_path)
    runtime_paths.controller_state.write_text("immutable", encoding="utf-8")
    before = hashlib.sha256(
        runtime_paths.controller_state.read_bytes()
    ).hexdigest()

    response = command_response("/status", snapshot(), runtime_paths)

    after = hashlib.sha256(
        runtime_paths.controller_state.read_bytes()
    ).hexdigest()
    assert "Crypto-bot status" in response
    assert after == before


def test_foreign_chat_id_is_ignored_without_content_logging(
    caplog,
) -> None:
    caplog.set_level(logging.WARNING)
    sent = []

    handled = process_update(
        {
            "message": {
                "chat": {"id": 999},
                "text": "/status secret message",
            }
        },
        allowed_chat_id="123",
        responder=lambda _: "response",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )

    assert handled is False
    assert sent == []
    assert "chat_id=999" in caplog.text
    assert "secret message" not in caplog.text


def test_missing_token_is_rejected_only_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("CRYPTO_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("CRYPTO_TELEGRAM_CHAT_ID", "123")
    monkeypatch.delenv("CRYPTO_TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="BOT_TOKEN is required"):
        TelegramConfig.from_env()


def test_telegram_timeout_is_bounded_and_token_not_in_error_or_logs(
    caplog,
) -> None:
    token = "super-secret-token"

    def failing(*args, **kwargs):
        raise URLError(f"timeout at bot{token}")

    client = TelegramClient(token, retries=0, opener=failing)
    with pytest.raises(RuntimeError) as caught:
        client.send_message("123", "hello")

    assert token not in str(caught.value)
    assert token not in caplog.text


def test_identical_unhealthy_state_is_deduplicated(tmp_path) -> None:
    store = NotificationStateStore(paths(tmp_path).notification_state)
    store.save(
        NotificationState(
            health_state="unhealthy",
            api_unavailable=True,
            stale_data=True,
        )
    )
    sent = []

    count = send_transition_alerts(
        store,
        snapshot(health_status="CRITICAL", api_status="CRITICAL"),
        health(HealthStatus.CRITICAL),
        sent.append,
        cycle_failed=False,
    )

    assert count == 0
    assert sent == []


def test_recovery_notification_is_sent_once(tmp_path) -> None:
    store = NotificationStateStore(paths(tmp_path).notification_state)
    store.save(NotificationState(health_state="unhealthy"))
    sent = []

    count = send_transition_alerts(
        store,
        snapshot(),
        health(),
        sent.append,
        cycle_failed=False,
    )

    assert count == 1
    assert "восстановился" in sent[0]
    assert (
        send_transition_alerts(
            store,
            snapshot(),
            health(),
            sent.append,
            cycle_failed=False,
        )
        == 0
    )


def test_notification_state_is_separate_from_trading_state(
    tmp_path,
) -> None:
    runtime_paths = paths(tmp_path)
    runtime_paths.runtime_state.write_text(
        json.dumps({"sentinel": True}), encoding="utf-8"
    )
    before = runtime_paths.runtime_state.read_bytes()
    store = NotificationStateStore(runtime_paths.notification_state)

    send_transition_alerts(
        store,
        snapshot(),
        health(),
        lambda _: None,
        cycle_failed=False,
    )

    assert runtime_paths.runtime_state.read_bytes() == before
    assert runtime_paths.notification_state.exists()


def test_unexpected_live_enabled_is_visible_for_critical_alert(
    tmp_path, monkeypatch
) -> None:
    runtime_paths = paths(tmp_path)
    runtime_paths.controller_state.write_text(
        json.dumps({"virtual_balance": "1000"}), encoding="utf-8"
    )
    runtime_paths.runtime_state.write_text(
        json.dumps({"counters": {}}), encoding="utf-8"
    )
    runtime_paths.last_candle.write_text("1785207600", encoding="utf-8")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("REGIME_FILTER_MODE", "shadow")

    current = datetime.fromtimestamp(1785208000, timezone.utc)
    observed, checks = collect_snapshot(
        runtime_paths,
        no_network=True,
        now=current,
        systemd_state=lambda _: "active",
    )
    store = NotificationStateStore(runtime_paths.notification_state)
    sent = []

    send_transition_alerts(
        store,
        observed,
        checks,
        sent.append,
        cycle_failed=False,
        now=current,
    )

    assert observed.live_trading_enabled is True
    assert all(item.name != "controller_lock" for item in checks)
    assert any("LIVE_TRADING_ENABLED" in item for item in sent)


def test_collect_snapshot_allows_candle_staleness_grace(
    tmp_path, monkeypatch
) -> None:
    runtime_paths = paths(tmp_path)
    runtime_paths.controller_state.write_text(
        json.dumps({"virtual_balance": "1000"}), encoding="utf-8"
    )
    runtime_paths.runtime_state.write_text(
        json.dumps({"counters": {}}), encoding="utf-8"
    )
    current = datetime(2026, 7, 28, 4, 0, tzinfo=timezone.utc)
    runtime_paths.last_candle.write_text(
        str(int(current.timestamp()) - 1950), encoding="utf-8"
    )
    monkeypatch.setenv("MAX_DATA_AGE_SECONDS", "1800")

    observed, checks = collect_snapshot(
        runtime_paths,
        no_network=True,
        now=current,
        systemd_state=lambda _: "active",
        stale_grace_seconds=300,
        stale_recheck_seconds=0,
    )

    candle = next(item for item in checks if item.name == "last_candle")
    assert candle.status is HealthStatus.OK
    assert observed.candle_age_seconds == 1950


def test_collect_snapshot_treats_unavailable_systemd_as_warning(
    tmp_path,
) -> None:
    runtime_paths = paths(tmp_path)
    current = datetime(2026, 7, 28, 4, 0, tzinfo=timezone.utc)
    runtime_paths.controller_state.write_text(
        json.dumps({"virtual_balance": "1000"}), encoding="utf-8"
    )
    runtime_paths.last_candle.write_text(
        str(int(current.timestamp())), encoding="utf-8"
    )

    observed, checks = collect_snapshot(
        runtime_paths,
        no_network=True,
        now=current,
        systemd_probe=lambda unit: SystemdUnitStatus(
            unit,
            False,
            "status unavailable",
            detail="permission denied",
        ),
        stale_recheck_seconds=0,
    )

    monitoring = next(
        item for item in checks if item.name == "systemd_monitoring"
    )
    assert monitoring.status is HealthStatus.WARNING
    assert observed.health_status == HealthStatus.WARNING.name
    assert observed.systemd_monitoring_detail is not None
    assert all(item.name != "paper_timer" for item in checks)


def test_collect_snapshot_reports_confirmed_service_failure(
    tmp_path,
) -> None:
    runtime_paths = paths(tmp_path)
    current = datetime(2026, 7, 28, 4, 0, tzinfo=timezone.utc)
    runtime_paths.controller_state.write_text(
        json.dumps({"virtual_balance": "1000"}), encoding="utf-8"
    )
    runtime_paths.last_candle.write_text(
        str(int(current.timestamp())), encoding="utf-8"
    )

    def probe(unit: str) -> SystemdUnitStatus:
        if unit.endswith(".timer"):
            return SystemdUnitStatus(unit, True, "active")
        return SystemdUnitStatus(
            unit,
            True,
            "failed",
            result="exit-code",
            exec_main_status=1,
        )

    observed, checks = collect_snapshot(
        runtime_paths,
        no_network=True,
        now=current,
        systemd_probe=probe,
        stale_recheck_seconds=0,
    )

    service = next(item for item in checks if item.name == "paper_service")
    assert service.status is HealthStatus.CRITICAL
    assert observed.health_status == HealthStatus.CRITICAL.name


def test_telegram_paths_follow_isolated_environment(tmp_path, monkeypatch):
    production = Path("/opt/crypto-bot/state")
    isolated = tmp_path / "isolated"
    monkeypatch.setenv(
        "REGIME_RUNTIME_STATE_PATH", str(isolated / "runtime.json")
    )
    monkeypatch.setenv(
        "TELEGRAM_NOTIFICATION_STATE_PATH",
        str(isolated / "notifications.json"),
    )

    configured = TelegramPaths.from_env()

    assert configured.runtime_state.is_relative_to(isolated)
    assert configured.notification_state.is_relative_to(isolated)
    assert not configured.runtime_state.is_relative_to(production)
