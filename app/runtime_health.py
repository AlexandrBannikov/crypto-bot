from __future__ import annotations

import fcntl
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable

from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.trading_controller_store import TradingControllerStateStore


class HealthStatus(IntEnum):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    # Public vocabulary aliases. CRITICAL is retained for compatibility with
    # existing callers; new diagnostics may use ERROR/UNKNOWN explicitly.
    ERROR = 2
    UNKNOWN = 1


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    name: str
    status: HealthStatus
    message: str
    details: dict[str, Any]
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.name
        return result


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_timestamp(path: Path) -> int:
    value = int(path.read_text(encoding="utf-8").strip())
    if value < 0:
        raise ValueError("timestamp must not be negative")
    return value


def read_jsonl_safely(
    path: Path, *, parser: Callable[[object], Any] | None = None
) -> tuple[list[Any], bool]:
    """Read JSONL without modifying it; ignore only an incomplete final line."""
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    values: list[Any] = []
    ignored_tail = False
    for index, raw in enumerate(lines):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw.decode("utf-8"))
            values.append(parser(value) if parser else value)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            final_unterminated = index == len(lines) - 1 and not raw.endswith(
                (b"\n", b"\r")
            )
            if final_unterminated:
                ignored_tail = True
                break
            raise ValueError(f"corrupt JSONL line {index + 1} in {path}")
    return values, ignored_tail


