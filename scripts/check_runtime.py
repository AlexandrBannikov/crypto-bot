from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import PaperStrategyConfig, RuntimeSafetyConfig
from app.execution import ExecutionMode
from app.process_lock import ProcessLock
from app.regime_runtime import RegimeRuntimeStateStore
from app.runtime import Runtime, build_runtime
from app.runtime_health import (
    HealthStatus,
    read_jsonl_safely,
    read_timestamp,
    run_health_checks,
)
from app.equity_history import (
    SCHEMA_VERSION,
    SnapshotStorage,
    load_equity_history_config,
)
from app.account_snapshot import market_from_decisions
from app.trading_controller_store import TradingControllerStateStore
from app.scored_observability import breakdown_from_record


@dataclass(frozen=True, slots=True)
class RuntimeSummary:
    execution_mode: ExecutionMode
    executor_type: str
    uses_exchange: bool
    dry_run: bool
    submits_orders: bool
    testnet: bool | None


def summarize_runtime(runtime: Runtime) -> RuntimeSummary:
    account = runtime.execution.account

    return RuntimeSummary(
        execution_mode=runtime.execution.mode,
        executor_type=type(runtime.executor).__name__,
        uses_exchange=runtime.execution.uses_exchange,
        dry_run=runtime.execution.dry_run,
        submits_orders=runtime.execution.submits_orders,
        testnet=(
            account.testnet
            if account is not None
            else None
        ),
    )


def main() -> None:
    raise SystemExit(run_checks())


