from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime_health import read_jsonl_safely
from app.scored_observability import aggregate, breakdown_from_record, format_breakdown


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Read-only scored candidate explainability")
    result.add_argument("--decisions", type=Path, default=ROOT / "state/scored_candidate_shadow/decisions.jsonl")
    result.add_argument("--latest", action="store_true")
    result.add_argument("--components", action="store_true")
    result.add_argument("--json", action="store_true")
    result.add_argument("--last", type=int, metavar="HOURS")
    result.add_argument("--aggregate", choices=("24h", "7d", "all"))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.last is not None and args.last <= 0:
        parser().error("--last must be positive")
    period = args.aggregate or (f"{args.last}h" if args.last else None)
    if period:
        hours = None if period == "all" else 168 if period == "7d" else int(period.removesuffix("h"))
        value = aggregate(args.decisions, hours=hours)
        print(json.dumps(value, ensure_ascii=False, indent=2) if args.json else _aggregate_text(value))
        return 0
    rows = read_jsonl_safely(args.decisions)[0] if args.decisions.exists() else []
    row = rows[-1] if rows else None
    value = breakdown_from_record(row or {})
    if args.json:
        print(json.dumps(value or {"score_breakdown": None, "reason": "unavailable or legacy record"}, ensure_ascii=False, indent=2))
    else:
        print(format_breakdown(row or {}, component_limit=99 if args.components else 5))
    return 0


def _aggregate_text(value: dict) -> str:
    score = value["score"]
    return "\n".join([
        "Scored Candidate — aggregate", f"Decisions: {value['decisions_total']}",
        f"Score avg/median/min/max: {score['average']} / {score['median']} / {score['minimum']} / {score['maximum']}",
        f"Bands: {value['score_bands']}", f"Average distance to entry: {value['average_distance_to_entry']}",
        f"Decisions: {value['decisions']}", f"Average allocation: {value['average_allocation_pct']}%",
        f"Allocation bands: {value['allocation_bands']}", f"Frequent limiters: {value['frequent_limiters']}",
        f"Average components: {value['average_components']}",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