def check_lock(path: Path, *, now: datetime | None = None) -> HealthCheckResult:
    checked = (now or utc_now()).isoformat()
    if not path.exists():
        return HealthCheckResult("controller_lock", HealthStatus.OK, "lock file absent", {}, checked)
    try:
        with path.open("r", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.seek(0)
                metadata_text = handle.read().strip()
                status = HealthStatus.OK
                message = "controller lock is held"
                try:
                    metadata = json.loads(metadata_text)
                    started = datetime.fromisoformat(metadata["started_at"])
                    age = ((now or utc_now()) - started).total_seconds()
                    if age > 1800:
                        status = HealthStatus.CRITICAL
                        message = f"controller lock appears stuck ({age / 60:.1f} minutes)"
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    age = None
                return HealthCheckResult(
                    "controller_lock", status, message,
                    {"held": True, "age_seconds": age}, checked,
                )
            finally:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        return HealthCheckResult(
            "controller_lock", HealthStatus.OK,
            "lock file exists but is not held", {"held": False}, checked,
        )
    except OSError as exc:
        return HealthCheckResult(
            "controller_lock", HealthStatus.CRITICAL,
            f"lock cannot be inspected: {exc}", {}, checked,
        )


def _result(name: str, status: HealthStatus, message: str, details: dict[str, Any], now: datetime) -> HealthCheckResult:
    return HealthCheckResult(name, status, message, details, now.isoformat())


def candle_timing_diagnostics(
    candle_open_timestamp: int,
    *,
    timeframe_minutes: int,
    now: datetime,
    max_cycle_delay_minutes: int = 30,
) -> dict[str, Any]:
    """Describe freshness for exchanges whose kline timestamp is open time."""
    if timeframe_minutes <= 0:
        raise ValueError("timeframe_minutes must be positive")
    interval = timeframe_minutes * 60
    current = int(now.timestamp())
    candle_close = candle_open_timestamp + interval
    expected_open = current // interval * interval - interval
    lag_seconds = max(0, expected_open - candle_open_timestamp)
    lag_candles = lag_seconds / interval
    close_age = current - candle_close
    cycle_delay = max(0, close_age)
    # A matching expected candle is fresh even late in the hour: its close
    # age naturally approaches one full timeframe. Cycle execution delay is
    # reported separately and must come from service timestamps, not kline
    # open time.
    stale = lag_candles > 0
    if lag_candles > 0:
        reason = f"local state is {lag_candles:.1f} closed candles behind"
    else:
        reason = "latest expected closed candle is processed"
    return {
        "candle_open_timestamp": candle_open_timestamp,
        "candle_close_timestamp": candle_close,
        "candle_open_age_seconds": current - candle_open_timestamp,
        "candle_close_age_seconds": close_age,
        "expected_latest_closed_candle": expected_open,
        "market_lag_candles": lag_candles,
        "cycle_delay_seconds": cycle_delay,
        "stale_state": stale,
        "warning_reason": reason,
    }


def run_health_checks(
    *,
    state_path: Path,
    candle_path: Path,
    journal_path: Path,
    shadow_path: Path,
    lock_path: Path | None,
    symbol: str = "ETHUSDT",
    timeframe: str = "60",
    max_candle_age_minutes: int = 90,
    max_market_lag_candles: int = 1,
    no_network: bool = False,
    inspect_lock: bool = True,
    now: datetime | None = None,
    market_fetcher: Callable[[], int] | None = None,
) -> tuple[list[HealthCheckResult], dict[str, Any]]:
    current = now or utc_now()
    checks: list[HealthCheckResult] = []
    context: dict[str, Any] = {"state": None, "last_candle": None, "market_candle": None}

    if not state_path.exists():
        checks.append(_result("controller_state", HealthStatus.CRITICAL, "controller state is missing", {"path": str(state_path)}, current))
    else:
        try:
            state = TradingControllerStateStore(state_path).load()
            context["state"] = state
            finite = all(
                value.is_finite()
                for value in (state.virtual_balance, state.position_quantity, state.total_fees, state.realized_pnl)
            )
            if not finite:
                raise ValueError("state contains non-finite numeric values")
            checks.append(_result("controller_state", HealthStatus.OK, "controller state is valid", {"path": str(state_path)}, current))
        except (OSError, ValueError) as exc:
            checks.append(_result("controller_state", HealthStatus.CRITICAL, f"controller state is invalid: {exc}", {"path": str(state_path)}, current))

    try:
        timestamp = read_timestamp(candle_path)
        context["last_candle"] = timestamp
        timing = candle_timing_diagnostics(
            timestamp,
            timeframe_minutes=int(timeframe),
            now=current,
            max_cycle_delay_minutes=max(
                1, max_candle_age_minutes - int(timeframe)
            ),
        )
        lag = float(timing["market_lag_candles"])
        status = (
            HealthStatus.CRITICAL
            if lag > max_market_lag_candles * 2
            else HealthStatus.WARNING
            if timing["stale_state"]
            else HealthStatus.OK
        )
        checks.append(
            _result(
                "last_candle",
                status,
                str(timing["warning_reason"]),
                {"path": str(candle_path), **timing},
                current,
            )
        )
    except (OSError, ValueError) as exc:
        checks.append(_result("last_candle", HealthStatus.CRITICAL, f"last candle timestamp unavailable: {exc}", {"path": str(candle_path)}, current))

    from app.trade_journal import TradeJournalEntry
    for name, path, parser in (
        ("trade_journal", journal_path, TradeJournalEntry.from_dict),
        ("shadow_diagnostics", shadow_path, None),
    ):
        if not path.exists():
            checks.append(_result(name, HealthStatus.WARNING, f"{name.replace('_', ' ')} is missing", {"path": str(path), "records": 0}, current))
            context[name] = []
            continue
        try:
            rows, ignored = read_jsonl_safely(path, parser=parser)
            context[name] = rows
            checks.append(_result(name, HealthStatus.WARNING if ignored else HealthStatus.OK, f"{len(rows)} records readable" + ("; incomplete final line ignored" if ignored else ""), {"path": str(path), "records": len(rows), "incomplete_final_line": ignored}, current))
        except (OSError, ValueError) as exc:
            context[name] = []
            checks.append(_result(name, HealthStatus.CRITICAL, f"{name.replace('_', ' ')} is invalid: {exc}", {"path": str(path)}, current))

    if inspect_lock:
        if lock_path is None:
            raise ValueError("lock_path is required when lock inspection is enabled")
        checks.append(check_lock(lock_path, now=current))
    if no_network:
        checks.append(_result("bybit_api", HealthStatus.OK, "network check disabled", {"skipped": True}, current))
    else:
        try:
            if market_fetcher is None:
                feed = BybitMarketDataFeed(BybitMarketDataConfig(symbol=symbol, interval=timeframe, limit=2, max_retries=1))
                market_timestamp = feed.get_latest_candle().timestamp
            else:
                market_timestamp = market_fetcher()
            context["market_candle"] = market_timestamp
            future = market_timestamp > current.timestamp() + int(timeframe) * 60
            checks.append(_result("bybit_api", HealthStatus.CRITICAL if future else HealthStatus.OK, "Bybit public market data available" if not future else "Bybit candle timestamp is in the future", {"latest_closed_candle": market_timestamp}, current))
            local = context["last_candle"]
            if local is not None:
                lag = max(0, market_timestamp - local)
                lag_candles = lag / (int(timeframe) * 60)
                status = HealthStatus.CRITICAL if lag_candles > max_market_lag_candles * 2 else HealthStatus.WARNING if lag_candles > max_market_lag_candles else HealthStatus.OK
                checks.append(_result("market_lag", status, f"local state lags market by {lag_candles:.1f} candles", {"lag_seconds": lag, "lag_candles": lag_candles, "local_candle_open": local, "market_candle_open": market_timestamp}, current))
        except Exception as exc:
            checks.append(_result("bybit_api", HealthStatus.CRITICAL, f"Bybit public API unavailable: {type(exc).__name__}: {exc}", {}, current))
    return checks, context


def overall_status(checks: list[HealthCheckResult]) -> HealthStatus:
    return max((item.status for item in checks), default=HealthStatus.OK)
