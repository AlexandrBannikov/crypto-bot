"""Observation-only diagnostics for closed production PAPER trades."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import statistics
from typing import Any, Iterable, Sequence

from app.candle import Candle
from app.trade_journal import TradeJournalEntry


D = Decimal
COMPONENTS = (
    "trend", "ema_alignment", "adx", "pullback", "momentum",
    "volatility", "cost",
)


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                result.append(value)
    return result


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else D(str(value))


def _entry_candle(opened_at: str, interval_seconds: int) -> int:
    opened = int(datetime.fromisoformat(opened_at).timestamp())
    return opened // interval_seconds * interval_seconds - interval_seconds


def _score_observation(rows: Iterable[dict[str, Any]], candle: int) -> dict[str, Any] | None:
    matches = [
        row for row in rows
        if int(row.get("candle_timestamp", -1)) == candle
        or int(row.get("candle_close_timestamp", -1)) == candle
    ]
    return matches[-1] if matches else None


def _score_decision(row: dict[str, Any] | None, threshold: Decimal) -> str | None:
    if row is None:
        return None
    score = _decimal(row.get("score_total", row.get("signal_score", row.get("score"))))
    blocked = bool(row.get("hard_blocks") or row.get("blockers"))
    return "ENTER_LONG" if score is not None and score >= threshold and not blocked else "HOLD"


def _components(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("components") or row.get("score_components") or {}
    result = {}
    for name in COMPONENTS:
        value = source.get(name, source.get(f"{name}_score"))
        if isinstance(value, dict):
            value = value.get("score")
        result[name] = value
    return result


def _classification(*, net: Decimal, mfe: Decimal, mae: Decimal,
                    score65: str | None, score62: str | None) -> str:
    if score65 is None or score62 is None:
        return "insufficient"
    entry_issue = net < 0 and mfe < D("1") and mae <= D("-1") and score65 == score62 == "HOLD"
    # A visible excursion followed by a give-back of at least 75%.
    final_return = net
    exit_issue = mfe >= D("1") and final_return <= mfe * D("0.25")
    if entry_issue and exit_issue:
        return "mixed"
    if entry_issue:
        return "possible_entry_issue"
    if exit_issue:
        return "possible_exit_issue"
    return "insufficient"


def build_trade_card(
    trade: TradeJournalEntry,
    *,
    candles: Sequence[Candle],
    exit_candle_timestamp: int,
    timeframe_minutes: int = 60,
    production_decisions: Iterable[dict[str, Any]] = (),
    scored65_observations: Iterable[dict[str, Any]] = (),
    scored62_observations: Iterable[dict[str, Any]] = (),
    break_even_observations: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    interval = timeframe_minutes * 60
    entry_candle = _entry_candle(trade.opened_at, interval)
    eligible = sorted(
        (item for item in candles if entry_candle < item.timestamp <= exit_candle_timestamp),
        key=lambda item: item.timestamp,
    )
    if not eligible:
        raise ValueError("closed candles do not cover trade lifecycle")
    maximum = max(eligible, key=lambda item: item.high)
    minimum = min(eligible, key=lambda item: item.low)
    max_price, min_price = D(str(maximum.high)), D(str(minimum.low))
    mfe_usdt = (max_price - trade.entry_price) * trade.quantity
    mae_usdt = (min_price - trade.entry_price) * trade.quantity
    mfe_pct = (max_price / trade.entry_price - 1) * 100
    mae_pct = (min_price / trade.entry_price - 1) * 100

    production = [
        row for row in production_decisions
        if int(row.get("candle_timestamp", -1)) == entry_candle
    ]
    prod = production[-1] if production else {}
    scored65 = _score_observation(scored65_observations, entry_candle)
    scored62 = _score_observation(scored62_observations, entry_candle)
    decision65 = _score_decision(scored65, D("65"))
    decision62 = _score_decision(scored62, D("62"))
    scored = None
    if scored65 is not None:
        scored = {
            "total_score": scored65.get("score_total", scored65.get("signal_score", scored65.get("score"))),
            "components": _components(scored65),
            "threshold65": 65,
            "threshold62": 62,
            "decision65": decision65,
            "decision62": decision62,
        }

    be_matches = [
        row for row in break_even_observations
        if row.get("opened_at") == trade.opened_at
        and int(row.get("candle_timestamp", -1)) <= exit_candle_timestamp
    ]
    be = be_matches[-1] if be_matches else {}
    armed_at = be.get("armed_at_candle")
    triggered_at = be.get("triggered_at_candle")
    if be.get("saved_loss"):
        effect = "saved_loss"
    elif be.get("worsened_winner"):
        effect = "worsened_winner"
    else:
        effect = "no_effect"

    exit_time = datetime.fromisoformat(trade.closed_at)
    entry_time = datetime.fromisoformat(trade.opened_at)
    trade_id_source = "|".join((trade.opened_at, str(trade.entry_price), str(trade.quantity), str(exit_candle_timestamp)))
    net_return = trade.net_pnl / trade.entry_notional * 100
    card = {
        "trade_card_version": 1,
        "trade_id": hashlib.sha256(trade_id_source.encode()).hexdigest()[:24],
        "symbol": trade.symbol,
        "environment": "production",
        "execution_mode": "PAPER",
        "entry": {
            "entry_time": trade.opened_at, "entry_candle_timestamp": entry_candle,
            "entry_price": str(trade.entry_price), "quantity": str(trade.quantity),
            "position_notional": str(trade.entry_notional), "entry_fee": str(trade.entry_fee),
            "entry_reason": prod.get("reason") or prod.get("baseline_signal") or "ema_cross",
            "production_signal": prod.get("baseline_signal") or prod.get("signal") or "OPEN_LONG",
            "production_decision": prod.get("execution_signal") or prod.get("effective_action") or "OPEN_LONG",
        },
        "exit": {
            "exit_time": trade.closed_at, "exit_candle_timestamp": exit_candle_timestamp,
            "exit_price": str(trade.exit_price), "exit_fee": str(trade.exit_fee),
            "exit_reason": trade.exit_reason, "gross_pnl": str(trade.gross_pnl),
            "net_pnl": str(trade.net_pnl), "net_return_pct": str(net_return),
            "hold_time_seconds": int((exit_time - entry_time).total_seconds()),
        },
        "excursion": {
            "maximum_price_after_entry": str(max_price), "mfe_usdt": str(mfe_usdt),
            "mfe_pct": str(mfe_pct), "mfe_candle_timestamp": maximum.timestamp,
            "minimum_price_after_entry": str(min_price), "mae_usdt": str(mae_usdt),
            "mae_pct": str(mae_pct), "mae_candle_timestamp": minimum.timestamp,
            "reached_0_5_pct": mfe_pct >= D("0.5"),
            "reached_1_0_pct": mfe_pct >= D("1"),
            "reached_2_0_pct": mfe_pct >= D("2"),
        },
        "scored_entry_observation": scored if scored is not None else "unavailable",
        "decision_comparison": {
            "production": "entered", "score65": decision65 or "unavailable",
            "score62": decision62 or "unavailable",
        },
        "break_even_shadow": {
            "activation_price": be.get("activation_price"), "protective_price": be.get("protective_price"),
            "reached_activation": armed_at is not None, "armed": armed_at is not None,
            "armed_at_candle": armed_at, "triggered": triggered_at is not None,
            "triggered_at_candle": triggered_at,
            "hypothetical_exit_price": be.get("hypothetical_exit_price"),
            "hypothetical_pnl": be.get("hypothetical_pnl"), "effect": effect,
        },
    }
    card["preliminary_classification"] = _classification(
        net=net_return, mfe=mfe_pct, mae=mae_pct,
        score65=decision65, score62=decision62,
    )
    card["classification_is_diagnostic_only"] = True
    return card


class TradeDiagnosticsJournal:
    """Append-only JSONL journal with full-file restart-safe deduplication."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read_all(self) -> list[dict[str, Any]]:
        return _rows(self.path)

    def append(self, card: dict[str, Any]) -> bool:
        trade_id = str(card["trade_id"])
        if any(str(row.get("trade_id")) == trade_id for row in self.read_all()):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o640)
            json.dump(card, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True


def aggregate_trade_diagnostics(cards: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def values(field: str) -> list[float]:
        return [float(row["excursion"][field]) for row in cards]
    winners = [row for row in cards if D(row["exit"]["net_pnl"]) > 0]
    losers = [row for row in cards if D(row["exit"]["net_pnl"]) < 0]
    mfes, maes = values("mfe_pct"), values("mae_pct")
    rejected65 = [row for row in cards if row["decision_comparison"]["score65"] == "HOLD"]
    rejected62 = [row for row in cards if row["decision_comparison"]["score62"] == "HOLD"]
    return {
        "closed_trades_analyzed": len(cards), "winners": len(winners), "losers": len(losers),
        "average_mfe_pct": statistics.mean(mfes) if mfes else None,
        "median_mfe_pct": statistics.median(mfes) if mfes else None,
        "average_mae_pct": statistics.mean(maes) if maes else None,
        "median_mae_pct": statistics.median(maes) if maes else None,
        "losing_trades_reached_0_5_pct": sum(row["excursion"]["reached_0_5_pct"] for row in losers),
        "losing_trades_reached_1_0_pct": sum(row["excursion"]["reached_1_0_pct"] for row in losers),
        "losing_trades_reached_2_0_pct": sum(row["excursion"]["reached_2_0_pct"] for row in losers),
        "scored65_rejected_entries": len(rejected65),
        "scored65_rejected_pnl": str(sum((D(row["exit"]["net_pnl"]) for row in rejected65), D("0"))),
        "scored62_rejected_entries": len(rejected62),
        "scored62_rejected_pnl": str(sum((D(row["exit"]["net_pnl"]) for row in rejected62), D("0"))),
        "be_armed_count": sum(row["break_even_shadow"]["armed"] for row in cards),
        "be_triggered_count": sum(row["break_even_shadow"]["triggered"] for row in cards),
        "saved_losses": sum(row["break_even_shadow"]["effect"] == "saved_loss" for row in cards),
        "worsened_winners": sum(row["break_even_shadow"]["effect"] == "worsened_winner" for row in cards),
        "research_only": True,
    }


def build_and_append_trade_card(*, trade: TradeJournalEntry, candles: Sequence[Candle],
                                exit_candle_timestamp: int, journal_path: Path,
                                production_decision_path: Path, scored65_path: Path,
                                scored62_path: Path, break_even_path: Path,
                                timeframe_minutes: int = 60) -> tuple[dict[str, Any], bool]:
    card = build_trade_card(
        trade, candles=candles, exit_candle_timestamp=exit_candle_timestamp,
        timeframe_minutes=timeframe_minutes,
        production_decisions=_rows(production_decision_path),
        scored65_observations=_rows(scored65_path),
        scored62_observations=_rows(scored62_path),
        break_even_observations=_rows(break_even_path),
    )
    return card, TradeDiagnosticsJournal(journal_path).append(card)
