"""Read-only Prometheus exporter for persisted crypto-bot runtime state.

This module deliberately does not import controller, executor, exchange, or
notification code.  It only reads files already persisted by those contours.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable

from app.runtime_versions import (
    EXECUTION_POLICY_VERSION,
    FEATURE_VERSION,
    LEDGER_SCHEMA_VERSION,
    STRATEGY_LOGIC_VERSION,
)


LOGGER = logging.getLogger("crypto.metrics_exporter")
INITIAL_BALANCE = Decimal("1000")
V2_CORRECTNESS_FORWARD_TIMESTAMP = 1787400000
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9476
MAX_JOURNAL_BYTES = 10 * 1024 * 1024
SAFE_VERSION = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


@dataclass(frozen=True, slots=True)
class ExporterPaths:
    production_state: Path = Path("state/trading_controller.json")
    production_journal: Path = Path("state/controller_trade_journal.jsonl")
    v2_state: Path = Path("state/strategy_v2_shadow.json")
    v2_journal: Path = Path("state/strategy_v2_shadow.jsonl")
    runtime_state: Path = Path("state/regime_runtime.json")
    last_candle: Path = Path("state/trading_controller_last_candle.txt")
    canonical_features: Path = Path("state/canonical/candle_features.jsonl")
    production_decisions: Path = Path("state/shadow_decisions.jsonl")

    @classmethod
    def from_root(cls, root: Path) -> "ExporterPaths":
        state = root / "state"
        return cls(
            production_state=state / "trading_controller.json",
            production_journal=state / "controller_trade_journal.jsonl",
            v2_state=state / "strategy_v2_shadow.json",
            v2_journal=state / "strategy_v2_shadow.jsonl",
            runtime_state=state / "regime_runtime.json",
            last_candle=state / "trading_controller_last_candle.txt",
            canonical_features=state / "canonical/candle_features.jsonl",
            production_decisions=state / "shadow_decisions.jsonl",
        )


METRICS: dict[str, tuple[str, str]] = {
    "crypto_metrics_exporter_up": ("Whether the exporter HTTP endpoint is serving.", "gauge"),
    "crypto_metrics_exporter_errors_total": ("Cumulative persisted-source read or validation errors.", "counter"),
    "crypto_build_info": ("Build and causal lifecycle version information.", "gauge"),
    "crypto_production_equity_usdt": ("Production paper equity marked at the latest persisted ETH price.", "gauge"),
    "crypto_production_cash_usdt": ("Production paper cash balance.", "gauge"),
    "crypto_production_realized_pnl_usdt": ("Production cumulative realized PnL.", "gauge"),
    "crypto_production_unrealized_pnl_usdt": ("Production open-position unrealized PnL including stored entry fee through equity reconciliation.", "gauge"),
    "crypto_production_total_pnl_usdt": ("Production total PnL relative to initial balance.", "gauge"),
    "crypto_production_total_return_ratio": ("Production total return as a ratio.", "gauge"),
    "crypto_production_position_open": ("Whether Production has an open position.", "gauge"),
    "crypto_production_position_quantity_eth": ("Production ETH position quantity.", "gauge"),
    "crypto_production_position_entry_price_usdt": ("Production position entry price; absent while flat.", "gauge"),
    "crypto_production_position_market_value_usdt": ("Production position market value.", "gauge"),
    "crypto_production_position_unrealized_return_ratio": ("Production price return from entry as a ratio; absent while flat.", "gauge"),
    "crypto_production_position_age_seconds": ("Production open-position age; absent while flat.", "gauge"),
    "crypto_production_closed_trades_total": ("Production persisted closed trades.", "gauge"),
    "crypto_production_winning_trades_total": ("Production profitable closed trades, cached from the journal.", "gauge"),
    "crypto_production_max_drawdown_ratio": ("Production maximum drawdown as a ratio.", "gauge"),
    "crypto_v2_equity_usdt": ("Strategy V2 research equity.", "gauge"),
    "crypto_v2_cash_usdt": ("Strategy V2 research cash.", "gauge"),
    "crypto_v2_realized_pnl_usdt": ("Strategy V2 realized PnL.", "gauge"),
    "crypto_v2_unrealized_pnl_usdt": ("Strategy V2 unrealized PnL.", "gauge"),
    "crypto_v2_total_pnl_usdt": ("Strategy V2 total PnL relative to initial balance.", "gauge"),
    "crypto_v2_position_open": ("Whether Strategy V2 has an open position.", "gauge"),
    "crypto_v2_position_quantity_eth": ("Strategy V2 ETH position quantity.", "gauge"),
    "crypto_v2_position_avg_entry_usdt": ("Strategy V2 average entry; absent while flat.", "gauge"),
    "crypto_v2_score": ("Latest Strategy V2 score.", "gauge"),
    "crypto_v2_closed_trades_total": ("Strategy V2 correctness-forward closed trades since timestamp 1787400000.", "gauge"),
    "crypto_v2_win_rate_ratio": ("Strategy V2 correctness-forward win rate ratio.", "gauge"),
    "crypto_v2_max_drawdown_ratio": ("Strategy V2 correctness-forward maximum drawdown ratio.", "gauge"),
    "crypto_v2_pending_entry": ("Whether Strategy V2 has a pending entry intent.", "gauge"),
    "crypto_v2_pending_exit": ("Whether Strategy V2 has a pending exit intent.", "gauge"),
    "crypto_v2_vs_production_equity_delta_usdt": ("Strategy V2 equity minus Production equity.", "gauge"),
    "crypto_eth_price_usdt": ("Latest persisted ETHUSDT close used for observability.", "gauge"),
    "crypto_market_lag_candles": ("Local persisted state lag behind the expected latest closed hourly candle.", "gauge"),
    "crypto_market_data_ok": ("Whether persisted market data is at most one candle behind.", "gauge"),
    "crypto_api_ok": ("Gauge derived from the controller's persisted active API halt state; it is not a live API probe.", "gauge"),
    "crypto_trading_health_ok": ("Whether required persisted sources are readable, current, and without an active halt.", "gauge"),
    "crypto_canonical_snapshot_ready": ("Whether the exact latest processed candle has a canonical feature snapshot.", "gauge"),
    "crypto_canonical_score": ("Latest canonical signal score.", "gauge"),
    "crypto_canonical_candle_timestamp_seconds": ("Latest canonical candle open timestamp.", "gauge"),
    "crypto_stale_events_total": ("Controller cumulative stale-data rejection events.", "counter"),
    "crypto_api_errors_total": ("Controller cumulative API error halt events.", "counter"),
    "crypto_risk_halts_total": ("Controller cumulative risk-limit halt events.", "counter"),
    "crypto_active_halt": ("Whether any controller halt is currently active.", "gauge"),
}


def _escape_help(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _number(value: Decimal | float | int) -> str:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("metric value must be finite")
    if result == 0:
        return "0"
    return format(result, ".15g")


class MetricSet:
    def __init__(self) -> None:
        self.samples: dict[str, list[tuple[dict[str, str], str]]] = {}

    def add(self, name: str, value: Decimal | float | int, labels: dict[str, str] | None = None) -> None:
        if name not in METRICS:
            raise KeyError(f"unknown metric {name}")
        self.samples.setdefault(name, []).append((labels or {}, _number(value)))

    def render(self) -> str:
        lines: list[str] = []
        for name in METRICS:
            if name not in self.samples:
                continue
            help_text, metric_type = METRICS[name]
            lines.extend((f"# HELP {name} {_escape_help(help_text)}", f"# TYPE {name} {metric_type}"))
            for labels, value in self.samples[name]:
                suffix = ""
                if labels:
                    suffix = "{" + ",".join(
                        f'{key}="{_escape_label(labels[key])}"' for key in sorted(labels)
                    ) + "}"
                lines.append(f"{name}{suffix} {value}")
        return "\n".join(lines) + "\n"


class FileCache:
    """Cache parsed immutable snapshots until size or mtime changes."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], tuple[tuple[int, int], Any]] = {}

    @staticmethod
    def signature(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def get(self, path: Path, kind: str, loader: Callable[[], Any]) -> Any:
        signature = self.signature(path)
        key = (str(path), kind)
        cached = self._values.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]
        value = loader()
        self._values[key] = (signature, value)
        return value


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _production_state(path: Path) -> dict[str, Any]:
    value = _json_object(path)
    for key in ("virtual_balance", "realized_pnl", "position_quantity"):
        _decimal(value, key)
    _decimal(value, "entry_price", optional=True)
    int(value.get("closed_trades", 0))
    return value


