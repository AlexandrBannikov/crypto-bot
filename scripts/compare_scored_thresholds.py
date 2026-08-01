from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.candle import Candle
from app.scored_threshold_comparison import compare, render_text


def _read_candles(path: Path) -> tuple[Candle, ...]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return tuple(Candle(**row) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare scored shadow thresholds 65 and 60")
    parser.add_argument("--threshold65", type=Path, default=ROOT / "state/scored_candidate_shadow/decisions.jsonl")
    parser.add_argument("--threshold60", type=Path, default=ROOT / "state/scored_candidate_threshold60/decisions.jsonl")
    parser.add_argument("--candles", type=Path, help="Optional JSONL candles; otherwise fetch the same closed ETHUSDT 1h feed")
    parser.add_argument("--minimum-order-value", type=float, default=5.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    candles = _read_candles(args.candles) if args.candles else BybitMarketDataFeed(BybitMarketDataConfig(symbol="ETHUSDT", interval="60", category="spot", limit=1000, max_retries=1, closed_candles_only=True)).get_candles()
    report = compare(args.threshold65, args.threshold60, candles=candles, minimum_order_value=args.minimum_order_value)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
