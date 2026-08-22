from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.scored_candidate import ScoredCandidateStateStore, evaluate_shadow_candles
from app.process_lock import ProcessAlreadyRunningError, ProcessLock


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scored candidate in shadow mode only")
    runtime = ROOT / "state/scored_candidate_shadow"
    parser.add_argument("--state", type=Path, default=runtime / "runtime.json")
    parser.add_argument("--decisions", type=Path, default=runtime / "decisions.jsonl")
    parser.add_argument("--lock-file", type=Path, default=runtime / "runtime.lock")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--interval", default="60")
    args = parser.parse_args()
    try:
        with ProcessLock(args.lock_file):
            feed = BybitMarketDataFeed(BybitMarketDataConfig(symbol=args.symbol, interval=args.interval, limit=500, category="spot", max_retries=1, closed_candles_only=True))
            candles = feed.get_ready_candles()
            state = evaluate_shadow_candles(candles, state_store=ScoredCandidateStateStore(args.state), decision_path=args.decisions, timeframe_minutes=int(args.interval))
    except ProcessAlreadyRunningError as exc:
        print(f"Scored candidate already running: {exc}", file=sys.stderr)
        return 2
    print(f"{state.last_candle=} {state.hypothetical_position=}; shadow only, no orders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
