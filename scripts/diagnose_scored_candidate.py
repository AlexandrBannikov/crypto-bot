from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scored_candidate_diagnostics import summarize


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only scored candidate diagnostics")
    parser.add_argument("--decisions", type=Path, default=ROOT / "state/scored_candidate_shadow/decisions.jsonl")
    parser.add_argument("--days", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.days is not None and args.days <= 0:
        parser.error("--days must be positive")
    result = summarize(args.decisions, days=args.days)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        score = result["score"]
        print("\n".join([
            "Scored Candidate — shadow", f"Candles: {result['total_candles']}",
            f"Decisions: {result['decisions']}",
            f"Score min/avg/max: {score['minimum']} / {score['average']} / {score['maximum']}",
            f"Average components: {result['average_components']}", f"Hard blocks: {result['hard_blocks']}",
            f"Score distribution: {result['score_distribution']}", f"Main limiters: {result['main_limiters']}",
        ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
