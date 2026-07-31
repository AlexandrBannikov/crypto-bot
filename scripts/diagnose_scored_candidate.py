from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime_health import read_jsonl_safely


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only scored candidate diagnostics")
    parser.add_argument("--decisions", type=Path, default=ROOT / "state/scored_candidate_v1_decisions.jsonl")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = read_jsonl_safely(args.decisions)[0] if args.decisions.exists() else []
    scores = [float(row["signal_score"]) for row in rows if row.get("signal_score") is not None]
    result = {"strategy_name": "scored_candidate_v1", "mode": "shadow", "decisions": len(rows), "actions": dict(Counter(row.get("action", "UNKNOWN") for row in rows)), "score_min": min(scores) if scores else None, "score_avg": sum(scores) / len(scores) if scores else None, "score_max": max(scores) if scores else None, "hard_blocks": dict(Counter(block for row in rows for block in row.get("hard_blocks", []))), "last": rows[-1] if rows else None}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else "\n".join(["Scored Candidate — shadow", f"Decisions: {result['decisions']}", f"Actions: {result['actions']}", f"Score min/avg/max: {result['score_min']} / {result['score_avg']} / {result['score_max']}", f"Hard blocks: {result['hard_blocks']}"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
