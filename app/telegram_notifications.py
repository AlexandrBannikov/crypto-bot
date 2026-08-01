from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.account_snapshot import (
    AccountSnapshot,
    calculate_account_snapshot,
    format_position_age,
    market_from_decisions,
)
from app.config import PaperStrategyConfig, RuntimeSafetyConfig
from app.regime_runtime import RegimeRuntimeStateStore
from app.runtime_health import (
    HealthCheckResult,
    HealthStatus,
    overall_status,
    read_jsonl_safely,
    run_health_checks,
)
from app.telegram_config import TelegramConfig
from app.trade_journal import TradeJournalEntry
from app.trading_controller_store import TradingControllerStateStore


LOGGER = logging.getLogger(__name__)
SYSTEMCTL = "/usr/bin/systemctl"
STALE_GRACE_SECONDS = 300
STALE_RECHECK_SECONDS = 5


@dataclass(frozen=True, slots=True)
class TelegramPaths:
    controller_state: Path
    runtime_state: Path
    last_candle: Path
    trade_journal: Path
    decision_journal: Path
    notification_state: Path
    candidate_state: Path = Path("state/bybit_candidate_controller.json")
    candidate_trade_journal: Path = Path("state/bybit_candidate_trades.jsonl")
    candidate_decision_journal: Path = Path("state/bybit_candidate_decisions.jsonl")
    candidate_runtime_summary: Path = Path("state/bybit_candidate_runtime.json")

    @classmethod
    def from_env(
        cls, *, notification_state: Path | None = None
    ) -> "TelegramPaths":
        return cls(
            controller_state=Path(
                os.environ.get(
                    "CONTROLLER_STATE_PATH",
                    "state/trading_controller.json",
                )
            ),
            runtime_state=Path(
                os.environ.get(
                    "REGIME_RUNTIME_STATE_PATH",
                    "state/regime_runtime.json",
                )
            ),
            last_candle=Path(
                os.environ.get(
                    "CONTROLLER_LAST_CANDLE_PATH",
                    "state/trading_controller_last_candle.txt",
                )
            ),
            trade_journal=Path(
                os.environ.get(
                    "CONTROLLER_TRADE_JOURNAL_PATH",
                    "state/controller_trade_journal.jsonl",
                )
            ),
            decision_journal=Path(
                os.environ.get(
                    "SHADOW_DIAGNOSTICS_PATH",
                    "state/shadow_decisions.jsonl",
                )
            ),
            notification_state=notification_state
            or Path(
                os.environ.get(
                    "TELEGRAM_NOTIFICATION_STATE_PATH",
                    "state/telegram_notifications.json",
                )
            ),
            candidate_state=Path(
                os.environ.get(
                    "CANDIDATE_STATE_PATH",
                    "state/bybit_candidate_controller.json",
                )
            ),
            candidate_trade_journal=Path(
                os.environ.get(
                    "CANDIDATE_TRADE_JOURNAL_PATH",
                    "state/bybit_candidate_trades.jsonl",
                )
            ),
            candidate_decision_journal=Path(
                os.environ.get(
                    "CANDIDATE_DECISION_JOURNAL_PATH",
                    "state/bybit_candidate_decisions.jsonl",
                )
            ),
            candidate_runtime_summary=Path(
                os.environ.get(
                    "CANDIDATE_RUNTIME_SUMMARY_PATH",
                    "state/bybit_candidate_runtime.json",
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    checked_at: str
    timer_state: str
    service_state: str
    execution_mode: str
    filter_mode: str
    live_trading_enabled: bool
    balance: str
    position: str
    position_quantity: str
    last_candle: int | None
    candle_age_seconds: float | None
    market_lag_candles: float | None
    api_status: str
    health_status: str
    active_halt_reason: str | None
    counters: dict[str, int]
    systemd_monitoring_detail: str | None = None
    health_reasons: tuple[str, ...] = ()
    component_statuses: dict[str, str] = field(default_factory=dict)
    candle_close_age_seconds: float | None = None
    scored_candidate_enabled: bool = False
    scored_candidate_mode: str = "shadow"
    score_model_version: str | None = None
    risk_model_version: str | None = None
    last_scored_candle: int | None = None
    last_signal_score: float | None = None
    last_scored_decision: str | None = None
    scored_hard_block_count: int = 0


@dataclass(frozen=True, slots=True)
class SystemdUnitStatus:
    unit: str
    available: bool
    active_state: str
    sub_state: str | None = None
    result: str | None = None
    exec_main_status: int | None = None
    detail: str | None = None


@dataclass(slots=True)
class NotificationState:
    version: int = 1
    health_state: str | None = None
    active_halt_reason: str | None = None
    api_unavailable: bool = False
    stale_data: bool = False
    cycle_failed: bool = False
    unsafe_live: bool = False
    last_sent_at: dict[str, str] = field(default_factory=dict)
    update_offset: int = 0


class NotificationStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> NotificationState:
        if not self.path.exists():
            return NotificationState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return NotificationState(**payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"notification state is invalid: {type(exc).__name__}"
            ) from exc

    def save(self, state: NotificationState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    asdict(state), handle, ensure_ascii=False, indent=2
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        timeout: float = 10.0,
        retries: int = 2,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not token:
            raise ValueError("Telegram bot token is required")
        self._token = token
        self.timeout = timeout
        self.retries = retries
        self._opener = opener

    def call(self, method: str, payload: dict[str, Any]) -> Any:
        encoded = urlencode(payload).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{self._token}/{method}",
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        for attempt in range(self.retries + 1):
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                if not result.get("ok"):
                    raise RuntimeError("Telegram API rejected the request")
                return result.get("result")
            except (
                HTTPError,
                URLError,
                TimeoutError,
                OSError,
                json.JSONDecodeError,
            ) as exc:
                if attempt >= self.retries:
                    raise RuntimeError(
                        f"Telegram request failed: {type(exc).__name__}"
                    ) from None
                time.sleep(min(0.5 * (attempt + 1), 1.0))

    def send_message(self, chat_id: str, text: str) -> None:
        for chunk in telegram_chunks(text):
            self.call(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": "true",
                },
            )


def _systemd_unit_status(unit: str) -> SystemdUnitStatus:
    properties = [
        "ActiveState",
        "SubState",
        "Result",
        "LastTriggerUSec",
        "NextElapseUSecRealtime",
    ]
    if unit.endswith(".service"):
        properties.append("ExecMainStatus")
    try:
        active = subprocess.run(
            [SYSTEMCTL, "is-active", unit],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        shown = subprocess.run(
            [
                SYSTEMCTL,
                "show",
                unit,
                f"--property={','.join(properties)}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired as exc:
        return SystemdUnitStatus(unit, False, "status unavailable", detail="timeout while querying systemd")
    except (OSError, subprocess.SubprocessError) as exc:
        return SystemdUnitStatus(
            unit,
            False,
            "status unavailable",
            detail=f"{type(exc).__name__}: {exc}",
        )

    if shown.returncode != 0:
        detail = shown.stderr.strip() or active.stderr.strip()
        lowered = detail.lower()
        if "not found" in lowered or "could not be found" in lowered:
            diagnostic = "unit not found"
        elif "permission" in lowered or "operation not permitted" in lowered or "failed to connect to bus" in lowered:
            diagnostic = "no access to systemd"
        else:
            diagnostic = f"systemctl command failed (exit {shown.returncode})"
        return SystemdUnitStatus(
            unit,
            False,
            "status unavailable",
            detail=(
                f"{diagnostic}: {detail or 'no diagnostic output'}"
            ),
        )

    values = {}
    for line in shown.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    state = values.get("ActiveState") or active.stdout.strip()
    if not state:
        return SystemdUnitStatus(
            unit,
            False,
            "status unavailable",
            detail=(
                f"systemctl is-active exit {active.returncode}; "
                "systemctl show returned no ActiveState"
            ),
        )
    raw_status = values.get("ExecMainStatus")
    try:
        exec_main_status = int(raw_status) if raw_status else None
    except ValueError:
        exec_main_status = None
    return SystemdUnitStatus(
        unit,
        True,
        state,
        sub_state=values.get("SubState") or None,
        result=values.get("Result") or None,
        exec_main_status=exec_main_status,
    )


def _cycle_failed() -> bool:
    status = _systemd_unit_status("crypto-paper.service")
    if not status.available:
        return False
    return (
        status.result not in {None, "", "success"}
        or status.exec_main_status not in {None, 0}
    )


def _compat_systemd_status(unit: str, value: str) -> SystemdUnitStatus:
    unavailable = value.startswith(("unknown", "status unavailable"))
    return SystemdUnitStatus(
        unit,
        not unavailable,
        "status unavailable" if unavailable else value,
        detail=value if unavailable else None,
    )


def collect_snapshot(
    paths: TelegramPaths,
    *,
    no_network: bool = False,
    now: datetime | None = None,
    systemd_state: Callable[[str], str] | None = None,
    systemd_probe: Callable[[str], SystemdUnitStatus] = _systemd_unit_status,
    market_fetcher: Callable[[], int] | None = None,
    stale_grace_seconds: int = STALE_GRACE_SECONDS,
    stale_recheck_seconds: int = STALE_RECHECK_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[RuntimeSnapshot, list[HealthCheckResult]]:
    current = now or datetime.now(timezone.utc)
    strategy = PaperStrategyConfig.from_env()
    live_raw = os.environ.get("LIVE_TRADING_ENABLED", "false")
    normalized_live = live_raw.strip().lower()
    if normalized_live not in {
        "1",
        "true",
        "yes",
        "on",
        "0",
        "false",
        "no",
        "off",
    }:
        raise ValueError("LIVE_TRADING_ENABLED must be a boolean")
    live_enabled = normalized_live in {"1", "true", "yes", "on"}
    if live_enabled:
        max_data_age_seconds = int(
            os.environ.get("MAX_DATA_AGE_SECONDS", "5400")
        )
        if max_data_age_seconds <= 0:
            raise ValueError("MAX_DATA_AGE_SECONDS must be positive")
    else:
        max_data_age_seconds = (
            RuntimeSafetyConfig.from_env().max_data_age_seconds
        )
    controller = TradingControllerStateStore(paths.controller_state).load()
    runtime = RegimeRuntimeStateStore(paths.runtime_state).load()
    if stale_grace_seconds < 0 or stale_recheck_seconds < 0:
        raise ValueError("stale grace and recheck must not be negative")

    def runtime_checks(
        checked_at: datetime,
    ) -> tuple[list[HealthCheckResult], dict[str, Any]]:
        return run_health_checks(
            state_path=paths.controller_state,
            candle_path=paths.last_candle,
            journal_path=paths.trade_journal,
            shadow_path=paths.decision_journal,
            # The Telegram contour does not need controller lock metadata.
            # Avoid granting its DynamicUser access to this writable lock.
            lock_path=None,
            inspect_lock=False,
            # Telegram applies the paper-specific threshold and grace below.
            max_candle_age_minutes=1_000_000,
            no_network=no_network,
            now=checked_at,
            market_fetcher=market_fetcher,
        )

    checks, context = runtime_checks(current)
    last_candle = context.get("last_candle")
    open_age = (
        max(0.0, current.timestamp() - last_candle)
        if last_candle is not None else None
    )
    age = (
        max(0.0, current.timestamp() - last_candle - 3600)
        if last_candle is not None
        else None
    )
    warning_age_minutes = int(os.environ.get(
        "MARKET_DATA_WARNING_AGE_MINUTES", str(max_data_age_seconds // 60)
    ))
    critical_age_minutes = int(os.environ.get(
        "MARKET_DATA_CRITICAL_AGE_MINUTES", str(max(2, max_data_age_seconds // 60 * 2))
    ))
    stale_after = warning_age_minutes * 60 + stale_grace_seconds
    if (
        age is not None
        and age > stale_after
        and stale_recheck_seconds
    ):
        sleeper(stale_recheck_seconds)
        rechecked_at = (
            current + timedelta(seconds=stale_recheck_seconds)
            if now is not None
            else datetime.now(timezone.utc)
        )
        rechecked_timestamp = read_timestamp(paths.last_candle)
        if rechecked_timestamp != last_candle:
            current = rechecked_at
            checks, context = runtime_checks(current)
            last_candle = context.get("last_candle")
            open_age = (
                max(0.0, current.timestamp() - last_candle)
                if last_candle is not None else None
            )
            age = (
                max(0.0, current.timestamp() - last_candle - 3600)
                if last_candle is not None
                else None
            )
    if age is not None:
        stale = age > stale_after
        checks = [
            (
                HealthCheckResult(
                    item.name,
                    HealthStatus.CRITICAL if stale else HealthStatus.OK,
                    (
                        "last candle close exceeds maximum age plus grace "
                        f"({age / 60:.1f} minutes)"
                        if stale
                        else f"last candle close age is {age / 60:.1f} minutes"
                    ),
                    {
                        **item.details,
                        "age_seconds": age,
                        "max_age_seconds": warning_age_minutes * 60,
                        "critical_age_seconds": critical_age_minutes * 60,
                        "grace_seconds": stale_grace_seconds,
                    },
                    item.checked_at,
                )
                if item.name == "last_candle"
                else item
            )
            for item in checks
        ]

    if systemd_state is None:
        timer_status = systemd_probe("crypto-paper.timer")
        service_status = systemd_probe("crypto-paper.service")
    else:
        timer_status = _compat_systemd_status(
            "crypto-paper.timer",
            systemd_state("crypto-paper.timer"),
        )
        service_status = _compat_systemd_status(
            "crypto-paper.service",
            systemd_state("crypto-paper.service"),
        )

    systemd_details = [
        f"{status.unit}: {status.detail}"
        for status in (timer_status, service_status)
        if not status.available
    ]
    checked = current.isoformat()
    if systemd_details:
        checks.append(
            HealthCheckResult(
                "systemd_monitoring",
                HealthStatus.WARNING,
                "systemd status unavailable; runtime heartbeat is authoritative",
                {"diagnostics": systemd_details},
                checked,
            )
        )
    elif timer_status.active_state != "active":
        checks.append(
            HealthCheckResult(
                "paper_timer",
                HealthStatus.CRITICAL,
                f"paper timer is {timer_status.active_state}",
                {"unit": timer_status.unit},
                checked,
            )
        )
    else:
        checks.append(
            HealthCheckResult(
                "paper_timer",
                HealthStatus.OK,
                "paper timer is active",
                {"unit": timer_status.unit},
                checked,
            )
        )
    if service_status.available:
        failed_service = (
            service_status.result not in {None, "", "success"}
            or service_status.exec_main_status not in {None, 0}
        )
        checks.append(
            HealthCheckResult(
                "paper_service",
                HealthStatus.CRITICAL if failed_service else HealthStatus.OK,
                (
                    "paper service has a confirmed failed result"
                    if failed_service
                    else f"paper service is {service_status.active_state}"
                ),
                {
                    "unit": service_status.unit,
                    "result": service_status.result,
                    "exec_main_status": service_status.exec_main_status,
                },
                checked,
            )
        )
    if runtime.active_halt_reason:
        checks.append(
            HealthCheckResult(
                "active_halt",
                HealthStatus.CRITICAL,
                f"runtime halt is active: {runtime.active_halt_reason}",
                {"reason": runtime.active_halt_reason},
                checked,
            )
        )
    check_map = {item.name: item for item in checks}
    lag = check_map.get("market_lag")
    api = check_map.get("bybit_api")
    position = "LONG" if controller.has_open_position else "FLAT"
    component_statuses = {
        "API": api.status.name if api else "UNKNOWN",
        "Market data": check_map.get("last_candle", HealthCheckResult("x", HealthStatus.WARNING, "", {}, checked)).status.name,
        "Paper state": check_map.get("controller_state", HealthCheckResult("x", HealthStatus.ERROR if hasattr(HealthStatus, "ERROR") else HealthStatus.CRITICAL, "", {}, checked)).status.name,
        "Risk control": check_map.get("active_halt", HealthCheckResult("x", HealthStatus.OK, "", {}, checked)).status.name,
        "Timer": "UNKNOWN" if not timer_status.available else ("OK" if timer_status.active_state == "active" else timer_status.active_state.upper()),
        "Service": "UNKNOWN" if not service_status.available else ("OK" if service_status.active_state in {"active", "inactive"} else service_status.active_state.upper()),
        "Equity history": "OK",
        "Candidate": "OK",
    }
    reasons = tuple(item.message for item in checks if item.status != HealthStatus.OK)
    snapshot = RuntimeSnapshot(
        checked_at=current.isoformat(),
        timer_state=timer_status.active_state,
        service_state=service_status.active_state,
        execution_mode="PAPER",
        filter_mode=strategy.mode.value,
        live_trading_enabled=live_enabled,
        balance=str(controller.virtual_balance),
        position=position,
        position_quantity=str(controller.position_quantity),
        last_candle=last_candle,
        candle_age_seconds=open_age,
        market_lag_candles=(
            float(lag.details["lag_candles"]) if lag else None
        ),
        api_status=api.status.name if api else "UNKNOWN",
        health_status=overall_status(checks).name,
        active_halt_reason=runtime.active_halt_reason,
        counters=asdict(runtime.counters),
        systemd_monitoring_detail=(
            "; ".join(systemd_details) if systemd_details else None
        ),
        health_reasons=reasons,
        component_statuses=component_statuses,
        candle_close_age_seconds=age,
        scored_candidate_enabled=Path(os.environ.get("SCORED_CANDIDATE_DECISION_PATH", "state/scored_candidate_shadow/decisions.jsonl")).exists(),
    )
    return snapshot, checks


def _age(value: float | None) -> str:
    return "unknown" if value is None else f"{value / 60:.1f} min"


def format_status(snapshot: RuntimeSnapshot) -> str:
    counters = snapshot.counters
    lines = [
        "Crypto-bot status",
        f"Runtime: {snapshot.execution_mode}",
        f"Regime filter: {snapshot.filter_mode}",
        (
            "Реальная торговля: включена — ОПАСНО"
            if snapshot.live_trading_enabled
            else "Реальная торговля: выключена"
        ),
        f"Timer: {snapshot.timer_state}",
        f"Service: {snapshot.service_state}",
        f"Health: {snapshot.health_status}",
        f"Bybit API: {snapshot.api_status}",
        f"Balance: {snapshot.balance}",
        f"Position: {snapshot.position} ({snapshot.position_quantity})",
        f"Last candle: {snapshot.last_candle}",
        f"Candle age: {_age(snapshot.candle_age_seconds)}",
        f"Market lag: {snapshot.market_lag_candles if snapshot.market_lag_candles is not None else 'unknown'} candles",
        f"Signals: {counters.get('signals_total', 0)}",
        f"Entries allowed: {counters.get('entries_allowed', 0)}",
        f"Entries blocked: {counters.get('entries_blocked', 0)}",
        f"Shadow would block: {counters.get('shadow_would_block', 0)}",
        f"API errors: {counters.get('api_error_halts', 0)}",
        f"Stale-data events: {counters.get('stale_data_rejections', 0)}",
        f"Risk halts: {counters.get('risk_limit_halts', 0)}",
        f"Active halt: {snapshot.active_halt_reason or 'none'}",
    ]
    return "\n".join(lines)


def _period_records(
    path: Path, start: datetime, end: datetime, timestamp_key: str
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records, _ = read_jsonl_safely(path)
    selected = []
    for record in records:
        raw = record.get(timestamp_key)
        timestamp = (
            datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if isinstance(raw, str)
            else datetime.fromtimestamp(int(raw), timezone.utc)
        )
        if start <= timestamp < end:
            selected.append(record)
    return selected


def _report_period(
    paths: TelegramPaths, start: datetime, end: datetime
) -> dict[str, Any]:
    decisions = _period_records(
        paths.decision_journal, start, end, "candle_timestamp"
    )
    trades = _period_records(paths.trade_journal, start, end, "closed_at")
    entries = sum(
        record.get("baseline_signal") in {"open_long", "open_short"}
        for record in decisions
    )
    exits = sum(
        record.get("baseline_signal") in {"close_long", "close_short"}
        for record in decisions
    )
    from collections import Counter
    reason_counts = Counter()
    for record in decisions:
        action = str(record.get("baseline_signal") or record.get("execution_signal") or "").lower()
        if record.get("position_before") in {"LONG", "SHORT"} and action in {"open_long", "open_short"}:
            key = "hold_existing_position"
        elif record.get("blocked") or record.get("shadow_would_block"):
            key = "regime_filter_block"
        elif action in {"close_long", "close_short"}:
            key = "exit_signal"
        elif action in {"open_long", "open_short"}:
            key = "entry_signal"
        else:
            key = "no_entry_signal"
        reason_counts[key] += 1
    return {
        "signals": len(decisions),
        "entries": entries,
        "exits": exits,
        "trades": len(trades),
        "fees": str(
            sum(
                (Decimal(str(record.get("total_fee", "0"))) for record in trades),
                Decimal("0"),
            )
        ),
        "pnl": str(
            sum(
                (Decimal(str(record.get("net_pnl", "0"))) for record in trades),
                Decimal("0"),
            )
        ),
        "shadow_would_block": sum(
            bool(record.get("shadow_would_block")) for record in decisions
        ),
        "decision_reasons": dict(reason_counts),
    }


def format_morning_report(
    snapshot: RuntimeSnapshot,
    paths: TelegramPaths,
    *,
    now: datetime | None = None,
    timezone_name: str = "Asia/Yekaterinburg",
) -> str:
    zone = ZoneInfo(timezone_name)
    current = (now or datetime.now(timezone.utc)).astimezone(zone)
    start = current.replace(hour=21, minute=0, second=0, microsecond=0)
    if start >= current:
        start -= timedelta(days=1)
    period = _report_period(paths, start, current)
    c = snapshot.counters
    reasons = list(snapshot.health_reasons)
    try:
        production_state = TradingControllerStateStore(paths.controller_state).load()
        rows = read_jsonl_safely(paths.decision_journal)[0] if paths.decision_journal.exists() else []
        market = market_from_decisions(rows)
        account = calculate_account_snapshot(
            initial_balance="1000", cash_balance=production_state.virtual_balance,
            position_side="LONG" if production_state.has_open_position else "FLAT",
            position_quantity=production_state.position_quantity,
            entry_price=production_state.entry_price, current_price=market["price"],
            realized_pnl=production_state.realized_pnl,
            opened_at=production_state.opened_at, now=current,
            stop_loss_price=production_state.stop_loss,
        )
        pnl_lines = [
            f"Equity: {_money(account.equity)}",
            f"Realised PnL: {_money(account.realized_pnl)}",
            f"Unrealised PnL: {_money(account.unrealized_pnl)}",
            f"Total PnL: {_money(account.total_pnl)} ({_pct(account.total_return_pct)})",
        ]
    except (OSError, ValueError):
        pnl_lines = ["Equity: N/A", "Realised PnL: N/A", "Unrealised PnL: N/A", "Total PnL: N/A"]
    production = "\n".join(
        [
            "🌅 Утренний отчёт crypto-bot",
            f"Период: {start.isoformat()} — {current.isoformat()}",
            f"Режим: {snapshot.execution_mode}",
            f"REGIME_FILTER_MODE: {snapshot.filter_mode}",
            (
                "Реальная торговля: включена — ОПАСНО"
                if snapshot.live_trading_enabled
                else "Реальная торговля: выключена"
            ),
            "",
            "⚙️ Сервисы",
            f"Timer: {_health_state(snapshot.timer_state)}",
            f"Service: {_service_report_label(snapshot.service_state)}",
            f"API: {snapshot.component_statuses.get('API', snapshot.api_status)}",
            f"Market data: {snapshot.component_statuses.get('Market data', 'UNKNOWN')}",
            f"Последняя свеча: {snapshot.last_candle}; age after close {_age(snapshot.candle_close_age_seconds if snapshot.candle_close_age_seconds is not None else snapshot.candle_age_seconds)}",
            f"Health: {snapshot.health_status}",
            *( ["Причины:"] + [f"- {item}" for item in reasons[:4]] if reasons else [] ),
            "",
            "📊 Production",
            f"Cash balance: {snapshot.balance}",
            *pnl_lines,
            f"Позиция: {snapshot.position} ({snapshot.position_quantity})",
            f"Решения стратегии за ночь: {period['signals']}",
            f"Paper-сделки за ночь: {period['trades']}",
            f"Разбивка решений: {period.get('decision_reasons') or 'нет данных'}",
            f"Shadow would block: {period['shadow_would_block']}",
            f"API errors: {c.get('api_error_halts', 0)}",
            f"Stale-data events: {c.get('stale_data_rejections', 0)}",
            f"Risk halts: {c.get('risk_limit_halts', 0)}",
            f"Active halt: {snapshot.active_halt_reason or 'none'}",
        ]
    )
    return production + "\n\n" + _candidate_report_block(paths) + "\n\n" + _scored_candidate_report_block()


def format_evening_report(
    snapshot: RuntimeSnapshot,
    paths: TelegramPaths,
    *,
    now: datetime | None = None,
    timezone_name: str = "Asia/Yekaterinburg",
) -> str:
    zone = ZoneInfo(timezone_name)
    current = (now or datetime.now(timezone.utc)).astimezone(zone)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    period = _report_period(paths, start, current)
    runtime = RegimeRuntimeStateStore(paths.runtime_state).load()
    beginning = Decimal(runtime.daily_starting_balance)
    production_state = TradingControllerStateStore(paths.controller_state).load()
    production_rows = (
        read_jsonl_safely(paths.decision_journal)[0]
        if paths.decision_journal.exists() else []
    )
    market = market_from_decisions(production_rows)
    production_snapshot = calculate_account_snapshot(
        initial_balance="1000",
        cash_balance=production_state.virtual_balance,
        position_side="LONG" if production_state.has_open_position else "FLAT",
        position_quantity=production_state.position_quantity,
        entry_price=production_state.entry_price,
        current_price=market["price"],
        realized_pnl=production_state.realized_pnl,
        opened_at=production_state.opened_at,
        now=current,
        stop_loss_price=production_state.stop_loss,
    )
    day_realized = Decimal(str(period["pnl"]))
    day_unrealized = production_snapshot.unrealized_pnl
    day_total = (
        day_realized + day_unrealized
        if day_unrealized is not None else None
    )
    day_return = (
        day_total / beginning * Decimal("100")
        if beginning and day_total is not None else None
    )
    errors = (
        snapshot.counters.get("api_error_halts", 0)
        + snapshot.counters.get("stale_data_rejections", 0)
        + snapshot.counters.get("risk_limit_halts", 0)
    )
    health_detail = (
        snapshot.systemd_monitoring_detail
        or ("systemd status unavailable or permission denied"
            if "unavailable" in snapshot.timer_state.lower() else "none")
    )
    production = "\n".join(
        [
            "Вечерний отчёт crypto-bot / Evening report",
            f"Period: {start.isoformat()} — {current.isoformat()}",
            "",
            "System health:",
            f"overall {snapshot.health_status}",
            f"API {snapshot.api_status}",
            f"timer {_health_state(snapshot.timer_state)}",
            f"service {_health_state(snapshot.service_state)}",
            f"last successful cycle {snapshot.last_candle or 'N/A'}",
            f"last candle age {_age(snapshot.candle_age_seconds)}",
            f"report generated at {current.isoformat()}",
            f"systemd detail {health_detail}",
            "",
            "Market:",
            f"symbol {market['symbol']}",
            f"current price {market['price'] or 'N/A'}",
            f"price timestamp {_local_iso(market['price_timestamp'], zone)}",
            f"source {market['source'] or 'N/A'}",
            "",
            "Production account:",
            *_account_lines(production_snapshot),
            f"Beginning equity {_money(beginning)}",
            f"Ending equity {_money(production_snapshot.equity)}",
            f"Day realized PnL {_money(day_realized)}",
            f"Day unrealized PnL {_money(day_unrealized)}",
            f"Day total PnL {_money(day_total)}",
            f"Day total return {_pct(day_return)}",
            "",
            *_position_lines(production_snapshot, market["symbol"], zone),
            *(
                ["Изменение cash balance связано с открытой позицией и не является само по себе зафиксированным убытком."]
                if production_snapshot.is_open else []
            ),
            "",
            f"Сигналы: {period['signals']}",
            f"Входы/выходы: {period['entries']}/{period['exits']}",
            f"Закрытые сделки: {period['trades']}",
            f"Комиссии: {period['fees']}",
            f"Shadow would block: {period['shadow_would_block']}",
            f"Ошибки и halts: {errors}",
            f"Active halt: {snapshot.active_halt_reason or 'none'}",
        ]
    )
    return (
        production
        + "\n\n"
        + _candidate_report_block(paths)
        + "\n\n"
        + format_daily_comparison(paths, now=now, timezone_name=timezone_name)
        + "\n\n"
        + _equity_history_block(now=now)
    )


def _equity_history_block(*, now: datetime | None = None) -> str:
    from app.equity_history import (
        SnapshotMetrics,
        SnapshotStorage,
        load_equity_history_config,
    )

    root = Path(__file__).resolve().parents[1]
    config = load_equity_history_config(
        root / "config/equity_history.json",
        root=root,
        require_writable_database_parent=False,
    )
    if not config.database_path.exists():
        return "История капитала\nProduction: N/A — insufficient history\nCandidate: N/A — insufficient history"
    current = now or datetime.now(timezone.utc)
    metrics = SnapshotMetrics(SnapshotStorage(config.database_path), config)
    from app.equity_integrity import check_equity_history
    integrity = check_equity_history(config.database_path, now=current)
    lines = [
        "История капитала",
        f"Integrity: {integrity['status']}",
    ]
    if integrity["status"] != "OK":
        lines.append(
            f"Duplicates: {integrity['timestamp_duplicates']}; "
            f"Conflicts: {integrity['timestamp_conflicts']}; "
            f"Gaps: {integrity['large_gaps']}"
        )
    for environment, label in (
        ("production", "Production"), ("candidate", "Candidate")
    ):
        seven = metrics.rolling(environment, "7d", now=current)
        thirty = metrics.rolling(environment, "30d", now=current)
        aggregate = metrics.aggregate(environment)
        reason = seven.get("insufficient_reason") or "none"
        lines.extend(
            [
                f"{label}:",
                f"  Equity {aggregate.get('latest_equity', 'N/A')}",
                f"  7d / 30d return "
                f"{seven.get('return_percent', 'N/A')} / "
                f"{thirty.get('return_percent', 'N/A')}",
                f"  Max DD {aggregate.get('max_drawdown_percent', 'N/A')}",
                f"  Completeness {seven.get('completeness_pct', 'N/A')}",
                f"  History note {reason}",
            ]
        )
    return "\n".join(lines)


def _money(value: Decimal | None) -> str:
    return "N/A" if value is None else f"{value:.2f} USDT"


def _pct(value: Decimal | None) -> str:
    return "N/A" if value is None else f"{value:.3f}%"


def _health_state(value: str) -> str:
    normalized = value.lower()
    if normalized in {"active", "inactive", "ok"}:
        return "OK" if normalized in {"active", "ok"} else "UNKNOWN"
    return "UNKNOWN"


def _service_report_label(value: str) -> str:
    normalized = value.lower()
    if normalized == "inactive":
        return "inactive — ожидаемо между запусками"
    return _health_state(value)


def _local_iso(value: str | None, zone: ZoneInfo) -> str:
    if value is None:
        return "N/A"
    try:
        return datetime.fromisoformat(value).astimezone(zone).isoformat()
    except ValueError:
        return "N/A"


def _account_lines(item: AccountSnapshot) -> list[str]:
    return [
        f"initial balance {_money(item.initial_balance)}",
        f"cash balance {_money(item.cash_balance)}",
        f"position market value {_money(item.position_market_value)}",
        f"equity {_money(item.equity)}",
        f"realized PnL {_money(item.realized_pnl)}",
        f"unrealized PnL {_money(item.unrealized_pnl)}",
        f"total PnL {_money(item.total_pnl)}",
        f"realized return {_pct(item.realized_return_pct)}",
        f"total return {_pct(item.total_return_pct)}",
    ]


def _position_lines(
    item: AccountSnapshot, symbol: str, zone: ZoneInfo
) -> list[str]:
    if not item.is_open:
        return ["Production open position: FLAT"]
    asset = symbol.removesuffix("USDT")
    distance_stop = (
        f"{_money(item.distance_to_stop_value)} / {_pct(item.distance_to_stop_pct)}"
    )
    distance_take = (
        f"{_money(item.distance_to_take_profit_value)} / "
        f"{_pct(item.distance_to_take_profit_pct)}"
    )
    return [
        "Production open position:",
        f"side {item.position_side}",
        f"quantity {item.position_quantity} {asset}",
        f"entry price {_money(item.entry_price)}",
        f"current price {_money(item.current_price)}",
        f"position notional {_money(item.position_quantity * item.entry_price if item.entry_price is not None else None)}",
        f"market value {_money(item.position_market_value)}",
        f"unrealized PnL {_money(item.unrealized_pnl)}",
        f"unrealized return {_pct(item.unrealized_return_pct)}",
        f"opened at {_local_iso(item.opened_at, zone)}",
        f"position age {format_position_age(item.position_age_seconds)}",
        f"stop-loss {_money(item.stop_loss_price)}",
        f"distance to stop {distance_stop}",
        f"take-profit {_money(item.take_profit_price)}",
        f"distance to take-profit {distance_take}",
        f"break-even {'active' if item.break_even_active else 'inactive'}",
        f"trailing-stop {'active' if item.trailing_stop_active else 'inactive'}",
    ]


def _candidate_report_block(paths: TelegramPaths) -> str:
    from app.candidate_runtime import CandidateStateStore

    if not paths.candidate_state.exists():
        return "Candidate paper\nState: not initialized"
    try:
        state = CandidateStateStore(paths.candidate_state).load()
        decisions = (
            read_jsonl_safely(paths.candidate_decision_journal)[0]
            if paths.candidate_decision_journal.exists() else []
        )
        trades = (
            read_jsonl_safely(
                paths.candidate_trade_journal,
                parser=TradeJournalEntry.from_dict,
            )[0]
            if paths.candidate_trade_journal.exists() else []
        )
    except (OSError, ValueError) as exc:
        return f"Candidate paper\nCandidate runtime problem: {type(exc).__name__}"
    from app.candidate_diagnostics import summarize_candidate
    diagnostic = summarize_candidate(paths.candidate_decision_journal, paths.candidate_trade_journal)
    reason_lines = [f"  {key}: {value}" for key, value in diagnostic["rejection_reasons"].items() if key != "entry_allowed"]
    return "\n".join(
        [
            "🧪 Candidate — ADX + HYBRID Pullback",
            f"Status: {'INSUFFICIENT_DATA' if not trades else 'OK'}",
            f"Balance: {state.controller.virtual_balance}",
            f"PnL: {state.controller.realized_pnl}",
            f"Position: {'LONG' if state.controller.has_open_position else 'FLAT'}",
            f"Decisions: {len(decisions)}; Trades: {len(trades)}",
            f"Last candle: {state.last_processed_candle}",
            *( ["Основные причины:"] + reason_lines[:5] if reason_lines else [] ),
        ]
    )


def _scored_candidate_report_block() -> str:
    """Compact read-only scored-candidate section; absent journal is harmless."""
    path = Path(os.environ.get("SCORED_CANDIDATE_DECISION_PATH", "state/scored_candidate_shadow/decisions.jsonl"))
    if not path.exists():
        return "Scored Candidate — shadow\nStatus: not initialized"
    try:
        rows = read_jsonl_safely(path)[0]
        last = rows[-1] if rows else {}
        return "\n".join([
            "🧪 Scored Candidate — shadow",
            "Status: initialized",
            f"Decision: {last.get('decision', last.get('action', 'N/A'))}",
            f"Score: {last.get('signal_score', 'N/A')} / 100",
            f"Risk allocation: {float(last.get('risk_fraction', 0)) * 100:.1f}%" if last else "Risk allocation: N/A",
            "Main limiters:",
            *[f"- {name.removesuffix('_score').replace('_', ' ').title()}" for name, _ in sorted(last.get('components', {}).items(), key=lambda item: item[1])[:2]],
        ])
    except (OSError, ValueError, TypeError):
        return "Scored Candidate — shadow\nStatus: diagnostic unavailable"


def format_trades(paths: TelegramPaths, limit: int = 5) -> str:
    if not paths.trade_journal.exists():
        return "Paper-сделок ещё не было: trade journal отсутствует."
    records, _ = read_jsonl_safely(
        paths.trade_journal, parser=TradeJournalEntry.from_dict
    )
    if not records:
        return "Paper-сделок ещё не было."
    lines = ["Последние paper-сделки:"]
    for trade in records[-limit:]:
        lines.append(
            f"{trade.closed_at} {trade.symbol}: PnL {trade.net_pnl}, "
            f"fee {trade.total_fee}, reason {trade.exit_reason}"
        )
    return "\n".join(lines)


def format_decision(paths: TelegramPaths) -> str:
    if not paths.decision_journal.exists():
        return "Shadow decision journal пока отсутствует."
    records, _ = read_jsonl_safely(paths.decision_journal)
    if not records:
        return "Shadow decisions пока отсутствуют."
    record = records[-1]
    executed = record.get(
        "baseline_trade_executed",
        record.get("execution_signal") == record.get("baseline_signal"),
    )
    would_block = bool(
        record.get("shadow_would_block")
        or (
            record.get("filter_mode") == "shadow"
            and record.get("blocked")
        )
    )
    return "\n".join(
        [
            "Последнее shadow-решение",
            f"Timestamp: {record.get('candle_timestamp')}",
            f"Режим рынка: {record.get('regime') or 'unknown'}",
            f"Baseline signal: {record.get('baseline_signal')}",
            f"Baseline trade executed: {'yes' if executed else 'no'}",
            f"Regime filter would block: {'yes' if would_block else 'no'}",
            f"Причина: {record.get('shadow_block_reason') or record.get('blocked_reason') or 'none'}",
        ]
    )


def format_mode(snapshot: RuntimeSnapshot) -> str:
    return "\n".join(
        [
            f"Execution mode: {snapshot.execution_mode}",
            f"Regime filter mode: {snapshot.filter_mode}",
            (
                "ВНИМАНИЕ: реальные ордера разрешены"
                if snapshot.live_trading_enabled
                else "Реальная торговля выключена; реальные ордера не отправляются."
            ),
        ]
    )


def format_candidate(paths: TelegramPaths) -> str:
    from app.candidate_runtime import CandidateStateStore

    if not paths.candidate_state.exists():
        return "Candidate paper ещё не инициализирован."
    try:
        state = CandidateStateStore(paths.candidate_state).load()
        decisions = (
            read_jsonl_safely(paths.candidate_decision_journal)[0]
            if paths.candidate_decision_journal.exists()
            else []
        )
        service = _systemd_unit_status("crypto-paper-candidate.service")
    except (OSError, ValueError) as exc:
        return f"Candidate runtime problem: {type(exc).__name__}"
    latest = decisions[-3:]
    recent = ", ".join(
        f"{row.get('candle_timestamp')}:{row.get('decision')}"
        for row in latest
    ) or "none"
    controller = state.controller
    return "\n".join(
        [
            "Candidate paper (read-only)",
            "Mode: PAPER; LIVE disabled",
            "Strategy: ADX + HYBRID Pullback",
            f"Balance: {controller.virtual_balance}",
            f"Position: {'LONG' if controller.has_open_position else 'FLAT'}",
            f"Recent decisions: {recent}",
            f"Closed trades: {controller.closed_trades}",
            f"PnL: {controller.realized_pnl}",
            f"Health: {service.active_state}; halt {state.active_halt or 'none'}",
        ]
    )


def format_comparison(paths: TelegramPaths) -> str:
    from app.paper_comparator import compare_paper_runtimes

    try:
        report = compare_paper_runtimes(
            production_state=paths.controller_state,
            production_trades=paths.trade_journal,
            production_decisions=paths.decision_journal,
            candidate_state=paths.candidate_state,
            candidate_trades=paths.candidate_trade_journal,
            candidate_decisions=paths.candidate_decision_journal,
            production_runtime_summary=paths.runtime_state,
            candidate_runtime_summary=paths.candidate_runtime_summary,
            period="since_candidate_start",
        )
    except (OSError, ValueError) as exc:
        return f"Comparison unavailable: {type(exc).__name__}"
    return _format_comparison_report(report, title="Production vs Candidate")


def format_daily_comparison(
    paths: TelegramPaths,
    *,
    now: datetime | None = None,
    timezone_name: str = "Asia/Yekaterinburg",
) -> str:
    from app.strategy_lab import (
        LaboratoryConfig,
        RankingThresholds,
        StrategySpec,
    )
    from app.strategy_confidence import (
        build_promotion_review,
        load_promotion_config,
        render_promotion_review,
    )

    config = LaboratoryConfig(
        initial_balance=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        ranking=RankingThresholds(),
        strategies=(
            StrategySpec(
                "production", "Production", True, "production",
                paths.controller_state, paths.trade_journal,
                paths.decision_journal, paths.runtime_state,
            ),
            StrategySpec(
                "candidate_adx_hybrid", "ADX + HYBRID Pullback", True,
                "candidate", paths.candidate_state,
                paths.candidate_trade_journal,
                paths.candidate_decision_journal,
                paths.candidate_runtime_summary,
            ),
        ),
    )
    try:
        promotion_path = Path(__file__).resolve().parents[1] / "config/strategy_lab.json"
        operational = {}
        for strategy_id, unit in (
            ("production", "crypto-paper.timer"),
            ("candidate_adx_hybrid", "crypto-paper-candidate.timer"),
        ):
            unit_status = _systemd_unit_status(unit)
            operational[strategy_id] = {
                "timer_status": unit_status.active_state,
                "timer_active": (
                    unit_status.active_state == "active"
                    if unit_status.available else None
                ),
            }
        report = build_promotion_review(
            config,
            load_promotion_config(promotion_path),
            period="24h",
            now=now or datetime.now(timezone.utc),
            timezone_name=timezone_name,
            operational=operational,
        )
    except (OSError, ValueError) as exc:
        return f"Production vs Candidate\nComparison unavailable: {type(exc).__name__}"
    return render_promotion_review(report, explain=True).rstrip()


def _format_comparison_report(report: dict[str, Any], *, title: str) -> str:
    prod, cand = report["production"], report["candidate"]
    delta, decisions = report["deltas"], report["decisions"]
    categories = decisions["categories"]
    lines = [
        title,
        f"Status: {report['status']}",
        "Production:",
        f"cash {prod['cash_balance']}; equity {prod['equity']}",
        f"realized {prod['realized_pnl']}; unrealized {prod['unrealized_pnl']}; total {prod['total_pnl']}",
        f"total return {prod['total_return_pct']}%; position {_position_text(prod)}",
        f"entry {prod['entry_price']}; current {prod['current_price']}; age {_metric_age(prod)}",
        f"distance to stop {prod['distance_to_stop_value']} / {prod['distance_to_stop_pct']}%; trades {prod['closed_trades']}; fees {prod['fees']}",
        f"drawdown {prod['max_drawdown_percent']}%; PF {prod['profit_factor']}",
        "Candidate:",
        f"cash {cand['cash_balance']}; equity {cand['equity']}",
        f"realized {cand['realized_pnl']}; unrealized {cand['unrealized_pnl']}; total {cand['total_pnl']}",
        f"total return {cand['total_return_pct']}%; position {_position_text(cand)}",
        f"entry {cand['entry_price']}; current {cand['current_price']}; age {_metric_age(cand)}",
        f"distance to stop {cand['distance_to_stop_value']} / {cand['distance_to_stop_pct']}%; trades {cand['closed_trades']}; fees {cand['fees']}",
        f"drawdown {cand['max_drawdown_percent']}%; PF {cand['profit_factor']}",
        "Delta candidate-production:",
        f"equity {delta['equity']}; total PnL {delta['total_pnl']}; total return {delta['total_return_pct']}%",
        f"unrealized PnL {delta['unrealized_pnl']}; realized PnL {delta['realized_pnl']}",
        f"fees {delta['fees']}; drawdown {delta['drawdown_percent']}; trades {delta['trade_count']}",
        "Decisions:",
        f"matched {decisions['matched_candles']}; agreement {decisions['agreement_rate_percent']}%; differences {decisions['difference_count']}",
        "Prod ENTER / Cand WAIT-HOLD: "
        + str(
            categories["PRODUCTION_ENTER_CANDIDATE_WAIT"]
            + categories["PRODUCTION_ENTER_CANDIDATE_HOLD"]
        ),
        f"Cand ENTER / Prod HOLD: {categories['CANDIDATE_ENTER_PRODUCTION_HOLD']}",
        f"Different EXIT: {categories['DIFFERENT_EXIT_REASON']}; missing: {decisions['unmatched_records']}",
    ]
    if report["warnings"]:
        candidate_warning = next(
            (item for item in report["warnings"] if "Candidate data unavailable" in item),
            None,
        )
        if candidate_warning:
            lines.append("Diagnostic: Candidate data unavailable")
    if report["recent_differences"]:
        lines.append("Последние расхождения:")
        for item in report["recent_differences"][-3:]:
            lines.append(
                f"{item['time']}: {item['production_decision']}/{item['candidate_decision']}; "
                f"{item['production_reason']} / {item['candidate_reason']}"
            )
    lines.append(report["conclusion"])
    return "\n".join(lines)


def _position_text(metrics: dict[str, Any]) -> str:
    if metrics["open_position"] == "N/A":
        return "N/A"
    side = "LONG" if metrics["open_position"] else "FLAT"
    return f"{side} ({metrics['position_size']})"


def _metric_age(metrics: dict[str, Any]) -> str:
    value = metrics.get("position_age_seconds")
    return "N/A" if value == "N/A" else format_position_age(int(value))


def telegram_chunks(text: str, *, limit: int = 4096, maximum: int = 4) -> list[str]:
    if len(text) <= limit:
        return [text]
    blocks = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    # Reserve room for "Part 00/00\n".
    content_limit = max(1, limit - 16)
    for block in blocks:
        pieces = [block]
        if len(block) > content_limit:
            pieces = []
            remainder = block
            while remainder:
                split = remainder.rfind("\n", 0, content_limit + 1)
                if split <= 0:
                    split = content_limit
                pieces.append(remainder[:split])
                remainder = remainder[split:].lstrip("\n")
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= content_limit:
                current = candidate
            else:
                chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    chunks = chunks[:maximum]
    total = len(chunks)
    return [f"Part {index}/{total}\n{chunk}" for index, chunk in enumerate(chunks, 1)]


HELP_TEXT = "\n".join(
    [
        "Команды crypto-bot:",
        "/status — состояние paper runtime",
        "/trades — последние 5 paper-сделок",
        "/decision — последнее shadow-решение",
        "/mode — режим исполнения",
        "/candidate — изолированный Strategy V2 candidate",
        "/comparison — production против candidate",
        "/help — эта справка",
    ]
)


def command_response(
    command: str,
    snapshot: RuntimeSnapshot,
    paths: TelegramPaths,
) -> str:
    normalized = command.split()[0].split("@")[0].lower()
    if normalized == "/status":
        return format_status(snapshot)
    if normalized == "/trades":
        return format_trades(paths)
    if normalized == "/decision":
        return format_decision(paths)
    if normalized == "/mode":
        return format_mode(snapshot)
    if normalized == "/candidate":
        return format_candidate(paths)
    if normalized == "/comparison":
        return format_comparison(paths)
    if normalized in {"/start", "/help"}:
        return HELP_TEXT
    return HELP_TEXT


def process_update(
    update: dict[str, Any],
    *,
    allowed_chat_id: str,
    responder: Callable[[str], str],
    sender: Callable[[str, str], None],
) -> bool:
    message = update.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if chat_id != str(allowed_chat_id):
        LOGGER.warning(
            "Ignored Telegram message from unauthorized chat_id=%s",
            chat_id or "unknown",
        )
        return False
    text = message.get("text")
    if not isinstance(text, str) or not text.startswith("/"):
        return False
    for chunk in telegram_chunks(responder(text)):
        sender(chat_id, chunk)
    return True


def transition_alerts(
    previous: NotificationState,
    snapshot: RuntimeSnapshot,
    checks: list[HealthCheckResult],
    *,
    cycle_failed: bool,
) -> tuple[list[tuple[str, str]], NotificationState]:
    check_map = {check.name: check for check in checks}
    unhealthy = (
        snapshot.health_status == HealthStatus.CRITICAL.name
        or cycle_failed
        or snapshot.live_trading_enabled
    )
    api_unavailable = (
        check_map.get("bybit_api") is not None
        and check_map["bybit_api"].status is HealthStatus.CRITICAL
    )
    stale = (
        check_map.get("last_candle") is not None
        and check_map["last_candle"].status is HealthStatus.CRITICAL
    )
    unsafe_live = snapshot.live_trading_enabled
    current_health = "unhealthy" if unhealthy else "healthy"
    alerts: list[tuple[str, str]] = []
    if previous.health_state and previous.health_state != current_health:
        alerts.append(
            (
                f"health:{current_health}",
                "Crypto-bot стал НЕИСПРАВЕН"
                if unhealthy
                else "Crypto-bot восстановился: состояние healthy",
            )
        )
    if (
        snapshot.active_halt_reason
        and snapshot.active_halt_reason != previous.active_halt_reason
    ):
        alerts.append(
            (
                f"halt:{snapshot.active_halt_reason}",
                f"Активирован runtime halt: {snapshot.active_halt_reason}",
            )
        )
    for key, active, was_active, message in (
        (
            "api",
            api_unavailable,
            previous.api_unavailable,
            "Bybit public API недоступен",
        ),
        (
            "stale",
            stale,
            previous.stale_data,
            "Данные устарели сверх допустимого порога",
        ),
        (
            "cycle",
            cycle_failed,
            previous.cycle_failed,
            "Последний systemd cycle завершился с ошибкой",
        ),
        (
            "live",
            unsafe_live,
            previous.unsafe_live,
            "КРИТИЧНО: неожиданно включён LIVE_TRADING_ENABLED",
        ),
    ):
        if active and not was_active:
            alerts.append((key, message))
    updated = NotificationState(
        health_state=current_health,
        active_halt_reason=snapshot.active_halt_reason,
        api_unavailable=api_unavailable,
        stale_data=stale,
        cycle_failed=cycle_failed,
        unsafe_live=unsafe_live,
        last_sent_at=dict(previous.last_sent_at),
        update_offset=previous.update_offset,
    )
    return alerts, updated


def send_transition_alerts(
    state_store: NotificationStateStore,
    snapshot: RuntimeSnapshot,
    checks: list[HealthCheckResult],
    sender: Callable[[str], None],
    *,
    cycle_failed: bool | None = None,
    now: datetime | None = None,
    cooldown_seconds: int = 1800,
) -> int:
    previous = state_store.load()
    alerts, updated = transition_alerts(
        previous,
        snapshot,
        checks,
        cycle_failed=_cycle_failed() if cycle_failed is None else cycle_failed,
    )
    current = now or datetime.now(timezone.utc)
    sent = 0
    for key, message in alerts:
        last_raw = previous.last_sent_at.get(key)
        if last_raw:
            last = datetime.fromisoformat(last_raw)
            if (current - last).total_seconds() < cooldown_seconds:
                continue
        sender(message)
        updated.last_sent_at[key] = current.isoformat()
        sent += 1
    state_store.save(updated)
    return sent
