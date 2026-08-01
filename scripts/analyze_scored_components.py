from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.candle import Candle
from app.scored_component_calibration import analyze, replay
from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.runtime_health import read_jsonl_safely


def load_candles(path: Path) -> tuple[Candle, ...]:
    frame = pd.read_csv(path)
    timestamps = pd.to_datetime(frame["datetime"], utc=True).astype("int64") // 10**9
    return tuple(Candle(
        int(timestamps.iloc[index]), float(row.open), float(row.high),
        float(row.low), float(row.close), float(row.volume),
    ) for index, row in frame.iterrows())


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only scored component calibration")
    parser.add_argument("--source", choices=("historical", "live-shadow"), default="historical")
    parser.add_argument("--data", type=Path, default=ROOT / "data/eth_usdt_1h.csv")
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--threshold", type=float, default=65.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.source == "historical":
        candles = load_candles(args.data)
        records = replay(candles)
    else:
        if args.journal is None:
            parser.error("--journal is required for --source live-shadow")
        candles = BybitMarketDataFeed(BybitMarketDataConfig(
            symbol="ETHUSDT", interval="60", category="spot", limit=1000,
            max_retries=1, closed_candles_only=True,
        )).get_candles()
        journal = read_jsonl_safely(args.journal)[0] if args.journal.exists() else []
        timestamps = {int(row["candle_close_timestamp"]) for row in journal}
        records = [row for row in replay(candles) if int(row["candle_close_timestamp"]) in timestamps]
    report = analyze(records, candles, threshold=args.threshold)
    report["source"] = args.source
    report["journal"] = str(args.journal) if args.journal else None
    if args.source == "live-shadow":
        report["journal_metadata"] = {
            "strategy_name": sorted({row.get("strategy_name") for row in journal}),
            "score_version": sorted({row.get("score_version") for row in journal}),
            "risk_model_version": sorted({row.get("risk_model_version") for row in journal}),
            "decisions": dict(pd.Series([row.get("decision", row.get("action")) for row in journal]).value_counts()),
        }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    if args.json:
        print(payload)
    else:
        print("\n".join([
            "Scored Candidate component calibration (read-only)",
            f"Valid setups: {report['valid_setup_decisions']}",
            f"Primary limiter: {report['primary_limiter']}",
            f"Pullback: {report['component_summary']['pullback']}",
            f"ADX: {report['component_summary']['adx']}",
            f"Marginal contribution: {report['marginal_contribution']}",
        ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
