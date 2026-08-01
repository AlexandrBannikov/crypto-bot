from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime_health import read_jsonl_safely
from app.scored_candidate import ScoredCandidateStateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional threshold-60 experiment health")
    runtime = ROOT / "state/scored_candidate_threshold60"
    parser.add_argument("--state", type=Path, default=runtime / "runtime.json")
    parser.add_argument("--decisions", type=Path, default=runtime / "decisions.jsonl")
    args = parser.parse_args()
    state = ScoredCandidateStateStore(args.state).load()
    rows = read_jsonl_safely(args.decisions)[0] if args.decisions.exists() else []
    last = rows[-1] if rows else {}
    print(json.dumps({"scored_threshold60": {
        "required": False,
        "status": "initialized" if state.last_candle is not None and rows else "disabled",
        "last_candle": last.get("candle_close_timestamp"),
        "last_score": last.get("signal_score"),
        "last_decision": last.get("decision", last.get("action")),
        "decisions_count": len(rows),
    }}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