def _v2_state(path: Path) -> dict[str, Any]:
    value = _json_object(path)
    for key in ("equity", "cash", "realised_pnl", "unrealised_pnl", "quantity"):
        _decimal(value, key)
    _decimal(value, "weighted_average_entry", optional=True)
    _decimal(value, "last_score", optional=True)
    return value


def _runtime_state(path: Path) -> dict[str, Any]:
    value = _json_object(path)
    _decimal(value, "maximum_drawdown_percent", optional=True)
    counters = value.get("counters")
    if not isinstance(counters, dict):
        raise ValueError("runtime counters must be an object")
    for key in ("stale_data_rejections", "api_error_halts", "risk_limit_halts"):
        number = int(counters.get(key, 0))
        if number < 0:
            raise ValueError(f"negative runtime counter {key}")
    return value


def _decision_record(path: Path) -> dict[str, Any]:
    value = _last_jsonl_object(path)
    price = _decimal(value, "price")
    if price is None or price <= 0:
        raise ValueError("decision price must be positive")
    int(value["candle_timestamp"])
    return value


def _canonical_record(path: Path) -> dict[str, Any]:
    value = _last_jsonl_object(path)
    int(value["candle_timestamp"])
    _decimal(value, "score_total")
    if not isinstance(value.get("feature_version"), str):
        raise ValueError("canonical feature version is missing")
    return value


