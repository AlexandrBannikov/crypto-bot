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
        print(f"Duplicates: {result['duplicates']}")
        print(f"Invalid values: {result['invalid_values'] + result['missing_fields'] + result['negative_equity']}")
        print(f"Large gaps: {result['large_gaps']}")
        print(f"Last snapshot age: {result['last_snapshot_age_minutes']} min")
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
