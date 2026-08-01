from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from app.setup_type_research import Direction, SCORE_VERSION, SETUP_VERSION, SetupType, research
from scripts.analyze_scored_components import load_candles


def _timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def render_csv(report: dict) -> str:
    output = io.StringIO()
    fields = ["timestamp", "asset", "regime", "direction", "setup_type", "setup_version", "score", "threshold", "outcome_3h", "outcome_6h", "outcome_12h", "outcome_24h", "MFE", "MAE", "trend_episode_id", "reasons", "features"]
    writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
    for row in report.get("decisions", []):
        writer.writerow({"timestamp": row["candle_close_timestamp"], "asset": row["asset"], "regime": row["regime"], "direction": row["direction"], "setup_type": row["setup_type"], "setup_version": row["setup_version"], "score": row["total_score"], "threshold": report["metadata"]["threshold"], "outcome_3h": row["outcomes"].get("return_3h"), "outcome_6h": row["outcomes"].get("return_6h"), "outcome_12h": row["outcomes"].get("return_12h"), "outcome_24h": row["outcomes"].get("return_24h"), "MFE": row["outcomes"].get("mfe_24h"), "MAE": row["outcomes"].get("mae_24h"), "trend_episode_id": row["trend_episode_id"], "reasons": " | ".join(row["reasons"]), "features": json.dumps(row["supporting_features"], separators=(",", ":"))})
    return output.getvalue()


def render_text(report: dict) -> str:
    if report.get("status") == "DATA_QUALITY_ERROR": return f"Setup Type Research Report\nDATA_QUALITY_ERROR: {report['data_quality']}"
    meta = report["metadata"]
    lines = ["Setup Type Research Report", f"Period: {meta['period']}", f"Asset: {meta['asset']}", f"Score version: {meta['score_version']}", f"Setup version: {meta['setup_version']}", f"Observations: {meta['observations']}", f"Non-overlapping observations: {meta['non_overlapping_observations']}", f"Trend episodes: {report['episode_analysis']['count']}", "Setup distribution:"]
    lines += [f"- {name}: {item['count']} ({item['share_percent']:.1f}%) [{item['status']}]" for name, item in sorted(report["setup_distribution"].items(), key=lambda pair: -pair[1]["count"])]
    lines += [f"MISSED decomposition: { {k:v['count'] for k,v in report['missed_decomposition']['groups'].items()} }", f"BAD decomposition: { {k:v['count'] for k,v in report['false_positive_decomposition']['groups'].items()} }", f"Conclusion: {report['status']}"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only setup type research")
    parser.add_argument("--data", type=Path, default=ROOT/"data/eth_usdt_1h_full.csv")
    parser.add_argument("--asset", default="ETH/USDT")
    parser.add_argument("--setup-type", choices=[item.value for item in SetupType])
    parser.add_argument("--direction", choices=[item.value for item in Direction])
    parser.add_argument("--regime")
    parser.add_argument("--non-overlapping", action="store_true")
    parser.add_argument("--trend-episodes", action="store_true", help="Retain episode detail in JSON (summaries are always calculated)")
    parser.add_argument("--score-version", default=SCORE_VERSION)
    parser.add_argument("--setup-version", default=SETUP_VERSION)
    parser.add_argument("--days", type=int)
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    output = parser.add_mutually_exclusive_group(); output.add_argument("--json", action="store_true"); output.add_argument("--csv", nargs="?", const="-", metavar="PATH")
    args = parser.parse_args()
    if args.days is not None and args.days <= 0: parser.error("--days must be positive")
    if args.score_version != SCORE_VERSION: parser.error(f"only {SCORE_VERSION} is available")
    if args.setup_version != SETUP_VERSION: parser.error(f"only {SETUP_VERSION} is available")
    if args.asset != "ETH/USDT": parser.error("no validated historical dataset for requested asset")
    candles = load_candles(args.data)
    start, end = (_timestamp(args.date_from) if args.date_from else None), (_timestamp(args.date_to) if args.date_to else None)
    if args.days is not None:
        effective_end = end or candles[-1].timestamp + 3600; start = max(start or 0, effective_end-args.days*86400)
    if start is not None and end is not None and start > end: parser.error("--from must not be after --to")
    report = research(candles, asset=args.asset, from_timestamp=start, to_timestamp=end, setup_type=args.setup_type, direction=args.direction, regime=args.regime, non_overlapping=args.non_overlapping)
    if not args.trend_episodes and report.get("episode_analysis"): report["episode_analysis"].pop("details", None)
    if args.json:
        # JSON is the aggregate research report; decision-level output belongs
        # to CSV and would otherwise exceed 100 MB on the fixed history.
        report.pop("decisions", None)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.csv is not None:
        payload = render_csv(report)
        if args.csv == "-": print(payload, end="")
        else:
            path=Path(args.csv); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(payload, encoding="utf-8")
    else: print(render_text(report))
    return 2 if report.get("status") == "DATA_QUALITY_ERROR" else 0


if __name__ == "__main__": raise SystemExit(main())