def _last_jsonl_object(path: Path, *, chunk_size: int = 65536) -> dict[str, Any]:
    """Read the newest complete JSONL record without scanning the whole file."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        data = b""
        while position > 0 and len(data) <= chunk_size * 4:
            take = min(chunk_size, position)
            position -= take
            handle.seek(position)
            data = handle.read(take) + data
            lines = data.splitlines()
            if position == 0 or len(lines) > 1:
                for raw in reversed(lines):
                    if not raw.strip():
                        continue
                    value = json.loads(raw.decode("utf-8"))
                    if not isinstance(value, dict):
                        raise ValueError("JSONL record must be an object")
                    return value
        raise ValueError("JSONL has no readable record")


def _decimal(payload: dict[str, Any], key: str, *, optional: bool = False) -> Decimal | None:
    value = payload.get(key)
    if value is None and optional:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric field {key}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite numeric field {key}")
    return result


def _safe_version(value: str) -> str:
    if not SAFE_VERSION.fullmatch(value):
        raise ValueError("invalid build version value")
    return value


def _journal_stats(path: Path, *, boundary: int | None = None) -> dict[str, Decimal | int]:
    if path.stat().st_size > MAX_JOURNAL_BYTES:
        raise ValueError("journal exceeds exporter scan limit")
    closed = winning = 0
    max_drawdown = Decimal("0")
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"corrupt journal line {line_number}") from exc
            if boundary is not None:
                try:
                    if int(row.get("candle_timestamp", -1)) < boundary:
                        continue
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid journal timestamp at line {line_number}") from exc
                drawdown = _decimal(row, "max_drawdown_pct", optional=True)
                if drawdown is not None:
                    max_drawdown = max(max_drawdown, drawdown)
                trade = row.get("closed_trade")
                if isinstance(trade, dict):
                    closed += 1
                    pnl = _decimal(trade, "net_pnl")
                    winning += int(pnl is not None and pnl > 0)
            else:
                pnl = _decimal(row, "net_pnl", optional=True)
                if pnl is not None:
                    closed += 1
                    winning += int(pnl > 0)
    return {"closed": closed, "winning": winning, "max_drawdown_pct": max_drawdown}


class CryptoMetricsCollector:
    def __init__(self, paths: ExporterPaths, *, clock: Callable[[], datetime] | None = None) -> None:
        self.paths = paths
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cache = FileCache()
        self.errors_total = 0
        self._lock = threading.Lock()

    def _read(self, source: str, path: Path, kind: str, loader: Callable[[], Any]) -> Any | None:
        try:
            return self.cache.get(path, kind, loader)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            self.errors_total += 1
            LOGGER.warning("metrics source %s unavailable (%s)", source, type(exc).__name__)
            return None

    def collect(self) -> str:
        with self._lock:
            return self._collect_locked()

    def _collect_locked(self) -> str:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        metrics = MetricSet()
        metrics.add("crypto_metrics_exporter_up", 1)
        metrics.add("crypto_build_info", 1, {
            "strategy_logic_version": _safe_version(STRATEGY_LOGIC_VERSION),
            "feature_version": _safe_version(FEATURE_VERSION),
            "execution_policy_version": _safe_version(EXECUTION_POLICY_VERSION),
            "ledger_schema_version": _safe_version(LEDGER_SCHEMA_VERSION),
        })

        production = self._read(
            "production_state", self.paths.production_state, "json",
            lambda: _production_state(self.paths.production_state),
        )
        runtime = self._read(
            "runtime_state", self.paths.runtime_state, "json",
            lambda: _runtime_state(self.paths.runtime_state),
        )
        decision = self._read(
            "production_decisions", self.paths.production_decisions, "tail",
            lambda: _decision_record(self.paths.production_decisions),
        )
        canonical = self._read(
            "canonical_features", self.paths.canonical_features, "tail",
            lambda: _canonical_record(self.paths.canonical_features),
        )
        production_stats = self._read(
            "production_journal", self.paths.production_journal, "stats",
            lambda: _journal_stats(self.paths.production_journal),
        )
        v2 = self._read(
            "v2_state", self.paths.v2_state, "json",
            lambda: _v2_state(self.paths.v2_state),
        )
        v2_stats = self._read(
            "v2_journal", self.paths.v2_journal, "forward_stats",
            lambda: _journal_stats(
                self.paths.v2_journal,
                boundary=V2_CORRECTNESS_FORWARD_TIMESTAMP,
            ),
        )

        price: Decimal | None = None
        if decision is not None:
            price = _decimal(decision, "price", optional=True)
            if price is not None and price <= 0:
                self.errors_total += 1
                LOGGER.warning("metrics source production_decisions unavailable (invalid price)")
                price = None
            elif price is not None:
                metrics.add("crypto_eth_price_usdt", price)

        production_price = price
        if production is not None and decision is not None:
            state_timestamp = production.get("last_processed_candle_timestamp")
            decision_timestamp = decision.get("candle_timestamp")
            if (
                state_timestamp is not None
                and decision_timestamp is not None
                and int(state_timestamp) != int(decision_timestamp)
            ):
                self.errors_total += 1
                LOGGER.warning("production state and decision timestamps do not match")
                production_price = None

        production_equity: Decimal | None = None
        production_ok = production is not None and production_price is not None
        if production is not None:
            cash = _decimal(production, "virtual_balance")
            realized = _decimal(production, "realized_pnl")
            quantity = _decimal(production, "position_quantity")
            entry = _decimal(production, "entry_price", optional=True)
            assert cash is not None and realized is not None and quantity is not None
            metrics.add("crypto_production_cash_usdt", cash)
            metrics.add("crypto_production_realized_pnl_usdt", realized)
            metrics.add("crypto_production_position_open", int(quantity > 0))
            metrics.add("crypto_production_position_quantity_eth", quantity)
            metrics.add("crypto_production_closed_trades_total", int(production.get("closed_trades", 0)))
            if quantity > 0 and entry is not None:
                metrics.add("crypto_production_position_entry_price_usdt", entry)
                opened_at = production.get("opened_at")
                if isinstance(opened_at, str):
                    try:
                        opened = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
                        if opened.tzinfo is not None:
                            metrics.add("crypto_production_position_age_seconds", max(0, (now - opened).total_seconds()))
                    except ValueError:
                        self.errors_total += 1
                        LOGGER.warning("metrics source production_state has invalid opened_at")
            if production_price is not None:
                market_value = quantity * production_price
                production_equity = cash + market_value
                total_pnl = production_equity - INITIAL_BALANCE
                unrealized = total_pnl - realized
                metrics.add("crypto_production_position_market_value_usdt", market_value)
                metrics.add("crypto_production_equity_usdt", production_equity)
                metrics.add("crypto_production_unrealized_pnl_usdt", unrealized)
                metrics.add("crypto_production_total_pnl_usdt", total_pnl)
                metrics.add("crypto_production_total_return_ratio", total_pnl / INITIAL_BALANCE)
                if quantity > 0 and entry is not None and entry > 0:
                    metrics.add("crypto_production_position_unrealized_return_ratio", (production_price - entry) / entry)
        if production_stats is not None:
            metrics.add("crypto_production_winning_trades_total", int(production_stats["winning"]))
        if runtime is not None:
            maximum_drawdown = _decimal(runtime, "maximum_drawdown_percent", optional=True)
            if maximum_drawdown is not None:
                metrics.add("crypto_production_max_drawdown_ratio", maximum_drawdown / 100)

        v2_equity: Decimal | None = None
        if v2 is not None:
            v2_equity = _decimal(v2, "equity")
            v2_cash = _decimal(v2, "cash")
            v2_realized = _decimal(v2, "realised_pnl")
            v2_unrealized = _decimal(v2, "unrealised_pnl")
            v2_quantity = _decimal(v2, "quantity")
            v2_entry = _decimal(v2, "weighted_average_entry", optional=True)
            v2_score = _decimal(v2, "last_score", optional=True)
            assert all(value is not None for value in (v2_equity, v2_cash, v2_realized, v2_unrealized, v2_quantity))
            metrics.add("crypto_v2_equity_usdt", v2_equity)
            metrics.add("crypto_v2_cash_usdt", v2_cash)
            metrics.add("crypto_v2_realized_pnl_usdt", v2_realized)
            metrics.add("crypto_v2_unrealized_pnl_usdt", v2_unrealized)
            metrics.add("crypto_v2_total_pnl_usdt", v2_equity - INITIAL_BALANCE)
            metrics.add("crypto_v2_position_open", int(v2_quantity > 0))
            metrics.add("crypto_v2_position_quantity_eth", v2_quantity)
            if v2_entry is not None:
                metrics.add("crypto_v2_position_avg_entry_usdt", v2_entry)
            if v2_score is not None:
                metrics.add("crypto_v2_score", v2_score)
            pending = str(v2.get("pending_action") or "")
            metrics.add("crypto_v2_pending_entry", int(pending == "entry"))
            metrics.add("crypto_v2_pending_exit", int(pending == "exit"))
        if v2_stats is not None:
            closed = int(v2_stats["closed"])
            winning = int(v2_stats["winning"])
            metrics.add("crypto_v2_closed_trades_total", closed)
            metrics.add("crypto_v2_win_rate_ratio", winning / closed if closed else 0)
            metrics.add("crypto_v2_max_drawdown_ratio", Decimal(v2_stats["max_drawdown_pct"]) / 100)
        if production_equity is not None and v2_equity is not None:
            metrics.add("crypto_v2_vs_production_equity_delta_usdt", v2_equity - production_equity)

        last_processed: int | None = None
        try:
            last_processed = int(self.paths.last_candle.read_text(encoding="utf-8").strip())
            if last_processed < 0:
                raise ValueError("negative timestamp")
        except (OSError, ValueError):
            self.errors_total += 1
            LOGGER.warning("metrics source last_candle unavailable")
        market_data_ok = False
        if last_processed is not None:
            interval = 3600
            expected = int(now.timestamp()) // interval * interval - interval
            lag = max(0, expected - last_processed) / interval
            market_data_ok = lag <= 1
            metrics.add("crypto_market_lag_candles", lag)
            metrics.add("crypto_market_data_ok", int(market_data_ok))
        else:
            metrics.add("crypto_market_data_ok", 0)

        canonical_ready = False
        if canonical is not None:
            try:
                canonical_timestamp = int(canonical["candle_timestamp"])
                canonical_score = _decimal(canonical, "score_total")
                canonical_ready = (
                    last_processed is not None
                    and canonical_timestamp == last_processed
                    and canonical.get("feature_version") == FEATURE_VERSION
                )
                metrics.add("crypto_canonical_snapshot_ready", int(canonical_ready))
                metrics.add("crypto_canonical_candle_timestamp_seconds", canonical_timestamp)
                assert canonical_score is not None
                metrics.add("crypto_canonical_score", canonical_score)
            except (KeyError, TypeError, ValueError):
                self.errors_total += 1
                LOGGER.warning("metrics source canonical_features unavailable (invalid record)")
        else:
            metrics.add("crypto_canonical_snapshot_ready", 0)

        active_halt = False
        api_ok = False
        if runtime is not None:
            counters = runtime.get("counters")
            if not isinstance(counters, dict):
                self.errors_total += 1
                LOGGER.warning("metrics source runtime_state unavailable (invalid counters)")
            else:
                metrics.add("crypto_stale_events_total", int(counters.get("stale_data_rejections", 0)))
                metrics.add("crypto_api_errors_total", int(counters.get("api_error_halts", 0)))
                metrics.add("crypto_risk_halts_total", int(counters.get("risk_limit_halts", 0)))
            halt_reason = runtime.get("active_halt_reason")
            active_halt = bool(halt_reason)
            api_ok = halt_reason != "api_error"
            metrics.add("crypto_active_halt", int(active_halt))
            metrics.add("crypto_api_ok", int(api_ok))
        else:
            metrics.add("crypto_api_ok", 0)

        trading_ok = production_ok and market_data_ok and canonical_ready and api_ok and not active_halt
        metrics.add("crypto_trading_health_ok", int(trading_ok))
        metrics.add("crypto_metrics_exporter_errors_total", self.errors_total)
        return metrics.render()


class MetricsHandler(BaseHTTPRequestHandler):
    collector: CryptoMetricsCollector

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path not in {"/metrics", "/-/healthy"}:
            self.send_error(404)
            return
        if self.path == "/-/healthy":
            body = b"ok\n"
            content_type = "text/plain; charset=utf-8"
        else:
            body = self.collector.collect().encode("utf-8")
            content_type = "text/plain; version=0.0.4; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.debug("http request: " + format, *args)


def create_server(host: str, port: int, collector: CryptoMetricsCollector) -> ThreadingHTTPServer:
    if host != DEFAULT_HOST:
        raise ValueError("metrics exporter must bind only to 127.0.0.1")
    handler = type("BoundMetricsHandler", (MetricsHandler,), {"collector": collector})
    return ThreadingHTTPServer((host, port), handler)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Read-only crypto-bot Prometheus exporter")
    result.add_argument("--host", default=DEFAULT_HOST, choices=(DEFAULT_HOST,))
    result.add_argument("--port", type=int, default=DEFAULT_PORT)
    result.add_argument("--project-root", type=Path, default=Path("/opt/crypto-bot"))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    collector = CryptoMetricsCollector(ExporterPaths.from_root(args.project_root))
    server = create_server(args.host, args.port, collector)
    LOGGER.info("serving read-only metrics on http://%s:%s/metrics", args.host, server.server_port)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
