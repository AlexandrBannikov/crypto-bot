from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import json
from pathlib import Path

from app.candidate_runtime import CandidateStateStore
from app.runtime_health import read_jsonl_safely
from app.trade_journal import TradeJournalEntry
from app.trading_controller_store import TradingControllerStateStore


@dataclass(frozen=True, slots=True)
class RuntimeMetrics:
    balance: str
    pnl: str
    return_percent: str
    open_position: bool
    entries: int
    exits: int
    closed_trades: int
    fees: str
    win_rate_percent: float
    profit_factor: float
    max_drawdown_percent: float
    signals: int


def _trade_metrics(path: Path) -> tuple[list[TradeJournalEntry], float, float, float]:
    if not path.exists():
        return [], 0.0, 0.0, 0.0
    trades, _ = read_jsonl_safely(path, parser=TradeJournalEntry.from_dict)
    wins = [float(item.net_pnl) for item in trades if item.net_pnl > 0]
    losses = [float(item.net_pnl) for item in trades if item.net_pnl < 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses else 0.0
    peak = Decimal("1000")
    drawdown = Decimal("0")
    for item in trades:
        balance = item.virtual_balance_after
        peak = max(peak, balance)
        if peak:
            drawdown = max(drawdown, (peak - balance) / peak * Decimal("100"))
    return trades, win_rate, profit_factor, float(drawdown)


def compare_paper_runtimes(
    *,
    production_state: Path,
    production_trades: Path,
    production_decisions: Path,
    candidate_state: Path,
    candidate_trades: Path,
    candidate_decisions: Path,
) -> dict:
    prod = TradingControllerStateStore(production_state).load()
    candidate = CandidateStateStore(candidate_state).load()
    prod_trades, prod_wr, prod_pf, prod_dd = _trade_metrics(production_trades)
    cand_trades, cand_wr, cand_pf, cand_dd = _trade_metrics(candidate_trades)
    prod_decisions = (
        read_jsonl_safely(production_decisions)[0]
        if production_decisions.exists() else []
    )
    cand_decisions = (
        read_jsonl_safely(candidate_decisions)[0]
        if candidate_decisions.exists() else []
    )
    prod_by_ts = {int(row["candle_timestamp"]): row for row in prod_decisions}
    cand_by_ts = {int(row["candle_timestamp"]): row for row in cand_decisions}
    categories = {
        "both_hold": 0,
        "production_enter_candidate_wait_block": 0,
        "candidate_enter_production_hold": 0,
        "both_enter": 0,
        "different_exit": 0,
        "state_mismatch_error": 0,
    }
    for timestamp in sorted(set(prod_by_ts) & set(cand_by_ts)):
        production_action = str(
            prod_by_ts[timestamp].get("effective_action")
            or prod_by_ts[timestamp].get("execution_signal")
            or "hold"
        ).lower()
        candidate_action = str(cand_by_ts[timestamp].get("decision", "HOLD")).upper()
        if production_action == "hold" and candidate_action in {"HOLD", "WAIT_PULLBACK", "CANCEL_PULLBACK"}:
            categories["both_hold"] += 1
        elif production_action == "open_long" and candidate_action in {"WAIT_PULLBACK", "HOLD", "CANCEL_PULLBACK"}:
            categories["production_enter_candidate_wait_block"] += 1
        elif production_action == "hold" and candidate_action == "ENTER":
            categories["candidate_enter_production_hold"] += 1
        elif production_action == "open_long" and candidate_action == "ENTER":
            categories["both_enter"] += 1
        elif (production_action == "close_long") != (candidate_action == "EXIT"):
            categories["different_exit"] += 1
    unmatched = len(set(prod_by_ts) ^ set(cand_by_ts))
    categories["state_mismatch_error"] = unmatched

    def metrics(state, trades, decisions, wr, pf, dd, entries=None, exits=None):
        balance = state.virtual_balance
        pnl = state.realized_pnl
        return RuntimeMetrics(
            str(balance), str(pnl), str(pnl / Decimal("1000") * 100),
            state.has_open_position,
            entries if entries is not None else sum(
                str(row.get("effective_action", "")).lower() == "open_long"
                for row in decisions
            ),
            exits if exits is not None else sum(
                str(row.get("effective_action", "")).lower() == "close_long"
                for row in decisions
            ),
            len(trades), str(state.total_fees), wr, pf, dd, len(decisions),
        )

    prod_metrics = metrics(prod, prod_trades, prod_decisions, prod_wr, prod_pf, prod_dd)
    cand_metrics = metrics(
        candidate.controller, cand_trades, cand_decisions, cand_wr, cand_pf,
        cand_dd, candidate.entries, candidate.exits,
    )
    divergent = sum(value for key, value in categories.items() if key not in {"both_hold", "both_enter"})
    average_wait = (
        candidate.total_pullback_wait_bars / candidate.pullback_confirmations
        if candidate.pullback_confirmations else 0.0
    )
    return {
        "production": asdict(prod_metrics),
        "candidate": asdict(cand_metrics),
        "balance_difference": str(
            Decimal(cand_metrics.balance) - Decimal(prod_metrics.balance)
        ),
        "pnl_difference": str(
            Decimal(cand_metrics.pnl) - Decimal(prod_metrics.pnl)
        ),
        "candidate_pullback_confirmations": candidate.pullback_confirmations,
        "candidate_average_pullback_wait_bars": average_wait,
        "decision_divergences": divergent,
        "divergence_categories": categories,
    }


def write_comparison_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
