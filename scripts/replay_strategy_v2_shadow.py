"""Replay Strategy V2 against local closed 1h candles and scored decisions."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.candle import Candle
from app.indicators import ema
from app.strategy_v2_shadow import StrategyV2State, metrics, process_candle
from app.signal_scoring import evaluate_signal
import pandas as pd


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Causal research replay for Strategy V2 Shadow")
    result.add_argument("--candles", type=Path, default=PROJECT_ROOT / "data/eth_usdt_1h_full.csv")
    result.add_argument("--scores", type=Path, default=PROJECT_ROOT / "state/scored_candidate_shadow/decisions.jsonl")
    result.add_argument("--output", type=Path)
    result.add_argument("--recompute-scores", action="store_true", help="causally recompute score65 over all CSV candles")
    return result


def replay(candle_path: Path, score_path: Path, *, recompute_scores: bool = False) -> dict:
    scores = {int(row["candle_timestamp"]): row for row in (
        json.loads(line) for line in score_path.read_text(encoding="utf-8").splitlines() if line.strip()
    )}
    candles = []
    with candle_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            timestamp = int(datetime.fromisoformat(row["datetime"]).timestamp())
            if recompute_scores or timestamp in scores:
                candles.append(Candle(timestamp, *(float(row[key]) for key in ("open", "high", "low", "close", "volume"))))
    frame = pd.DataFrame({"close": [c.close for c in candles]})
    fast, slow = ema(frame["close"], 20), ema(frame["close"], 50)
    state = StrategyV2State()
    events = []
    maximum_quantity = Decimal("0")
    scored_position = False
    for index, candle in enumerate(candles):
        cross_down = bool(index and pd.notna(fast.iloc[index - 1]) and pd.notna(slow.iloc[index - 1]) and fast.iloc[index - 1] >= slow.iloc[index - 1] and fast.iloc[index] < slow.iloc[index])
        if recompute_scores:
            scored = evaluate_signal(candles[max(0, index - 199): index + 1])
            if scored_position and scored.indicators.get("ema_fast", 0) < scored.indicators.get("ema_slow", 0):
                decision, scored_position = "EXIT_LONG", False
            elif not scored_position and scored.total_score >= 65 and not scored.hard_blocks:
                decision, scored_position = "ENTER_LONG", True
            else:
                decision = "HOLD"
            score_row = {"decision": decision, "score_total": scored.total_score, "components": {
                "trend_score": scored.trend_score, "ema_alignment_score": scored.ema_alignment_score,
                "adx_score": scored.adx_score}}
        else:
            score_row = scores[candle.timestamp]
        state, observation = process_candle(state, candle=candle, score=score_row, bearish_ema_cross=cross_down)
        maximum_quantity = max(maximum_quantity, state.quantity)
        if observation["event"] != "hold":
            events.append(observation)
    result = metrics(state)
    payload = {
        "research_only": True,
        "parameters_changed_after_replay": False,
        "matched_closed_candles": len(candles),
        "events": len(events),
        "entries": sum(row["event"] == "entry" for row in events),
        "add_ons": sum(row["event"] == "add" for row in events),
        "exits": sum(row["event"] == "exit" for row in events),
        "closed_trades": state.closed_trades,
        "ending_equity": str(state.equity),
        "realised_pnl": str(state.realised_pnl),
        "max_drawdown_pct": str(state.max_drawdown),
        "maximum_quantity": str(maximum_quantity),
        "accounting_identity_error": str(state.equity - (state.cash + state.quantity * (Decimal(str(candles[-1].close)) if candles else Decimal("0")))),
        "profit_factor": None if result["profit_factor"] is None else str(result["profit_factor"]),
        "score_source": "causally_recomputed" if recompute_scores else "persisted_scored65",
        "causal_semantics": "pre-candle levels; close decisions/fills; current high affects next candle",
    }
    return payload


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    payload = replay(args.candles, args.scores, recompute_scores=args.recompute_scores)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
