from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.equity_integrity import check_equity_history


def _backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"equity-history-{stamp}.db")
    source = sqlite3.connect(path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    shutil.copymode(path, target)
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run equity history repair")
    parser.add_argument("--mode", choices=("production", "candidate"), required=True)
    parser.add_argument("--database", type=Path, default=ROOT / "state/equity_history.db")
    parser.add_argument("--dry-run", action="store_true", help="inspect only (default)")
    parser.add_argument("--apply", action="store_true", help="apply approved exact/equivalent deduplication")
    parser.add_argument("--deduplicate-exact", action="store_true")
    parser.add_argument("--deduplicate-equivalent", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.apply:
        args.dry_run = True
    result = check_equity_history(args.database, mode=args.mode)
    groups = result["duplicate_groups"]
    requested = set()
    if args.deduplicate_exact:
        requested.add("exact")
    if args.deduplicate_equivalent:
        requested.add("equivalent")
    plan = [item for item in groups if item["type"] in requested]
    conflicts = [item for item in groups if item["type"] == "conflict"]
    payload = {"mode": args.mode, "dry_run": not args.apply, "integrity": result, "planned_groups": plan, "conflicts_blocking": conflicts, "planned_deletions": sum(max(0, len(item["ids"]) - 1) for item in plan)}
    if args.apply:
        if not requested:
            print("Refusing --apply without --deduplicate-exact or --deduplicate-equivalent", file=sys.stderr)
            return 2
        if conflicts:
            print("Refusing repair: timestamp conflicts require manual review", file=sys.stderr)
            return 2
        if not args.database.exists():
            print("Database does not exist", file=sys.stderr)
            return 2
        backup = _backup(args.database)
        payload["backup"] = str(backup)
        with sqlite3.connect(args.database) as connection:
            for group in plan:
                for row_id in group["ids"][1:]:
                    connection.execute("DELETE FROM equity_snapshots WHERE id=?", (row_id,))
        all_integrity = check_equity_history(args.database)
        if all_integrity["timestamp_duplicates"] == 0 and all_integrity["timestamp_conflicts"] == 0:
            with sqlite3.connect(args.database) as connection:
                connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_equity_canonical ON equity_snapshots(environment, strategy_name, candle_close_timestamp)")
        payload["after"] = check_equity_history(args.database, mode=args.mode)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print("Equity history repair: DRY-RUN" if not args.apply else "Equity history repair: APPLIED")
        print(f"Mode: {args.mode}")
        print(f"Planned deletions: {payload['planned_deletions']}")
        if payload.get("backup"):
            print(f"Backup: {payload['backup']}")
        if conflicts:
            print(f"Blocking timestamp conflicts: {len(conflicts)}")
        if args.apply:
            print(f"After status: {payload['after']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
