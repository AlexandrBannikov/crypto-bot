from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.strategy_confidence import (
    build_promotion_review,
    load_promotion_config,
    render_promotion_review,
)
from app.strategy_lab import PERIODS, load_config, render_report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Read-only Strategy Laboratory v2 report"
    )
    result.add_argument("--period", choices=PERIODS, default="24h")
    result.add_argument("--strategy")
    result.add_argument("--recommendations", action="store_true")
    result.add_argument("--explain", action="store_true")
    result.add_argument("--diagnostics", action="store_true")
    result.add_argument("--json", action="store_true")
    result.add_argument("--timezone", default="UTC")
    result.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/strategy_lab.json",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    laboratory = load_config(args.config, root=ROOT)
    report = build_promotion_review(
        laboratory,
        load_promotion_config(args.config),
        period=args.period,
        strategy_filter=args.strategy,
        timezone_name=args.timezone,
    )
    from app.comparison_diagnostics import assess_comparison
    production = report.get("strategies", {}).get("production")
    assessments = {}
    for candidate_id, comparison in report.get("comparisons", {}).items():
        assessments[candidate_id] = assess_comparison(
            production, report.get("strategies", {}).get(candidate_id),
            matched_candles=int(comparison.get("matched_candles", 0)),
            production_only=int(comparison.get("production_only_decisions", 0)),
            candidate_only=int(comparison.get("candidate_only_decisions", 0)),
        )
    report["comparison_diagnostics"] = assessments
    first = next(iter(assessments.values()), {"comparison_status": "INSUFFICIENT", "comparison_error_code": "COMPARISON_HISTORY_INSUFFICIENT"})
    report["comparison_status"] = first["comparison_status"]
    report["comparison_error_code"] = first["comparison_error_code"]
    if args.diagnostics:
        from app.candidate_diagnostics import summarize_candidate
        from datetime import datetime
        candidate = next((s for s in laboratory.strategies if s.kind == "candidate"), None)
        period_data = report.get("period", {})
        start = datetime.fromisoformat(period_data["start"]) if period_data.get("start") else None
        end = datetime.fromisoformat(period_data["end"]) if period_data.get("end") else None
        report["no_signal_diagnostics"] = summarize_candidate(candidate.decisions, candidate.trades, start=start, end=end) if candidate else {"status": "unavailable"}
    if args.recommendations or args.explain:
        text = render_promotion_review(report, explain=args.explain)
    else:
        text = render_report(report)
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json else text,
        end="" if not args.json else "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
