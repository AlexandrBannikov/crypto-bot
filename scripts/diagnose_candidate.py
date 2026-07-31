from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.candidate_diagnostics import render_candidate_diagnostics, summarize_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only candidate diagnostics")
    period = parser.add_mutually_exclusive_group()
    period.add_argument("--hours", type=float)
    period.add_argument("--days", type=float)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--decisions", type=Path, default=ROOT / "state/bybit_candidate_decisions.jsonl")
    parser.add_argument("--trades", type=Path, default=ROOT / "state/bybit_candidate_trades.jsonl")
    args = parser.parse_args()
    end = datetime.now(timezone.utc)
    amount = args.hours if args.hours is not None else (args.days * 24 if args.days is not None else None)
    start = end - timedelta(hours=amount) if amount is not None else None
    report = summarize_candidate(args.decisions, args.trades, start=start, end=end)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_candidate_diagnostics(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
