from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.paper_comparator import (
    PERIODS,
    compare_paper_runtimes,
    render_comparison_markdown,
    write_comparison_report,
    write_text_report,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Compare production and candidate paper runtimes")
    result.add_argument("--period", choices=PERIODS, default="since_candidate_start")
    result.add_argument("--timezone", default="UTC")
    result.add_argument("--output", type=Path)
    result.add_argument("--markdown-output", type=Path)
    result.add_argument("--daily", action="store_true", help="write previous-day and cumulative reports")
    return result


def _kwargs() -> dict:
    return {
        "production_state": ROOT / "state/trading_controller.json",
        "production_trades": ROOT / "state/controller_trade_journal.jsonl",
        "production_decisions": ROOT / "state/shadow_decisions.jsonl",
        "production_runtime_summary": ROOT / "state/regime_runtime.json",
        "candidate_state": ROOT / "state/bybit_candidate_controller.json",
        "candidate_trades": ROOT / "state/bybit_candidate_trades.jsonl",
        "candidate_decisions": ROOT / "state/bybit_candidate_decisions.jsonl",
        "candidate_runtime_summary": ROOT / "state/bybit_candidate_runtime.json",
    }


def _write(report: dict, json_path: Path, markdown_path: Path) -> None:
    write_comparison_report(report, json_path)
    write_text_report(render_comparison_markdown(report), markdown_path)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    base = ROOT / "reports/runtime/comparison"
    if args.daily:
        day = (now - timedelta(days=1)).date().isoformat()
        daily = compare_paper_runtimes(
            **_kwargs(), period="last_24h", now=now, timezone_name=args.timezone
        )
        cumulative = compare_paper_runtimes(
            **_kwargs(), period="since_candidate_start", now=now,
            timezone_name=args.timezone,
        )
        daily["cumulative"] = {
            "production": cumulative["production"],
            "candidate": cumulative["candidate"],
            "deltas": cumulative["deltas"],
            "decisions": cumulative["decisions"],
        }
        json_path = args.output or base / "daily" / f"{day}.json"
        markdown_path = args.markdown_output or base / "daily" / f"{day}.md"
        _write(daily, json_path, markdown_path)
        write_comparison_report(cumulative, base / "latest.json")
        print(json_path)
        return 0
    report = compare_paper_runtimes(
        **_kwargs(), period=args.period, now=now, timezone_name=args.timezone
    )
    json_path = args.output or base / "latest.json"
    markdown_path = args.markdown_output or json_path.with_suffix(".md")
    _write(report, json_path, markdown_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
