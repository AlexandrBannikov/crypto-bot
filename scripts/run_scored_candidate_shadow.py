from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.scored_candidate import ScoredCandidateStateStore, evaluate_shadow_candles


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scored candidate in shadow mode only")
    parser.add_argument("--state", type=Path, default=ROOT / "state/scored_candidate_v1.json")
    parser.add_argument("--decisions", type=Path, default=ROOT / "state/scored_candidate_v1_decisions.jsonl")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--interval", default="60")
    args = parser.parse_args()
    candles = BybitMarketDataFeed(BybitMarketDataConfig(symbol=args.symbol, interval=args.interval, limit=500, category="spot", max_retries=1)).get_candles()
    state = evaluate_shadow_candles(candles, state_store=ScoredCandidateStateStore(args.state), decision_path=args.decisions)
    print(f"{state.last_candle=} {state.hypothetical_position=}; shadow only, no orders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