def run_checks(*, no_network: bool = False) -> int:
    checks: list[tuple[str, str, str]] = []
    try:
        strategy = PaperStrategyConfig.from_env()
        safety = RuntimeSafetyConfig.from_env()
        runtime = build_runtime()
        summary = summarize_runtime(runtime)
        safe = (
            summary.execution_mode is ExecutionMode.PAPER
            and not summary.submits_orders
            and not summary.uses_exchange
            and not safety.live_trading_enabled
        )
        checks.append(
            (
                "PASS" if safe else "FAIL",
                "execution_config",
                (
                    f"paper-only; regime_filter_mode={strategy.mode.value}"
                    if safe
                    else "runtime could submit or use exchange orders"
                ),
            )
        )
    except Exception as exc:
        checks.append(
            ("FAIL", "execution_config", f"{type(exc).__name__}: {exc}")
        )
        summary = None

    state_path = Path(
        os.environ.get(
            "CONTROLLER_STATE_PATH",
            "state/trading_controller.json",
        )
    )
    operational_path = Path(
        os.environ.get(
            "REGIME_RUNTIME_STATE_PATH",
            "state/regime_runtime.json",
        )
    )
    journal_path = Path(
        os.environ.get(
            "CONTROLLER_TRADE_JOURNAL_PATH",
            "state/controller_trade_journal.jsonl",
        )
    )
    decision_path = Path(
        os.environ.get(
            "SHADOW_DIAGNOSTICS_PATH",
            "state/shadow_decisions.jsonl",
        )
    )
    report_dir = Path(
        os.environ.get("RUNTIME_REPORT_DIR", "reports/runtime")
    )
    lock_path = Path(
        os.environ.get(
            "CONTROLLER_LOCK_PATH",
            "state/bybit_controller.lock",
        )
    )
    candle_path = Path(
        os.environ.get(
            "CONTROLLER_LAST_CANDLE_PATH",
            "state/trading_controller_last_candle.txt",
        )
    )
    scored_state_path = Path(os.environ.get("SCORED_CANDIDATE_STATE_PATH", "state/scored_candidate_shadow/runtime.json"))
    scored_journal_path = Path(os.environ.get("SCORED_CANDIDATE_DECISION_PATH", "state/scored_candidate_shadow/decisions.jsonl"))

    try:
        operational = RegimeRuntimeStateStore(operational_path).load()
        unexplained = operational.active_halt_reason not in {
            None,
            "stale_data",
            "api_error",
            "daily_loss",
            "maximum_drawdown",
        }
        checks.append(
            (
                "FAIL"
                if unexplained
                else "WARN"
                if operational.active_halt_reason
                else "PASS",
                "operational_state",
                f"active_halt_reason={operational.active_halt_reason}",
            )
        )
    except ValueError as exc:
        checks.append(("FAIL", "operational_state", str(exc)))

    checks.extend(check_scored_observability(scored_state_path, scored_journal_path))

    for name, path in (
        ("journal_writable", journal_path.parent),
        ("report_directory", report_dir),
    ):
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".runtime-health-write-probe"
            probe.touch(exist_ok=False)
            probe.unlink()
            checks.append(("PASS", name, f"{path} is writable"))
        except OSError as exc:
            checks.append(("FAIL", name, f"{path}: {exc}"))

    health, _ = run_health_checks(
        state_path=state_path,
        candle_path=candle_path,
        journal_path=journal_path,
        shadow_path=decision_path,
        lock_path=lock_path,
        max_candle_age_minutes=max(
            1, int(
                getattr(
                    locals().get("safety", None),
                    "max_data_age_seconds",
                    5400,
                )
                / 60
            )
        ),
        no_network=no_network,
    )
    for item in health:
        label = {
            HealthStatus.OK: "PASS",
            HealthStatus.WARNING: "WARN",
            HealthStatus.CRITICAL: "FAIL",
        }[item.status]
        if (
            item.name == "last_candle"
            and item.details.get("age_seconds", 0)
            > getattr(
                locals().get("safety", None),
                "max_data_age_seconds",
                5400,
            )
        ):
            label = "FAIL"
        checks.append((label, item.name, item.message))

    history_config = load_equity_history_config(
        PROJECT_ROOT / "config/equity_history.json", root=PROJECT_ROOT
    )
    try:
        history_storage = SnapshotStorage(history_config.database_path)
        version = history_storage.schema_version()
        checks.append(
            (
                "PASS" if version == SCHEMA_VERSION else "WARN"
                if version == 0 else "FAIL",
                "equity_history_db",
                (
                    f"schema version {version}; production/candidate separated"
                    if version else "database not initialized yet"
                ),
            )
        )
        latest_snapshot = history_storage.latest("production")
        if latest_snapshot is None:
            checks.extend(
                [
                    ("WARN", "equity_reconciliation", "no production snapshot yet; statistical history is immature"),
                    ("WARN", "snapshot_freshness", "no production snapshot yet"),
                    ("WARN", "snapshot_market_lag", "no production snapshot yet"),
                ]
            )
        else:
            controller = TradingControllerStateStore(state_path).load()
            decision_rows = (
                read_jsonl_safely(decision_path)[0]
                if decision_path.exists() else []
            )
            market = market_from_decisions(decision_rows)
            price = (
                Decimal(str(market["price"]))
                if market["price"] is not None else None
            )
            expected = controller.virtual_balance + (
                controller.position_quantity * price
                if controller.has_open_position and price is not None
                else Decimal("0")
            )
            difference = abs(expected - latest_snapshot.equity)
            reconciled = difference <= history_config.reconciliation_tolerance
            checks.append(
                (
                    "PASS" if reconciled else "FAIL",
                    "equity_reconciliation",
                    f"difference={difference}",
                )
            )
            local_candle = read_timestamp(candle_path)
            expected_close = local_candle + 3600
            snapshot_close = latest_snapshot.candle_close_timestamp
            lag_seconds = (
                max(0, expected_close - snapshot_close)
                if snapshot_close is not None else None
            )
            fresh = lag_seconds == 0
            checks.append(
                (
                    "PASS" if fresh else "WARN",
                    "snapshot_freshness",
                    (
                        "latest snapshot matches paper state candle"
                        if fresh else f"snapshot lag seconds={lag_seconds}"
                    ),
                )
            )
            checks.append(
                (
                    "PASS" if fresh else "WARN",
                    "snapshot_market_lag",
                    f"lag_candles={lag_seconds / 3600 if lag_seconds is not None else 'N/A'}",
                )
            )
            history_rows = history_storage.query(environment="production")
            invalid_recent = sum(
                item.data_quality_status == "INVALID"
                for item in history_rows[-20:]
            )
            checks.append(
                (
                    "PASS" if invalid_recent == 0 else "FAIL",
                    "equity_history_quality",
                    f"invalid_recent_snapshots={invalid_recent}",
                )
            )
            zone = ZoneInfo(history_config.timezone)
            local_now = datetime.now(timezone.utc).astimezone(zone)
            today = local_now.date().isoformat()
            daily_exists = any(
                item.snapshot_reason == "daily_close"
                and item.source_cycle_id == f"daily:{today}"
                for item in history_rows
            )
            due = (
                local_now.hour,
                local_now.minute,
            ) >= (
                history_config.daily_snapshot_hour,
                history_config.daily_snapshot_minute,
            )
            checks.append(
                (
                    "PASS" if daily_exists or not due else "WARN",
                    "daily_snapshot_status",
                    (
                        f"daily snapshot exists for {today}"
                        if daily_exists
                        else f"daily snapshot not due or unavailable for {today}"
                    ),
                )
            )
    except Exception as exc:
        checks.append(
            ("FAIL", "equity_history_db", f"{type(exc).__name__}: {exc}")
        )

    # Acquiring and releasing the real lock is a read-safe operational test;
    # a held lock is reported by run_health_checks and is not disturbed.
    if not lock_path.exists():
        try:
            with ProcessLock(lock_path):
                pass
            checks.append(("PASS", "lock_operation", "lock acquire/release works"))
        except Exception as exc:
            checks.append(("FAIL", "lock_operation", str(exc)))

    for status, name, message in checks:
        print(f"{status} {name}: {message}")
    print("Ордера не отправлялись; API check uses public market data only.")
    return 1 if any(status == "FAIL" for status, _, _ in checks) else 0


