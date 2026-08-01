from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scored_threshold60_diagnostics import summarize_threshold60


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only threshold-60 shadow diagnostics")
    parser.add_argument("--decisions", type=Path, default=ROOT / "state/scored_candidate_threshold60/decisions.jsonl")
    parser.add_argument("--days", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.days is not None and args.days <= 0:
        parser.error("--days must be positive")
    result = summarize_threshold60(args.decisions, days=args.days)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n".join([
            "Scored Candidate Threshold 60 — shadow experiment",
            f"Candles: {result['total_candles']}",
            f"Decisions: {result['decisions']}",
            f"Score: {result['score']}",
            f"Hard blocks: {result['hard_blocks']}",
            f"Allocation: {result['score_distribution']}",
        ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
