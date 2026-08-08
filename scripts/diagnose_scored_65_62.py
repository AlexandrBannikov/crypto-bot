from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scored_threshold62_diagnostics import summarize_scored_65_62


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only scored candidate 65 vs 62 observability"
    )
    parser.add_argument(
        "--threshold65",
        type=Path,
        default=ROOT / "state/scored_candidate_shadow/decisions.jsonl",
    )
    parser.add_argument(
        "--threshold62",
        type=Path,
        default=ROOT / "state/scored_candidate_threshold62/decisions.jsonl",
    )
    parser.add_argument("--days", type=int)
    args = parser.parse_args()
    if args.days is not None and args.days <= 0:
        parser.error("--days must be positive")
    report = summarize_scored_65_62(
        args.threshold65,
        args.threshold62,
        days=args.days,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

