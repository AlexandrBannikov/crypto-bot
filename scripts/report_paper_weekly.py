from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.paper_runtime_reports import load_period_data, shadow_summary, trade_summary, write_report
from app.runtime_health import overall_status, run_health_checks


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create Monday-to-Monday paper weekly report")
    p.add_argument("--week-start", help="Monday date YYYY-MM-DD; defaults to current week's Monday")
    p.add_argument("--timezone", default="UTC")
    p.add_argument("--state-path", type=Path, default=PROJECT_ROOT / "state/trading_controller.json")
    p.add_argument("--journal-path", type=Path, default=PROJECT_ROOT / "state/controller_trade_journal.jsonl")
    p.add_argument("--shadow-path", type=Path, default=PROJECT_ROOT / "state/shadow_decisions.jsonl")
    p.add_argument("--json-output", type=Path)
    p.add_argument("--text-output", type=Path)
    return p


def create_report(args: argparse.Namespace) -> dict:
    zone = ZoneInfo(args.timezone)
    today = datetime.now(zone).date()
    day = datetime.strptime(args.week_start, "%Y-%m-%d").date() if args.week_start else today - timedelta(days=today.weekday())
    if day.weekday() != 0:
        raise ValueError("--week-start must be a Monday")
    start = datetime.combine(day, datetime.min.time(), zone)
    end = start + timedelta(days=7)
    state, trades, shadows = load_period_data(args.state_path, args.journal_path, args.shadow_path, start, end)
    summary = trade_summary(trades)
    ending = trades[-1].virtual_balance_after if trades else state.virtual_balance
    beginning = ending - Decimal(summary["realised_pnl"])
    daily = []
    for offset in range(7):
        ds, de = start + timedelta(days=offset), start + timedelta(days=offset + 1)
        subset = [t for t in trades if ds <= datetime.fromisoformat(t.closed_at.replace("Z", "+00:00")) < de]
        daily.append({"date": ds.date().isoformat(), **trade_summary(subset)})
    checks, _ = run_health_checks(
        state_path=args.state_path, candle_path=args.state_path.parent / "trading_controller_last_candle.txt",
        journal_path=args.journal_path, shadow_path=args.shadow_path,
        lock_path=PROJECT_ROOT / "state/bybit_controller.lock", no_network=True,
    )
    report = {
        "report_type": "weekly", "timezone": args.timezone,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "beginning_balance": str(beginning), "ending_balance": str(ending),
        "weekly_return_percentage": float((ending - beginning) / beginning * 100) if beginning else None,
        **summary, "shadow": shadow_summary(shadows), "daily_breakdown": daily,
        "health_summary": {"overall_status": overall_status(checks).name, "checks": {c.name: c.status.name for c in checks}},
    }
    write_report(report, args.json_output, args.text_output)
    return report


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        report = create_report(args)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"weekly report error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
