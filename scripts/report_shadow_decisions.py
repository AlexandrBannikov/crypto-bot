from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.shadow_decision_journal import ShadowDecisionJournal
from app.trading_types import TradeAction


DEFAULT_INPUT = PROJECT_ROOT / "state/shadow_decisions.jsonl"
ENTRY_ACTIONS = {
    TradeAction.OPEN_LONG.value,
    TradeAction.OPEN_SHORT.value,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize paper shadow strategy decisions",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--from", dest="from_time", type=parse_time)
    parser.add_argument("--to", dest="to_time", type=parse_time)
    parser.add_argument("--symbol")
    parser.add_argument("--timeframe")
    return parser


def parse_time(value: str) -> int:
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "time must be an ISO-8601 datetime"
        ) from exc


def build_summary(records) -> dict[str, object]:
    evaluated = [
        item for item in records
        if item.baseline_signal in ENTRY_ACTIONS
    ]
    reasons = Counter(
        item.blocked_reason
        for item in evaluated
        if item.blocked and item.blocked_reason
    )
    allowed = sum(item.allowed is True for item in evaluated)
    blocked = sum(item.blocked for item in evaluated)
    same = sum(
        item.baseline_signal == item.filtered_signal
        for item in records
    )
    return {
        "records": len(records),
        "evaluated_entries": len(evaluated),
        "allowed_entries": allowed,
        "blocked_entries": blocked,
        "blocked_by_reason": dict(sorted(reasons.items())),
        "baseline_only_entries": sum(
            item.baseline_signal in ENTRY_ACTIONS
            and item.filtered_signal not in ENTRY_ACTIONS
            for item in records
        ),
        "filtered_only_entries": sum(
            item.filtered_signal in ENTRY_ACTIONS
            and item.baseline_signal not in ENTRY_ACTIONS
            for item in records
        ),
        "identical_decisions": same,
        "detector_errors": sum(
            item.detector_error is not None for item in records
        ),
        "agreement_percent": (
            same / len(records) * 100 if records else 0.0
        ),
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records = ShadowDecisionJournal(args.input).read_all()
    records = [
        item
        for item in records
        if (
            (args.from_time is None or item.candle_timestamp >= args.from_time)
            and (args.to_time is None or item.candle_timestamp <= args.to_time)
            and (args.symbol is None or item.symbol == args.symbol)
            and (args.timeframe is None or item.timeframe == args.timeframe)
        )
    ]
    summary = build_summary(records)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json_output is not None:
        atomic_write(
            args.json_output,
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
