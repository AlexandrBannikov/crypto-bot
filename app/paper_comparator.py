from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

from app.account_snapshot import calculate_account_snapshot, market_from_decisions
from app.comparison_semantics import candidate_advantage, candidate_delta, max_drawdown_percent
from app.candidate_runtime import CandidateStateStore
from app.runtime_health import read_jsonl_safely
from app.trade_journal import TradeJournalEntry
from app.trading_controller_store import TradingControllerStateStore


CATEGORIES = (
    "BOTH_HOLD",
    "BOTH_ENTER",
    "BOTH_EXIT",
    "PRODUCTION_ENTER_CANDIDATE_HOLD",
    "PRODUCTION_ENTER_CANDIDATE_WAIT",
    "CANDIDATE_ENTER_PRODUCTION_HOLD",
    "PRODUCTION_EXIT_CANDIDATE_HOLD",
    "CANDIDATE_EXIT_PRODUCTION_HOLD",
    "DIFFERENT_EXIT_REASON",
    "MISSING_PRODUCTION_DECISION",
    "MISSING_CANDIDATE_DECISION",
    "STATE_MISMATCH",
    "ERROR",
)
AGREEMENT_CATEGORIES = {"BOTH_HOLD", "BOTH_ENTER", "BOTH_EXIT"}
PERIODS = ("today", "last_24h", "since_candidate_start", "all_available")
NA = "N/A"


@dataclass(frozen=True, slots=True)
class ComparisonPaths:
    production_state: Path
    production_trades: Path
    production_decisions: Path
    candidate_state: Path
    candidate_trades: Path
    candidate_decisions: Path
    production_runtime_summary: Path | None = None
    candidate_runtime_summary: Path | None = None


def _iso(timestamp: int, zone: ZoneInfo) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(zone).isoformat()


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _read_rows(path: Path, *, parser=None) -> tuple[list[Any], list[str]]:
    if not path.exists():
        return [], [f"missing: {path}"]
    rows, ignored = read_jsonl_safely(path, parser=parser)
    warnings = [f"incomplete final line ignored: {path}"] if ignored else []
    return rows, warnings


def _read_summary(path: Path | None, name: str) -> tuple[dict[str, Any], list[str]]:
    if path is None:
        return {}, []
    if not path.exists():
        return {}, [f"{name} runtime summary missing: {path}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} runtime summary is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} runtime summary is not an object")
    return value, []


def _validate_decisions(rows: list[dict[str, Any]], name: str) -> list[str]:
    errors: list[str] = []
    timestamps: list[int] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"{name} decision {index} is not an object")
            continue
        try:
            timestamps.append(int(row["candle_timestamp"]))
        except (KeyError, TypeError, ValueError):
            errors.append(f"{name} decision {index} has invalid candle_timestamp")
    duplicate = sorted(ts for ts, count in Counter(timestamps).items() if count > 1)
    if duplicate:
        errors.append(f"{name} duplicate candle timestamp(s): {duplicate}")
    if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
        errors.append(f"{name} decision timestamps are not strictly monotonic")
    return errors


def _decision_action(row: dict[str, Any], candidate: bool) -> str:
    if candidate:
        raw = row.get("decision")
        if raw is None:
            return "ERROR"
        action = str(raw).upper()
        return {
            "ENTER": "ENTER",
            "EXIT": "EXIT",
            "HOLD": "HOLD",
            "WAIT_PULLBACK": "WAIT",
            "CANCEL_PULLBACK": "HOLD",
        }.get(action, "ERROR")
    raw = row.get("effective_action")
    if raw is None:
        raw = row.get("execution_signal")
    if raw is None:
        return "ERROR"
    return {
        "open_long": "ENTER",
        "open_short": "ENTER",
        "close_long": "EXIT",
        "close_short": "EXIT",
        "hold": "HOLD",
    }.get(str(raw).lower(), "ERROR")


def _reason(row: dict[str, Any], candidate: bool) -> str:
    if candidate:
        return str(row.get("reason") or "none")
    return str(
        row.get("exit_reason")
        or row.get("blocked_reason")
        or row.get("shadow_block_reason")
        or row.get("reason")
        or "none"
    )


