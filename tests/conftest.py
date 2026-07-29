from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = tuple(
    PROJECT_ROOT / name for name in ("state", "logs", "reports")
)


def _artifact_snapshot() -> dict[str, tuple]:
    snapshot: dict[str, tuple] = {}
    for root in PRODUCTION_ROOTS:
        if not root.exists():
            snapshot[str(root)] = (False,)
            continue
        for path in sorted((root, *root.rglob("*"))):
            stat = path.lstat()
            relative = str(path.relative_to(PROJECT_ROOT))
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                digest = None
            snapshot[relative] = (
                stat.st_mode,
                stat.st_uid,
                stat.st_gid,
                stat.st_size,
                stat.st_mtime_ns,
                digest,
            )
    return snapshot


@pytest.fixture(scope="session", autouse=True)
def production_artifacts_are_immutable():
    """Fail the suite if any production runtime artifact changes."""
    before = _artifact_snapshot()
    yield
    after = _artifact_snapshot()
    assert after == before, (
        "pytest modified production state/logs/reports; "
        "all runtime artifacts must use tmp_path"
    )


@pytest.fixture(autouse=True)
def isolated_runtime_artifacts(tmp_path: Path, monkeypatch):
    """Redirect every runtime default that can write to a per-test sandbox."""
    root = tmp_path / "runtime-artifacts"
    state = root / "state"
    reports = root / "reports"
    logs = root / "logs"
    paths = {
        "CONTROLLER_STATE_PATH": state / "trading_controller.json",
        "CONTROLLER_LAST_CANDLE_PATH": (
            state / "trading_controller_last_candle.txt"
        ),
        "REGIME_RUNTIME_STATE_PATH": state / "regime_runtime.json",
        "CONTROLLER_TRADE_JOURNAL_PATH": (
            state / "controller_trade_journal.jsonl"
        ),
        "SHADOW_DIAGNOSTICS_PATH": state / "shadow_decisions.jsonl",
        "CONTROLLER_LOCK_PATH": state / "bybit_controller.lock",
        "CONTROLLER_STATISTICS_REPORT_PATH": (
            reports / "trade_statistics.txt"
        ),
        "CONTROLLER_STATISTICS_PLOT_PATH": (
            reports / "trade_statistics.png"
        ),
        "RUNTIME_REPORT_DIR": reports / "runtime",
        "PAPER_TRADE_LOG_PATH": logs / "paper_trades.csv",
        "EQUITY_HISTORY_DB_PATH": state / "equity_history.db",
        "TELEGRAM_NOTIFICATION_STATE_PATH": (
            state / "telegram_notifications.json"
        ),
    }
    for name, path in paths.items():
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    monkeypatch.setenv("CRYPTO_TELEGRAM_ENABLED", "false")
    monkeypatch.delenv("CRYPTO_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CRYPTO_TELEGRAM_CHAT_ID", raising=False)

    # The controller module is imported during collection, before fixtures can
    # set the environment, so patch its resolved module constants as well.
    from scripts import run_bybit_controller as controller

    monkeypatch.setattr(controller, "STATE_PATH", paths["CONTROLLER_STATE_PATH"])
    monkeypatch.setattr(
        controller,
        "LAST_CANDLE_PATH",
        paths["CONTROLLER_LAST_CANDLE_PATH"],
    )
    monkeypatch.setattr(
        controller,
        "RUNTIME_STATE_PATH",
        paths["REGIME_RUNTIME_STATE_PATH"],
    )
    monkeypatch.setattr(
        controller,
        "JOURNAL_PATH",
        paths["CONTROLLER_TRADE_JOURNAL_PATH"],
    )
    monkeypatch.setattr(
        controller,
        "DEFAULT_LOCK_PATH",
        paths["CONTROLLER_LOCK_PATH"],
    )
    monkeypatch.setattr(
        controller,
        "DEFAULT_STATISTICS_REPORT_PATH",
        paths["CONTROLLER_STATISTICS_REPORT_PATH"],
    )
    monkeypatch.setattr(
        controller,
        "DEFAULT_STATISTICS_PLOT_PATH",
        paths["CONTROLLER_STATISTICS_PLOT_PATH"],
    )
    yield root
