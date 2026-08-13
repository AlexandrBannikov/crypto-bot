"""Print research-only aggregate statistics for production trade cards."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trade_diagnostics import TradeDiagnosticsJournal, aggregate_trade_diagnostics


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Research-only PAPER trade diagnostics")
    value.add_argument(
        "--journal", type=Path,
        default=Path("state/production_trade_diagnostics.jsonl"),
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    statistics = aggregate_trade_diagnostics(
        TradeDiagnosticsJournal(args.journal).read_all()
    )
    print(json.dumps(statistics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