def _position(row: dict[str, Any], candidate: bool) -> str | None:
    value = row.get("position_after" if candidate else "position_state_after")
    if value is None:
        return None
    normalized = str(value).upper()
    return "LONG" if normalized in {"LONG", "OPEN", "OPEN_LONG"} else "FLAT"


def _category(production: dict[str, Any], candidate: dict[str, Any]) -> str:
    prod = _decision_action(production, False)
    cand = _decision_action(candidate, True)
    if "ERROR" in {prod, cand}:
        return "ERROR"
    prod_position = _position(production, False)
    cand_position = _position(candidate, True)
    if (
        prod_position is not None
        and cand_position is not None
        and prod_position != cand_position
        and prod == cand
    ):
        return "STATE_MISMATCH"
    if prod == cand == "HOLD":
        return "BOTH_HOLD"
    if prod == cand == "ENTER":
        return "BOTH_ENTER"
    if prod == cand == "EXIT":
        return (
            "BOTH_EXIT"
            if _reason(production, False) == _reason(candidate, True)
            else "DIFFERENT_EXIT_REASON"
        )
    if prod == "ENTER" and cand == "WAIT":
        return "PRODUCTION_ENTER_CANDIDATE_WAIT"
    if prod == "ENTER" and cand == "HOLD":
        return "PRODUCTION_ENTER_CANDIDATE_HOLD"
    if cand == "ENTER" and prod == "HOLD":
        return "CANDIDATE_ENTER_PRODUCTION_HOLD"
    if prod == "EXIT" and cand in {"HOLD", "WAIT"}:
        return "PRODUCTION_EXIT_CANDIDATE_HOLD"
    if cand == "EXIT" and prod == "HOLD":
        return "CANDIDATE_EXIT_PRODUCTION_HOLD"
    return "STATE_MISMATCH"


def _explanation(category: str) -> str:
    return {
        "PRODUCTION_ENTER_CANDIDATE_WAIT": "Production entered while candidate waited for pullback.",
        "PRODUCTION_ENTER_CANDIDATE_HOLD": "Production entered while candidate held.",
        "CANDIDATE_ENTER_PRODUCTION_HOLD": "Candidate entered while production held.",
        "PRODUCTION_EXIT_CANDIDATE_HOLD": "Production exited while candidate held.",
        "CANDIDATE_EXIT_PRODUCTION_HOLD": "Candidate exited while production held.",
        "DIFFERENT_EXIT_REASON": "Both exited, but for different reasons.",
        "MISSING_PRODUCTION_DECISION": "Production has no record for this candle.",
        "MISSING_CANDIDATE_DECISION": "Candidate has no record for this candle.",
        "STATE_MISMATCH": "Decision or resulting position state differs.",
        "ERROR": "A decision record could not be interpreted.",
    }.get(category, category.replace("_", " ").title())


def _period_bounds(
    period: str,
    *,
    now: datetime,
    zone: ZoneInfo,
    candidate_start: int | None,
) -> tuple[int | None, int | None]:
    if period not in PERIODS:
        raise ValueError(f"unsupported comparison period: {period}")
    if period == "all_available":
        return None, None
    if period == "since_candidate_start":
        return candidate_start, None
    if period == "last_24h":
        return int((now - timedelta(hours=24)).timestamp()), int(now.timestamp())
    local = now.astimezone(zone)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp()), int(now.timestamp())


def _in_period(timestamp: int, start: int | None, end: int | None) -> bool:
    return (start is None or timestamp >= start) and (end is None or timestamp < end)


def _trade_timestamp(trade: TradeJournalEntry) -> int:
    return int(datetime.fromisoformat(trade.closed_at.replace("Z", "+00:00")).timestamp())


def _runtime_freshness(
    last_candle: int | None, now: datetime, *, max_age_seconds: int = 7200
) -> tuple[str, str]:
    if last_candle is None:
        return NA, "WARNING"
    age = max(0, int(now.timestamp()) - last_candle)
    return f"{age}s", "OK" if age <= max_age_seconds else "WARNING"


