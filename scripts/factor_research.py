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

from app.factor_research import research
from scripts.analyze_scored_components import load_candles


def _timestamp(value: str) -> int:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _csv(report: dict) -> str:
    output = io.StringIO()
    fields = ["record_type", "factor", "bucket", "count", "predictive_quality", "mean", "median", "positive_rate_percent", "mfe_mean", "mae_mean"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for rank in report["ranking"]:
        factor = rank["factor"]
        profile = report["factors"][factor]
        writer.writerow({
            "record_type": "factor", "factor": factor,
            "predictive_quality": rank["predictive_quality"],
            "count": profile["contribution"]["count"],
            "mean": profile["contribution"]["mean"],
            "median": profile["contribution"]["median"],
        })
        for bucket in profile["distribution"]:
            ret = bucket["returns"]["24h"]
            writer.writerow({
                "record_type": "bucket", "factor": factor,
                "bucket": bucket["range"], "count": bucket["count"],
                "mean": ret["mean"], "median": ret["median"],
                "positive_rate_percent": ret["positive_rate_percent"],
                "mfe_mean": bucket["mfe"]["24h"]["mean"],
                "mae_mean": bucket["mae"]["24h"]["mean"],
            })
    return output.getvalue()


def render_text(report: dict) -> str:
    ranking = "\n".join(
        f"{index}. {item['factor']}: {item['predictive_quality']:.2f}"
        for index, item in enumerate(report["ranking"], 1)
    )
    return "\n".join([
        "Scored Candidate Factor Research (analysis only)",
        f"Period: {report['period']}",
        "Predictive quality ranking:", ranking,
        f"Redundant pairs: {report['redundant_factor_pairs']}",
        f"Near misses: {report['near_miss_55_to_threshold']['all']['count']}",
        f"False negatives: {report['false_negatives']['count']}",
        f"False positives: {report['false_positives']['count']}",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Scored Candidate factor research")
    parser.add_argument("--data", type=Path, default=ROOT / "data/eth_usdt_1h.csv")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--csv", nargs="?", const="-", metavar="PATH", help="Write CSV to PATH or stdout")
    parser.add_argument("--days", type=int)
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    args = parser.parse_args()
    if args.days is not None and args.days <= 0:
        parser.error("--days must be positive")
    candles = load_candles(args.data)
    from_timestamp = _timestamp(args.date_from) if args.date_from else None
    to_timestamp = _timestamp(args.date_to) if args.date_to else None
    if args.days is not None:
        end = to_timestamp or (candles[-1].timestamp + 3600)
        from_timestamp = max(from_timestamp or 0, end - args.days * 86400)
    if from_timestamp is not None and to_timestamp is not None and from_timestamp > to_timestamp:
        parser.error("--from must not be after --to")
    report = research(candles, from_timestamp=from_timestamp, to_timestamp=to_timestamp)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.csv is not None:
        payload = _csv(report)
        if args.csv == "-":
            print(payload, end="")
        else:
            path = Path(args.csv)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
