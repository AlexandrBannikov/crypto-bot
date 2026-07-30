from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_loader import load_market_data
from app.engine import Candle
from app.strategy_diagnostics import (
    DiagnosticJournal,
    format_diagnostic_summary,
    summarize_diagnostics,
)
from app.strategy_experiments import (
    format_experiment_table,
    run_experiments,
)


DEFAULT_DATA = Path("data/eth_usdt_1h_full.csv")
DEFAULT_OUTPUT = Path("reports/strategy_diagnostics.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run EMA diagnostics and train/test comparisons."
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--no-json", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.journal is not None:
        summary = summarize_diagnostics(
            DiagnosticJournal(args.journal).read_all()
        )
        print(format_diagnostic_summary(summary))
        if not args.no_json:
            _save_json(args.output, {"journal_summary": summary.to_dict()})
        return

    frame = load_market_data(args.data)
    candles = tuple(
        Candle(
            timestamp=int(row.datetime.timestamp()),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in frame.itertuples(index=False)
    )
    results = run_experiments(
        candles,
        train_fraction=args.train_fraction,
        initial_balance=1000.0,
        commission_rate=0.001,
    )
    print(f"Data: {frame.iloc[0]['datetime']} — {frame.iloc[-1]['datetime']}")
    print("Fee: 0.1000%; chronological train/test split")
    print(format_experiment_table(results))
    print(
        "\nDo not select a configuration by return alone: compare drawdown, "
        "monthly stability, trade count, and test performance."
    )
    if not args.no_json:
        _save_json(
            args.output,
            {
                "data_file": str(args.data),
                "commission_rate": 0.001,
                "train_fraction": args.train_fraction,
                "results": [result.to_dict() for result in results],
            },
        )
        print(f"JSON report: {args.output}")


def _save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
