from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.process_lock import ProcessAlreadyRunningError, ProcessLock
from app.runtime_health import read_jsonl_safely
from app.scored_candidate import ScoredCandidateStateStore, evaluate_shadow_candles
from app.scored_threshold62_experiment import STRATEGY_NAME, experiment_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run threshold-62 scored candidate in shadow mode"
    )
    runtime = ROOT / "state/scored_candidate_threshold62"
    parser.add_argument("--state", type=Path, default=runtime / "runtime.json")
    parser.add_argument(
        "--decisions", type=Path, default=runtime / "decisions.jsonl"
    )
    parser.add_argument("--lock-file", type=Path, default=runtime / "runtime.lock")
    parser.add_argument(
        "--threshold65-decisions",
        type=Path,
        default=ROOT / "state/scored_candidate_shadow/decisions.jsonl",
    )
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--interval", default="60")
    args = parser.parse_args()
    try:
        with ProcessLock(args.lock_file):
            bootstrap = not args.state.exists() and args.threshold65_decisions.exists()
            candles = BybitMarketDataFeed(
                BybitMarketDataConfig(
                    symbol=args.symbol,
                    interval=args.interval,
                    limit=1000 if bootstrap else 500,
                    category="spot",
                    max_retries=1,
                    closed_candles_only=True,
                )
            ).get_candles()
            if bootstrap:
                baseline = read_jsonl_safely(args.threshold65_decisions)[0]
                if baseline:
                    first = int(baseline[0]["candle_timestamp"])
                    last = int(baseline[-1]["candle_timestamp"])
                    candles = tuple(
                        candle
                        for candle in candles
                        if first <= candle.timestamp <= last
                    )
                    if (
                        not candles
                        or candles[0].timestamp != first
                        or candles[-1].timestamp != last
                    ):
                        raise ValueError(
                            "Bybit history does not cover the threshold-65 "
                            "bootstrap range"
                        )
            state = evaluate_shadow_candles(
                candles,
                state_store=ScoredCandidateStateStore(args.state),
                decision_path=args.decisions,
                config=experiment_config(),
                timeframe_minutes=int(args.interval),
                strategy_name=STRATEGY_NAME,
            )
    except ProcessAlreadyRunningError as exc:
        print(f"Threshold-62 candidate already running: {exc}", file=sys.stderr)
        return 2
    print(
        f"{state.last_candle=} {state.hypothetical_position=}; "
        "shadow only, no orders"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

