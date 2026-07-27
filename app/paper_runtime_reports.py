from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.runtime_health import read_jsonl_safely
from app.trade_journal import TradeJournalEntry
from app.trading_controller_store import TradingControllerStateStore

ENTRY_ACTIONS = {"open_long", "open_short"}


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_datetime(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("journal timestamps must include timezone")
    return result


def load_period_data(state_path: Path, journal_path: Path, shadow_path: Path, start: datetime, end: datetime) -> tuple[Any, list[TradeJournalEntry], list[dict[str, Any]]]:
    state = TradingControllerStateStore(state_path).load()
    trades, _ = read_jsonl_safely(journal_path, parser=TradeJournalEntry.from_dict) if journal_path.exists() else ([], False)
    shadows, _ = read_jsonl_safely(shadow_path) if shadow_path.exists() else ([], False)
    trades = [item for item in trades if start <= parse_datetime(item.closed_at) < end]
    shadows = [item for item in shadows if start.timestamp() <= int(item["candle_timestamp"]) < end.timestamp()]
    return state, trades, shadows


def shadow_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [r for r in records if r.get("baseline_signal") in ENTRY_ACTIONS]
    reasons = Counter(r.get("blocked_reason") for r in evaluated if r.get("blocked") and r.get("blocked_reason"))
    same = sum(r.get("baseline_signal") == r.get("filtered_signal") for r in records)
    blocked = sum(bool(r.get("blocked")) for r in evaluated)
    return {
        "evaluations": len(evaluated), "allowed_entries": sum(r.get("allowed") is True for r in evaluated),
        "blocked_entries": blocked, "blocked_reasons": dict(sorted(reasons.items())),
        "detector_errors": sum(bool(r.get("detector_error")) for r in records),
        "baseline_only_decisions": sum(r.get("baseline_signal") in ENTRY_ACTIONS and r.get("filtered_signal") not in ENTRY_ACTIONS for r in records),
        "filtered_only_decisions": sum(r.get("filtered_signal") in ENTRY_ACTIONS and r.get("baseline_signal") not in ENTRY_ACTIONS for r in records),
        "agreement_percentage": same / len(records) * 100 if records else 0.0,
        "market_regimes": dict(sorted(Counter(r.get("regime") or "unknown" for r in records).items())),
    }


def trade_summary(trades: list[TradeJournalEntry]) -> dict[str, Any]:
    net = [t.net_pnl for t in trades]
    gross_profit = sum((v for v in net if v > 0), Decimal("0"))
    gross_loss = sum((v for v in net if v < 0), Decimal("0"))
    fees = sum((t.total_fee for t in trades), Decimal("0"))
    peak = Decimal("0")
    equity = Decimal("0")
    max_dd = Decimal("0")
    durations = [(parse_datetime(t.closed_at) - parse_datetime(t.opened_at)).total_seconds() for t in trades]
    for value in net:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trade_count": len(trades), "entries": len(trades), "exits": len(trades),
        "winning_trades": sum(v > 0 for v in net), "losing_trades": sum(v < 0 for v in net),
        "win_rate": sum(v > 0 for v in net) / len(net) * 100 if net else 0.0,
        "realised_pnl": str(sum(net, Decimal("0"))), "gross_profit": str(gross_profit),
        "gross_loss": str(gross_loss), "fees": str(fees),
        "profit_factor": float(gross_profit / abs(gross_loss)) if gross_loss else None,
        "maximum_drawdown": str(max_dd), "average_trade": str(sum(net, Decimal("0")) / len(net)) if net else "0",
        "best_trade": str(max(net)) if net else None, "worst_trade": str(min(net)) if net else None,
        "average_duration_seconds": sum(durations) / len(durations) if durations else None,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [f"{report['report_type'].upper()} PAPER REPORT", f"Period: {report['period_start']} .. {report['period_end']}"]
    for key, value in report.items():
        if key not in {"report_type", "period_start", "period_end"}:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], json_output: Path | None, text_output: Path | None) -> None:
    if json_output:
        atomic_write(json_output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if text_output:
        atomic_write(text_output, render_text(report))
