from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.candle import Candle
from app.entry_blocker_analysis import analyze_entry_blockers, replay_entry_observations
from scripts.analyze_scored_components import select_period


def load_candles(path: Path) -> tuple[Candle, ...]:
    frame = pd.read_csv(path)
    column = "datetime" if "datetime" in frame else "timestamp"
    timestamps = pd.to_datetime(frame[column], utc=True).astype("int64") // 10**9
    return tuple(Candle(int(timestamps.iloc[i]), float(row.open), float(row.high), float(row.low), float(row.close), float(row.volume))
                 for i, row in frame.iterrows())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only scored entry blocker and near-miss analysis")
    parser.add_argument("--period", default="90d", help="30d, 90d, 180d, 365d, or all")
    parser.add_argument("--data", type=Path, default=ROOT / "data/eth_usdt_1h_full.csv")
    parser.add_argument("--forward-horizons", default="1,3,6,12,24")
    parser.add_argument("--include-counterfactuals", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, help="Explicit local report path; no output file by default")
    args = parser.parse_args(argv)
    horizons = tuple(int(x) for x in args.forward_horizons.split(","))
    if not horizons or any(x <= 0 for x in horizons):
        parser.error("--forward-horizons must contain positive integers")
    candles = load_candles(args.data)
    selected = select_period(candles, args.period)
    all_rows, quality = replay_entry_observations(candles)
    selected_timestamps = {c.timestamp for c in selected}
    rows = [row for row in all_rows if row.timestamp in selected_timestamps]
    quality.update({"dataset": str(args.data), "available_start": pd.Timestamp(candles[0].timestamp, unit="s", tz="UTC").isoformat() if candles else None,
                    "available_end": pd.Timestamp(candles[-1].timestamp + 3600, unit="s", tz="UTC").isoformat() if candles else None})
    report = asdict(analyze_entry_blockers(rows, candles, period=args.period, horizons=horizons,
                                           include_counterfactuals=args.include_counterfactuals, quality=quality))
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    if args.json:
        print(payload)
    else:
        categories = report["decision_categories"]
        print("\n".join(("Scored Candidate entry blocker audit (read-only / ANALYSIS_ONLY)",
            f"Period: {args.period}; observations: {report['observations']}",
            f"Base signal: {report['base_signal_funnel']['base_signal']} ({report['base_signal_funnel']['conversion_rates_pct']['base_signal']:.2f}%)",
            f"Score >=65: {report['base_signal_funnel']['score_gte_65']}",
            f"Near miss 60-65: {report['near_misses']['count']}",
            f"HOLD score-blocked: {categories['SCORE_BELOW_THRESHOLD']}",
            f"Top blocker: {max(report['blocker_frequency'], key=lambda x: report['blocker_frequency'][x]['primary_count'])}",
            f"Verdict: {report['verdict']['status']}")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