def check_scored_observability(state_path: Path, journal_path: Path, *, now: datetime | None = None) -> list[tuple[str, str, str]]:
    names = ("scored_breakdown", "scored_reconciliation", "scored_thresholds", "scored_allocation", "scored_journal_freshness")
    if not journal_path.exists():
        return [("WARN", name, "scored journal not initialized") for name in names]
    rows, warnings = read_jsonl_safely(journal_path)
    if not rows:
        return [("WARN", name, "scored journal empty or unreadable") for name in names]
    row = rows[-1]
    detail = breakdown_from_record(row)
    if detail is None:
        return [("WARN", name, "legacy record has no score breakdown") for name in names]
    result = [("PASS", "scored_breakdown", f"{len(detail.get('score_components', {}))} components available")]
    consistent = bool(detail.get("score_consistent"))
    result.append(("PASS" if consistent else "WARN", "scored_reconciliation", detail.get("reconciliation_warning") or "component sum matches total"))
    entry, strong = detail.get("entry_threshold"), detail.get("strong_entry_threshold")
    valid_thresholds = isinstance(entry, (int, float)) and (strong is None or isinstance(strong, (int, float)) and entry < strong <= 100)
    result.append(("PASS" if valid_thresholds else "WARN", "scored_thresholds", f"entry={entry}; strong={strong}"))
    allocation = float(detail.get("risk_allocation_pct", 0))
    score = float(detail.get("total_score", 0))
    allocation_ok = allocation >= 0 and not (score < float(entry or 65) and allocation != 0)
    result.append(("PASS" if allocation_ok else "WARN", "scored_allocation", f"decision={detail.get('decision')}; allocation={allocation}%"))
    runtime_candle = None
    try:
        runtime_candle = json.loads(state_path.read_text(encoding="utf-8")).get("last_candle") if state_path.exists() else None
    except (OSError, ValueError, TypeError):
        pass
    candle_matches = runtime_candle is None or int(row.get("candle_timestamp", -1)) == int(runtime_candle)
    age = (now or datetime.now(timezone.utc)).timestamp() - float(row.get("candle_close_timestamp", 0))
    fresh = age <= 3 * 3600
    label = "PASS" if candle_matches and fresh else "WARN"
    message = f"runtime_match={candle_matches}; age_seconds={max(0, int(age))}"
    if warnings:
        message += f"; parse_warnings={len(warnings)}"
    result.append((label, "scored_journal_freshness", message))
    return result


if __name__ == "__main__":
    main()