def _metrics(
    state: Any | None,
    trades: list[TradeJournalEntry],
    decisions: list[dict[str, Any]],
    *,
    candidate: bool,
    last_candle: int | None,
    now: datetime,
) -> dict[str, Any]:
    if state is None:
        return {
            key: NA
            for key in (
                "balance", "cumulative_pnl", "return_percent", "open_position",
                "position_size", "entries", "exits", "closed_trades",
                "winning_trades", "losing_trades", "win_rate_percent",
                "gross_profit", "gross_loss", "profit_factor", "fees",
                "max_drawdown_percent", "signals_decisions",
                "last_processed_candle", "runtime_freshness", "health_status",
                "cash_balance", "equity", "realized_pnl", "unrealized_pnl",
                "total_pnl", "realized_return_pct", "total_return_pct",
                "entry_price", "current_price", "position_age_seconds",
                "distance_to_stop_value", "distance_to_stop_pct",
            )
        } | {"data_status": "unavailable"}
    controller = state.controller if candidate else state
    wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))
    if not trades:
        win_rate: float | str = NA
        profit_factor: float | str = NA
        drawdown: float | str = NA
    else:
        win_rate = len(wins) / len(trades) * 100
        if losses:
            profit_factor = float(gross_profit / abs(gross_loss))
        elif wins:
            profit_factor = math.inf
        else:
            profit_factor = NA
        balances = [trade.virtual_balance_after for trade in trades]
        initial = balances[0] - trades[0].net_pnl
        drawdown = float(max_drawdown_percent([initial, *balances]))
    actions = [_decision_action(row, candidate) for row in decisions]
    freshness, health = _runtime_freshness(last_candle, now)
    initial_balance = Decimal("1000")
    market = market_from_decisions(decisions)
    portfolio = calculate_account_snapshot(
        initial_balance=initial_balance,
        cash_balance=controller.virtual_balance,
        position_side="LONG" if controller.has_open_position else "FLAT",
        position_quantity=controller.position_quantity,
        entry_price=controller.entry_price,
        current_price=market["price"],
        realized_pnl=controller.realized_pnl,
        opened_at=controller.opened_at,
        now=now,
        stop_loss_price=controller.stop_loss,
    )
    pnl = controller.realized_pnl
    return {
        "snapshot": portfolio.to_dict(),
        "market": market,
        "cash_balance": str(portfolio.cash_balance),
        "equity": str(portfolio.equity) if portfolio.equity is not None else NA,
        "realized_pnl": str(portfolio.realized_pnl),
        "unrealized_pnl": (
            str(portfolio.unrealized_pnl)
            if portfolio.unrealized_pnl is not None else NA
        ),
        "total_pnl": str(portfolio.total_pnl) if portfolio.total_pnl is not None else NA,
        "realized_return_pct": str(portfolio.realized_return_pct),
        "total_return_pct": (
            str(portfolio.total_return_pct)
            if portfolio.total_return_pct is not None else NA
        ),
        "entry_price": str(portfolio.entry_price) if portfolio.entry_price is not None else NA,
        "current_price": str(portfolio.current_price) if portfolio.current_price is not None else NA,
        "position_age_seconds": (
            portfolio.position_age_seconds
            if portfolio.position_age_seconds is not None else NA
        ),
        "distance_to_stop_value": (
            str(portfolio.distance_to_stop_value)
            if portfolio.distance_to_stop_value is not None else NA
        ),
        "distance_to_stop_pct": (
            str(portfolio.distance_to_stop_pct)
            if portfolio.distance_to_stop_pct is not None else NA
        ),
        "balance": str(controller.virtual_balance),
        "cumulative_pnl": str(pnl),
        "return_percent": str(pnl / initial_balance * Decimal("100")),
        "open_position": bool(controller.has_open_position),
        "position_size": str(controller.position_quantity),
        "entries": actions.count("ENTER"),
        "exits": actions.count("EXIT"),
        "closed_trades": len(trades),
        "winning_trades": len(wins) if trades else NA,
        "losing_trades": len(losses) if trades else NA,
        "win_rate_percent": win_rate,
        "gross_profit": str(gross_profit) if trades else NA,
        "gross_loss": str(gross_loss) if trades else NA,
        "profit_factor": profit_factor,
        "fees": str(sum((trade.total_fee for trade in trades), Decimal("0"))),
        "max_drawdown_percent": drawdown,
        "signals_decisions": len(decisions),
        "last_processed_candle": last_candle if last_candle is not None else NA,
        "runtime_freshness": freshness,
        "health_status": health,
        "data_status": "ok" if trades else "insufficient data",
    }


