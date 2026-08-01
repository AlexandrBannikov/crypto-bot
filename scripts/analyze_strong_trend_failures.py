from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.strong_trend_failure_analysis import analyze
from scripts.analyze_scored_components import load_candles


def _timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def render_csv(report: dict) -> str:
    output = io.StringIO()
    fields = ["feature", "good_count", "good_mean", "good_median", "good_std", "bad_count", "bad_mean", "bad_median", "bad_std", "mean_difference", "cohens_d", "ci_low", "ci_high"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in report["good_vs_bad"]:
        writer.writerow({"feature": item["feature"], "good_count": item["good"]["count"], "good_mean": item["good"]["mean"], "good_median": item["good"]["median"], "good_std": item["good"]["standard_deviation"], "bad_count": item["bad"]["count"], "bad_mean": item["bad"]["mean"], "bad_median": item["bad"]["median"], "bad_std": item["bad"]["standard_deviation"], "mean_difference": item["mean_difference_good_minus_bad"], "cohens_d": item["cohens_d"], "ci_low": item["mean_difference_95pct_ci"][0], "ci_high": item["mean_difference_95pct_ci"][1]})
    return output.getvalue()


def render_text(report: dict) -> str:
    leaders = ", ".join(f"{item['feature']} (d={item['cohens_d']:.2f})" for item in report["good_vs_bad"][:5] if item["cohens_d"] is not None)
    return "\n".join(["Strong Trend Failure Analysis (analysis only)", f"Period: {report['period']}", f"GOOD: {report['groups']['good']['count']}", f"BAD: {report['groups']['bad']['count']}", f"MISSED: {report['groups']['missed']['count']}", f"Largest GOOD/BAD effects: {leaders}"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only strong trend failure analysis")
    parser.add_argument("--data", type=Path, default=ROOT / "data/eth_usdt_1h_full.csv")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--csv", nargs="?", const="-", metavar="PATH")
    parser.add_argument("--days", type=int)
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    args = parser.parse_args()
    if args.days is not None and args.days <= 0:
        parser.error("--days must be positive")
    candles = load_candles(args.data)
    start = _timestamp(args.date_from) if args.date_from else None
    end = _timestamp(args.date_to) if args.date_to else None
    if args.days is not None:
        effective_end = end or candles[-1].timestamp + 3600
        start = max(start or 0, effective_end - args.days * 86400)
    if start is not None and end is not None and start > end:
        parser.error("--from must not be after --to")
    report = analyze(candles, from_timestamp=start, to_timestamp=end)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.csv is not None:
        payload = render_csv(report)
        if args.csv == "-": print(payload, end="")
        else:
            path = Path(args.csv); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(payload, encoding="utf-8")
    else: print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
