from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.equity_integrity import check_equity_history


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only equity duplicate classifier")
    parser.add_argument("--database", type=Path, default=ROOT / "state/equity_history.db")
    parser.add_argument("--environment", choices=("production", "candidate"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = check_equity_history(args.database, mode=args.environment)
    payload = {"mode": "dry-run", "database": str(args.database), "would_delete": 0,
               "apply_supported": False, "exact_duplicates": result["exact_duplicates"],
               "semantic_duplicates": result["semantic_duplicates"],
               "expected_multi_reason_snapshots": result["expected_multi_reason_snapshots"],
               "groups": result["duplicate_groups"]}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else
          f"Dry-run only; would delete: 0\nExact duplicates: {payload['exact_duplicates']}\nSemantic duplicates: {payload['semantic_duplicates']}\nExpected multi-reason snapshots: {payload['expected_multi_reason_snapshots']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
