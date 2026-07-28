from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import PaperStrategyConfig, RuntimeSafetyConfig
from app.execution import ExecutionMode
from app.process_lock import ProcessLock
from app.regime_runtime import RegimeRuntimeStateStore
from app.runtime import Runtime, build_runtime
from app.runtime_health import HealthStatus, run_health_checks


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


if __name__ == "__main__":
    main()
