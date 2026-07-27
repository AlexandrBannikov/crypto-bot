from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.report_paper_daily as daily
import scripts.report_paper_weekly as weekly


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate missing runtime daily and weekly reports")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--daily-only", action="store_true")
    mode.add_argument("--weekly-only", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--timezone", default="UTC")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    zone = ZoneInfo(args.timezone)
    today = datetime.now(zone).date()
    daily_day = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday() + 7)
    jobs = []
    if not args.weekly_only:
        base = PROJECT_ROOT / "reports/runtime/daily" / daily_day.isoformat()
        jobs.append((daily.create_report, daily.parser().parse_args(["--date", daily_day.isoformat(), "--timezone", args.timezone, "--json-output", str(base.with_suffix(".json")), "--text-output", str(base.with_suffix(".txt"))]), base))
    if not args.daily_only:
        base = PROJECT_ROOT / "reports/runtime/weekly" / f"{week_start.isoformat()}_week"
        jobs.append((weekly.create_report, weekly.parser().parse_args(["--week-start", week_start.isoformat(), "--timezone", args.timezone, "--json-output", str(base.with_suffix(".json")), "--text-output", str(base.with_suffix(".txt"))]), base))
    for function, report_args, base in jobs:
        outputs = (base.with_suffix(".json"), base.with_suffix(".txt"))
        if all(path.exists() for path in outputs) and not args.force:
            print(f"skip existing report: {base}")
            continue
        function(report_args)
        print(f"created report: {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
