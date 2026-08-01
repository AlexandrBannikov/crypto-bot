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

from app.market_regime_research import research
from scripts.analyze_scored_components import load_candles


def _timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def render_csv(report: dict) -> str:
    output = io.StringIO()
    fields = ["regime", "candle_count", "history_share_percent", "factor", "rank", "predictive_quality", "positive_rate_percent", "future_return_24h_mean", "mfe_24h_mean", "mae_24h_mean"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for regime, data in report["regimes"].items():
        for rank, factor in enumerate(data["factor_ranking"], 1):
            writer.writerow({"regime": regime, "candle_count": data["candle_count"], "history_share_percent": data["history_share_percent"], "factor": factor["factor"], "rank": rank, **{name: factor[name] for name in fields[5:]}})
    return output.getvalue()


def render_text(report: dict) -> str:
    ordered = sorted(report["regimes"].items(), key=lambda item: item[1]["candle_count"], reverse=True)
    lines = ["Market Regime Research (analysis only)", f"Period: {report['period']}", "Regimes:"]
    for regime, data in ordered:
        leaders = ", ".join(f"{item['factor']}={item['predictive_quality']:.1f}" for item in data["factor_ranking"][:3])
        lines.append(f"- {regime}: {data['candle_count']} ({data['history_share_percent']:.1f}%), best: {leaders}")
    lines.extend([f"Near threshold 60-65: {report['near_threshold_60_65']['count']}", f"False negatives: {report['false_negatives']['count']}", f"False positives: {report['false_positives']['count']}"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only deterministic market regime research")
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
    report = research(candles, from_timestamp=start, to_timestamp=end)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.csv is not None:
        payload = render_csv(report)
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
