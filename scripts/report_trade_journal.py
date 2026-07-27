from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import trade_reporting
from app.trade_journal import JsonlTradeJournal, TradeJournalEntry
from app.trade_statistics import (
    TradeStatistics,
    calculate_trade_statistics,
)


DEFAULT_JOURNAL_PATH = Path(
    "state/controller_trade_journal.jsonl"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Отчёт по журналу закрытых сделок",
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=DEFAULT_JOURNAL_PATH,
        help="путь к JSONL-журналу",
    )
    return parser


def format_statistics(statistics: TradeStatistics) -> list[str]:
    return trade_reporting.format_trade_statistics(statistics)


def render_report(
    entries: list[TradeJournalEntry],
) -> str:
    statistics = calculate_trade_statistics(entries)
    return trade_reporting.format_trade_report(entries, statistics)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    entries = JsonlTradeJournal(args.journal).read_all()
    print(render_report(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