def compare_paper_runtimes(
    *,
    production_state: Path,
    production_trades: Path,
    production_decisions: Path,
    candidate_state: Path,
    candidate_trades: Path,
    candidate_decisions: Path,
    production_runtime_summary: Path | None = None,
    candidate_runtime_summary: Path | None = None,
    period: str = "since_candidate_start",
    now: datetime | None = None,
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    zone = ZoneInfo(timezone_name)
    errors: list[str] = []
    warnings: list[str] = []
    prod_state = cand_state = None
    try:
        if not production_state.exists():
            raise ValueError("production state is missing")
        prod_state = TradingControllerStateStore(production_state).load()
    except (OSError, ValueError) as exc:
        errors.append(f"production data unavailable: {exc}")
    try:
        if not candidate_state.exists():
            raise ValueError("candidate state is missing")
        cand_state = CandidateStateStore(candidate_state).load()
    except (OSError, ValueError) as exc:
        warnings.append(f"Candidate data unavailable: {exc}")
    prod_summary: dict[str, Any] = {}
    cand_summary: dict[str, Any] = {}
    try:
        prod_summary, notices = _read_summary(
            production_runtime_summary, "production"
        )
        warnings.extend(notices)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        cand_summary, notices = _read_summary(
            candidate_runtime_summary, "candidate"
        )
        warnings.extend(notices)
    except ValueError as exc:
        warnings.append(f"Candidate data unavailable: {exc}")

    def load(path: Path, name: str, parser=None):
        try:
            rows, notices = _read_rows(path, parser=parser)
            warnings.extend(f"{name}: {notice}" for notice in notices)
            return rows
        except (OSError, ValueError) as exc:
            target = errors if name.startswith("production") else warnings
            target.append(f"{name} unavailable: {exc}")
            return []

    prod_trade_rows = load(production_trades, "production trade journal", TradeJournalEntry.from_dict)
    cand_trade_rows = load(candidate_trades, "candidate trade journal", TradeJournalEntry.from_dict)
    prod_rows = load(production_decisions, "production decision journal")
    cand_rows = load(candidate_decisions, "candidate decision journal")
    validation = _validate_decisions(prod_rows, "production") + _validate_decisions(cand_rows, "candidate")
    if validation:
        warnings.extend(validation)
    prod_rows = [
        row for row in prod_rows
        if isinstance(row, dict) and _valid_timestamp(row.get("candle_timestamp"))
    ]
    cand_rows = [
        row for row in cand_rows
        if isinstance(row, dict) and _valid_timestamp(row.get("candle_timestamp"))
    ]

    candidate_start = None
    if cand_state is not None:
        candidate_start = cand_state.baseline_candle
    if candidate_start is None and cand_rows:
        candidate_start = int(cand_rows[0]["candle_timestamp"])
    start, end = _period_bounds(
        period, now=current, zone=zone, candidate_start=candidate_start
    )
    prod_rows = [
        row for row in prod_rows
        if _in_period(int(row["candle_timestamp"]), start, end)
    ]
    cand_rows = [
        row for row in cand_rows
        if _in_period(int(row["candle_timestamp"]), start, end)
    ]
    prod_trade_rows = [
        trade for trade in prod_trade_rows
        if _in_period(_trade_timestamp(trade), start, end)
    ]
    cand_trade_rows = [
        trade for trade in cand_trade_rows
        if _in_period(_trade_timestamp(trade), start, end)
    ]

    prod_by_ts = {int(row["candle_timestamp"]): row for row in prod_rows}
    cand_by_ts = {int(row["candle_timestamp"]): row for row in cand_rows}
    counts = {name: 0 for name in CATEGORIES}
    differences: list[dict[str, Any]] = []
    common = sorted(set(prod_by_ts) & set(cand_by_ts))
    for timestamp in common:
        production = prod_by_ts[timestamp]
        candidate = cand_by_ts[timestamp]
        category = _category(production, candidate)
        counts[category] += 1
        if category not in AGREEMENT_CATEGORIES:
            differences.append(
                _difference(timestamp, production, candidate, category, zone)
            )
    for timestamp in sorted(set(prod_by_ts) - set(cand_by_ts)):
        counts["MISSING_CANDIDATE_DECISION"] += 1
        differences.append(
            _difference(timestamp, prod_by_ts[timestamp], None, "MISSING_CANDIDATE_DECISION", zone)
        )
    for timestamp in sorted(set(cand_by_ts) - set(prod_by_ts)):
        counts["MISSING_PRODUCTION_DECISION"] += 1
        differences.append(
            _difference(timestamp, None, cand_by_ts[timestamp], "MISSING_PRODUCTION_DECISION", zone)
        )
    matched = len(common)
    agreements = sum(counts[name] for name in AGREEMENT_CATEGORIES)
    agreement_rate: float | str = agreements / matched * 100 if matched else NA
    prod_last = _summary_timestamp(
        prod_summary, "last_processed_closed_candle", max(prod_by_ts, default=None)
    )
    cand_last = _summary_timestamp(
        cand_summary,
        "last_processed_candle",
        cand_state.last_processed_candle if cand_state is not None else max(cand_by_ts, default=None),
    )
    production_metrics = _metrics(
        prod_state, prod_trade_rows, prod_rows, candidate=False,
        last_candle=prod_last, now=current,
    )
    candidate_metrics = _metrics(
        cand_state, cand_trade_rows, cand_rows, candidate=True,
        last_candle=cand_last, now=current,
    )
    production_metrics["health_status"] = _summary_health(
        prod_summary, production_metrics["health_status"], "active_halt_reason"
    )
    candidate_metrics["health_status"] = _summary_health(
        cand_summary, candidate_metrics["health_status"], "active_halt"
    )
    if prod_by_ts and cand_by_ts and not common:
        warnings.append("production and candidate decision timestamps are not comparable")
    status = "CRITICAL" if errors else "WARNING" if warnings else "OK"
    report = {
        "schema_version": 2,
        "generated_at": current.astimezone(timezone.utc).isoformat(),
        "timezone": timezone_name,
        "period": {
            "name": period,
            "start": _iso(start, zone) if start is not None else None,
            "end": _iso(end, zone) if end is not None else None,
            "candidate_start": _iso(candidate_start, zone) if candidate_start is not None else None,
        },
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "production": production_metrics,
        "candidate": candidate_metrics,
        "deltas": _deltas(production_metrics, candidate_metrics),
        "market": production_metrics.get("market", {}),
        "health": {
            "overall": status,
            "production": production_metrics["health_status"],
            "candidate": candidate_metrics["health_status"],
            "report_generated_at": current.astimezone(timezone.utc).isoformat(),
        },
        "decisions": {
            "matched_candles": matched,
            "agreement_rate_percent": agreement_rate,
            "unmatched_records": counts["MISSING_PRODUCTION_DECISION"] + counts["MISSING_CANDIDATE_DECISION"],
            "difference_count": len(differences),
            "categories": counts,
        },
        "recent_differences": differences[-20:],
        "conclusion": (
            "Недостаточно данных для оценки."
            if matched == 0 or not prod_trade_rows or not cand_trade_rows
            else "Candidate ahead on observed paper results, but sample is insufficient."
            if _as_decimal(candidate_metrics["cumulative_pnl"]) > _as_decimal(production_metrics["cumulative_pnl"])
            else "Недостаточно данных для оценки."
        ),
    }
    report["comparison"] = report["deltas"]
    report["decision_agreement"] = report["decisions"]
    # Keep the original public fields available for Telegram and older
    # automation while consumers migrate to the structured v2 sections.
    report.update(
        {
            "balance_difference": report["deltas"]["balance"],
            "pnl_difference": report["deltas"]["pnl"],
            "decision_divergences": len(differences),
            "candidate_pullback_confirmations": (
                cand_state.pullback_confirmations if cand_state is not None else 0
            ),
            "candidate_average_pullback_wait_bars": (
                cand_state.total_pullback_wait_bars / cand_state.pullback_confirmations
                if cand_state is not None and cand_state.pullback_confirmations
                else 0.0
            ),
            "divergence_categories": counts,
        }
    )
    report["production"]["pnl"] = report["production"]["cumulative_pnl"]
    report["candidate"]["pnl"] = report["candidate"]["cumulative_pnl"]
    return report


def _valid_timestamp(value: Any) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _summary_timestamp(
    summary: dict[str, Any], key: str, fallback: int | None
) -> int | None:
    value = summary.get(key)
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _summary_health(
    summary: dict[str, Any], freshness_health: str, halt_key: str
) -> str:
    if summary.get(halt_key):
        return "CRITICAL"
    if summary and freshness_health == "OK":
        return "OK"
    return freshness_health


def _difference(
    timestamp: int,
    production: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    category: str,
    zone: ZoneInfo,
) -> dict[str, Any]:
    source = candidate or production or {}
    return {
        "candle_timestamp": timestamp,
        "time": _iso(timestamp, zone),
        "close": source.get("close", source.get("price", NA)),
        "production_decision": _decision_action(production, False) if production else "MISSING",
        "candidate_decision": _decision_action(candidate, True) if candidate else "MISSING",
        "production_reason": _reason(production, False) if production else "missing decision",
        "candidate_reason": _reason(candidate, True) if candidate else "missing decision",
        "ema20": (candidate or {}).get("ema20", NA),
        "ema50": (candidate or {}).get("ema50", NA),
        "adx": (candidate or {}).get("adx", NA),
        "pullback_pending": (candidate or {}).get("pullback_pending", NA),
        "bars_waited": (candidate or {}).get("bars_waited", NA),
        "category": category,
        "explanation": _explanation(category),
    }


def _as_decimal(value: Any) -> Decimal:
    try:
        return _decimal(value)
    except Exception:
        return Decimal("0")


def _deltas(production: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    pairs = {
        "balance": ("balance", "balance"),
        "pnl": ("cumulative_pnl", "cumulative_pnl"),
        "return_percent": ("return_percent", "return_percent"),
        "equity": ("equity", "equity"),
        "total_pnl": ("total_pnl", "total_pnl"),
        "total_return_pct": ("total_return_pct", "total_return_pct"),
        "unrealized_pnl": ("unrealized_pnl", "unrealized_pnl"),
        "realized_pnl": ("realized_pnl", "realized_pnl"),
        "fees": ("fees", "fees"),
        "drawdown_percent": ("max_drawdown_percent", "max_drawdown_percent"),
        "trade_count": ("closed_trades", "closed_trades"),
    }
    result: dict[str, Any] = {}
    for output, (prod_key, cand_key) in pairs.items():
        left, right = production.get(prod_key), candidate.get(cand_key)
        if left == NA or right == NA:
            result[output] = NA
        else:
            result[output] = str(candidate_delta(_decimal(right), _decimal(left)))
    drawdown = result.get("drawdown_percent")
    result["drawdown_improvement_percent"] = (
        NA if drawdown == NA else str(candidate_advantage(
            _decimal(candidate["max_drawdown_percent"]),
            _decimal(production["max_drawdown_percent"]),
            lower_is_better=True,
        ))
    )
    return result


def write_comparison_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def render_comparison_markdown(report: dict[str, Any]) -> str:
    prod, cand, decisions = report["production"], report["candidate"], report["decisions"]
    lines = [
        "# Production vs Candidate",
        "",
        f"Period: {report['period']['name']} ({report['period']['start']} — {report['period']['end']})",
        f"Status: {report['status']}",
        "",
        "| Metric | Production | Candidate | Delta |",
        "|---|---:|---:|---:|",
    ]
    for label, key, delta in (
        ("Balance", "balance", "balance"),
        ("PnL", "cumulative_pnl", "pnl"),
        ("Return %", "return_percent", "return_percent"),
        ("Fees", "fees", "fees"),
        ("Max drawdown %", "max_drawdown_percent", "drawdown_percent"),
        ("Closed trades", "closed_trades", "trade_count"),
        ("Profit factor", "profit_factor", None),
    ):
        lines.append(
            f"| {label} | {prod[key]} | {cand[key]} | "
            f"{report['deltas'].get(delta, NA) if delta else NA} |"
        )
    lines.extend(
        [
            "",
            f"Matched candles: {decisions['matched_candles']}",
            f"Agreement rate: {decisions['agreement_rate_percent']}%",
            f"Unmatched records: {decisions['unmatched_records']}",
            "",
            "## Recent differences",
            "",
        ]
    )
    for item in report["recent_differences"][-20:]:
        lines.append(
            f"- {item['time']}: {item['production_decision']} / "
            f"{item['candidate_decision']} — {item['explanation']}"
        )
    lines.extend(["", report["conclusion"], ""])
    return "\n".join(lines)


def write_text_report(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
