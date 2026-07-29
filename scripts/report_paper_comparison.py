from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.paper_comparator import compare_paper_runtimes, write_comparison_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare production and candidate paper runtimes")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or ROOT / "reports/runtime/comparison" / f"{datetime.now(timezone.utc).date()}.json"
    report = compare_paper_runtimes(
        production_state=ROOT / "state/trading_controller.json",
        production_trades=ROOT / "state/controller_trade_journal.jsonl",
        production_decisions=ROOT / "state/shadow_decisions.jsonl",
        candidate_state=ROOT / "state/bybit_candidate_controller.json",
        candidate_trades=ROOT / "state/bybit_candidate_trades.jsonl",
        candidate_decisions=ROOT / "state/bybit_candidate_decisions.jsonl",
    )
    write_comparison_report(report, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
