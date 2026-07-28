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


@dataclass(frozen=True, slots=True)
class TelegramPaths:
    controller_state: Path
    runtime_state: Path
    last_candle: Path
    trade_journal: Path
    decision_journal: Path
    controller_lock: Path
    notification_state: Path

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
            controller_lock=Path(
                os.environ.get(
                    "CONTROLLER_LOCK_PATH",
                    "state/bybit_controller.lock",
                )
            ),
            notification_state=notification_state
            or Path(
                os.environ.get(
                    "TELEGRAM_NOTIFICATION_STATE_PATH",
                    "state/telegram_notifications.json",
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
        self.call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[:4096],
                "disable_web_page_preview": "true",
            },
        )


def _systemd_state(unit: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        value = result.stdout.strip()
        return value or f"unknown (exit {result.returncode})"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _cycle_failed() -> bool:
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                "crypto-paper.service",
                "--property=ExecMainStatus",
                "--value",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode != 0 or result.stdout.strip() not in {"", "0"}
    except (OSError, subprocess.SubprocessError):
        return True


def collect_snapshot(
    paths: TelegramPaths,
    *,
    no_network: bool = False,
    now: datetime | None = None,
    systemd_state: Callable[[str], str] = _systemd_state,
    market_fetcher: Callable[[], int] | None = None,
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
    checks, context = run_health_checks(
        state_path=paths.controller_state,
        candle_path=paths.last_candle,
        journal_path=paths.trade_journal,
        shadow_path=paths.decision_journal,
        lock_path=paths.controller_lock,
        max_candle_age_minutes=max(1, max_data_age_seconds // 60),
        no_network=no_network,
        now=current,
        market_fetcher=market_fetcher,
    )
    last_candle = context.get("last_candle")
    age = (
        max(0.0, current.timestamp() - last_candle)
        if last_candle is not None
        else None
    )
    if age is not None and age > max_data_age_seconds:
        checks = [
            (
                HealthCheckResult(
                    item.name,
                    HealthStatus.CRITICAL,
                    (
                        "last candle exceeds configured maximum age "
                        f"({age / 60:.1f} minutes)"
                    ),
                    {**item.details, "age_seconds": age},
                    item.checked_at,
                )
                if item.name == "last_candle"
                else item
            )
            for item in checks
        ]
    check_map = {item.name: item for item in checks}
    lag = check_map.get("market_lag")
    api = check_map.get("bybit_api")
    position = "LONG" if controller.has_open_position else "FLAT"
    snapshot = RuntimeSnapshot(
        checked_at=current.isoformat(),
        timer_state=systemd_state("crypto-paper.timer"),
        service_state=systemd_state("crypto-paper.service"),
        execution_mode="PAPER",
        filter_mode=strategy.mode.value,
        live_trading_enabled=live_enabled,
        balance=str(controller.virtual_balance),
        position=position,
        position_quantity=str(controller.position_quantity),
        last_candle=last_candle,
        candle_age_seconds=age,
        market_lag_candles=(
            float(lag.details["lag_candles"]) if lag else None
        ),
        api_status=api.status.name if api else "UNKNOWN",
        health_status=overall_status(checks).name,
        active_halt_reason=runtime.active_halt_reason,
        counters=asdict(runtime.counters),
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
    return "\n".join(
        [
            "Утренний отчёт crypto-bot",
            f"Период: {start.isoformat()} — {current.isoformat()}",
            f"Timer/service: {snapshot.timer_state}/{snapshot.service_state}",
            f"Режим: {snapshot.execution_mode}",
            f"REGIME_FILTER_MODE: {snapshot.filter_mode}",
            (
                "Реальная торговля: включена — ОПАСНО"
                if snapshot.live_trading_enabled
                else "Реальная торговля: выключена"
            ),
            f"Баланс: {snapshot.balance}",
            f"Позиция: {snapshot.position} ({snapshot.position_quantity})",
            f"Сигналы за ночь: {period['signals']}",
            f"Paper-сделки за ночь: {period['trades']}",
            f"Shadow would block: {period['shadow_would_block']}",
            f"API errors: {c.get('api_error_halts', 0)}",
            f"Stale-data events: {c.get('stale_data_rejections', 0)}",
            f"Risk halts: {c.get('risk_limit_halts', 0)}",
            f"Active halt: {snapshot.active_halt_reason or 'none'}",
            f"Последняя свеча: {snapshot.last_candle}; age {_age(snapshot.candle_age_seconds)}",
            f"Health: {snapshot.health_status}; API {snapshot.api_status}",
        ]
    )


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
    ending = Decimal(snapshot.balance)
    return_percent = (
        (ending - beginning) / beginning * Decimal("100")
        if beginning
        else Decimal("0")
    )
    errors = (
        snapshot.counters.get("api_error_halts", 0)
        + snapshot.counters.get("stale_data_rejections", 0)
        + snapshot.counters.get("risk_limit_halts", 0)
    )
    return "\n".join(
        [
            "Вечерний отчёт crypto-bot",
            f"Период: {start.isoformat()} — {current.isoformat()}",
            f"Результат дня: PnL {period['pnl']}",
            f"Beginning/ending balance: {beginning}/{ending}",
            f"Доходность: {return_percent}%",
            f"Сигналы: {period['signals']}",
            f"Входы/выходы: {period['entries']}/{period['exits']}",
            f"Закрытые сделки: {period['trades']}",
            f"Комиссии: {period['fees']}",
            f"Shadow would block: {period['shadow_would_block']}",
            f"Ошибки и halts: {errors}",
            f"Система: {snapshot.health_status}; timer {snapshot.timer_state}; API {snapshot.api_status}",
            f"Открытая позиция: {snapshot.position} ({snapshot.position_quantity})",
            f"Active halt: {snapshot.active_halt_reason or 'none'}",
        ]
    )


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


HELP_TEXT = "\n".join(
    [
        "Команды crypto-bot:",
        "/status — состояние paper runtime",
        "/trades — последние 5 paper-сделок",
        "/decision — последнее shadow-решение",
        "/mode — режим исполнения",
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
    sender(chat_id, responder(text))
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
