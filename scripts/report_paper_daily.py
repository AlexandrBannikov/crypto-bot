from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.paper_runtime_reports import load_period_data, shadow_summary, trade_summary, write_report
from app.runtime_health import overall_status, run_health_checks


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create paper report for one calendar day (current UTC date by default)")
    p.add_argument("--date", help="calendar date YYYY-MM-DD")
    p.add_argument("--timezone", default="UTC")
    p.add_argument("--state-path", type=Path, default=PROJECT_ROOT / "state/trading_controller.json")
    p.add_argument("--journal-path", type=Path, default=PROJECT_ROOT / "state/controller_trade_journal.jsonl")
    p.add_argument("--shadow-path", type=Path, default=PROJECT_ROOT / "state/shadow_decisions.jsonl")
    p.add_argument("--json-output", type=Path)
    p.add_argument("--text-output", type=Path)
    return p


def create_report(args: argparse.Namespace) -> dict:
    zone = ZoneInfo(args.timezone)
    day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(zone).date()
    start = datetime.combine(day, datetime.min.time(), zone)
    end = start + timedelta(days=1)
    state, trades, shadows = load_period_data(args.state_path, args.journal_path, args.shadow_path, start, end)
    summary = trade_summary(trades)
    ending = trades[-1].virtual_balance_after if trades else state.virtual_balance
    beginning = ending - Decimal(summary["realised_pnl"])
    checks, _ = run_health_checks(
        state_path=args.state_path, candle_path=args.state_path.parent / "trading_controller_last_candle.txt",
        journal_path=args.journal_path, shadow_path=args.shadow_path,
        lock_path=PROJECT_ROOT / "state/bybit_controller.lock", no_network=True,
    )
    candle_path = args.state_path.parent / "trading_controller_last_candle.txt"
    report = {
        "report_type": "daily", "timezone": args.timezone,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "beginning_balance": str(beginning), "ending_balance": str(ending),
        **summary, "unrealised_pnl": None,
        "open_position_at_end": {
            "side": "long" if state.has_open_position else "flat",
            "quantity": str(state.position_quantity), "entry_price": str(state.entry_price) if state.entry_price else None,
        },
        "shadow": shadow_summary(shadows),
        "latest_candle": int(candle_path.read_text().strip()) if candle_path.exists() else None,
        "health_status": overall_status(checks).name,
    }
    write_report(report, args.json_output, args.text_output)
    return report


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        report = create_report(args)
        print(__import__("json").dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"daily report error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
