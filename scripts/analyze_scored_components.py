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
from app.scored_component_analysis import analyze_observations, replay_closed_candles, select_period


def load_candles(path: Path) -> tuple[Candle, ...]:
    frame = pd.read_csv(path)
    column = "datetime" if "datetime" in frame else "timestamp"
    timestamps = pd.to_datetime(frame[column], utc=True).astype("int64") // 10**9
    return tuple(Candle(int(timestamps.iloc[i]), float(row.open), float(row.high), float(row.low),
                        float(row.close), float(row.volume)) for i, row in frame.iterrows())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Scored Candidate historical component audit")
    parser.add_argument("--period", default="90d", help="30d, 90d, 180d, 365d, or all")
    parser.add_argument("--environment", choices=("scored_candidate",), default="scored_candidate")
    parser.add_argument("--data", type=Path, default=ROOT / "data/eth_usdt_1h_full.csv")
    parser.add_argument("--forward-horizons", default="1,3,6,12,24")
    parser.add_argument("--include-counterfactuals", action="store_true")
    parser.add_argument("--output", type=Path, help="Explicit local report path; nothing is written by default")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        horizons = tuple(int(x) for x in args.forward_horizons.split(","))
        if not horizons or any(x <= 0 for x in horizons): raise ValueError
    except ValueError:
        build_parser().error("--forward-horizons must be comma-separated positive integers")
    candles = load_candles(args.data)
    selected = select_period(candles, args.period)
    all_observations, quality = replay_closed_candles(candles)
    selected_timestamps = {c.timestamp for c in selected}
    observations = [row for row in all_observations if row.timestamp in selected_timestamps]
    quality.update({"dataset": str(args.data), "available_start": pd.Timestamp(candles[0].timestamp, unit="s", tz="UTC").isoformat() if candles else None,
                    "available_end": pd.Timestamp(candles[-1].timestamp + 3600, unit="s", tz="UTC").isoformat() if candles else None})
    report = asdict(analyze_observations(observations, period=args.period, horizons=horizons, quality=quality,
                                         include_counterfactuals=args.include_counterfactuals))
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    if args.json:
        print(payload)
    else:
        trend = report["component_distributions"]["trend"]["percentages"]["exactly_zero"]
        ema = report["component_distributions"]["ema_alignment"]["percentages"]["exactly_zero"]
        top = max(report["limiter_frequency"]["components"], key=lambda x: report["limiter_frequency"]["components"][x]["limiter_1_pct"], default="N/A")
        print("\n".join(("Scored Candidate audit (read-only / ANALYSIS_ONLY)",
            f"Period: {report['start']} — {report['end']}", f"Observations: {report['observations']}",
            f"Score >=65: {report['score_distribution']['statistics']['percentage_gte_65']:.3f}%",
            f"Score >=80: {report['score_distribution']['statistics']['percentage_gte_80']:.3f}%",
            f"Trend zero: {trend:.3f}%", f"EMA Alignment zero: {ema:.3f}%", f"Top limiter: {top}",
            f"Data quality: duplicates={quality['duplicate_candles']}, warmup_excluded={quality['warmup_excluded']}",
            f"Verdict: {report['verdict']['status']}")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
