from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.equity_integrity import check_equity_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only equity history integrity check")
    parser.add_argument("--mode", choices=("production", "candidate"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--database", type=Path, default=ROOT / "state/equity_history.db")
    args = parser.parse_args()
    result = check_equity_history(args.database, mode=args.mode)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Equity history: {result['status']}")
        print(f"Snapshots: {result['snapshots']}")
        print(f"Exact duplicates: {result['exact_duplicates']}")
        print(f"Timestamp duplicates: {result['timestamp_duplicates']}")
        print(f"Timestamp conflicts: {result['timestamp_conflicts']}")
        print(f"Cross-mode collisions: {result['cross_mode_collisions']}")
        print(f"Invalid values: {result['invalid_values'] + result['missing_fields'] + result['negative_equity']}")
        print(f"Gaps: {result['large_gaps']}")
        for gap in result["gaps"]:
            print(
                f"  {gap['mode']}/{gap['strategy']}: "
                f"{gap['previous_timestamp']} -> {gap['next_timestamp']} "
                f"({gap['duration_seconds']}s, expected {gap['expected_interval_seconds']}s, "
                f"missing ~{gap['estimated_missing_snapshots']}, {gap['classification']})"
            )
        print(f"Last snapshot age: {result['last_snapshot_age_minutes']} min")
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
