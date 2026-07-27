from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import trade_reporting
from app.trade_journal import JsonlTradeJournal
from app.trade_statistics import (
    calculate_trade_statistics,
)


DEFAULT_JOURNAL_PATH = Path("state/controller_trade_journal.jsonl")
DEFAULT_OUTPUT_PATH = Path("reports/trade_statistics.png")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a PNG report for the closed-trade journal",
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=DEFAULT_JOURNAL_PATH,
        help="path to the JSONL trade journal",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="path to the output PNG",
    )
    parser.add_argument(
        "--title",
        default="Trade Statistics",
        help="report title",
    )
    parser.add_argument("--dpi", type=positive_int, default=150)
    parser.add_argument("--width", type=positive_float, default=12.0)
    parser.add_argument("--height", type=positive_float, default=9.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        entries = JsonlTradeJournal(args.journal).read_all()
        statistics = calculate_trade_statistics(entries)
        trade_reporting.save_trade_statistics_plot(
            statistics,
            args.output,
            title=args.title,
            dpi=args.dpi,
            width=args.width,
            height=args.height,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Failed to create trade statistics report: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
