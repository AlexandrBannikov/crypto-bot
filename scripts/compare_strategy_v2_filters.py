from __future__ import annotations

import argparse
import csv
import io
import json
import math
from dataclasses import asdict
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_loader import load_market_data
from app.regime_filter_research import atomic_write
from app.strategy_v2_research import (
    StrategyV2Config,
    VARIANTS,
    metadata,
    run_comparison,
    run_walk_forward,
    summarize_walk_forward,
)


DEFAULT_DATA = PROJECT_ROOT / "data/eth_usdt_1h_full.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "reports/strategy_v2"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare independent Strategy v2 ATR/ADX filters"
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def write_csv(path: Path, rows) -> None:
    values = [asdict(row) for row in rows]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(values[0]))
    writer.writeheader()
    writer.writerows(values)
    atomic_write(path, output.getvalue())


def write_json(path: Path, payload: object) -> None:
    atomic_write(
        path,
        json.dumps(
            _json_safe(payload),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n",
    )


def print_comparison(rows) -> None:
    print(
        f"{'Period':<7}{'Variant':<10}{'Return':>10}{'Ann.':>10}"
        f"{'DD':>9}{'PF':>9}{'Trades':>8}{'Exposure':>10}"
        f"{'Fees':>10}{'ATR blk':>9}{'ADX blk':>9}"
    )
    for row in rows:
        print(
            f"{row.period:<7}{row.variant:<10}"
            f"{row.total_return_percent:>+9.2f}%"
            f"{row.annualized_return_percent:>+9.2f}%"
            f"{row.maximum_drawdown_percent:>8.2f}%"
            f"{row.profit_factor:>9.2f}"
            f"{row.trades:>8}"
            f"{row.exposure_percent:>9.2f}%"
            f"{row.total_fees:>10.2f}"
            f"{row.blocked_by_atr:>9}"
            f"{row.blocked_by_adx:>9}"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = StrategyV2Config()
    data = load_market_data(args.data).iloc[:-1].copy()
    comparison = run_comparison(data, config)
    windows = run_walk_forward(data, config)
    summary = {
        "comparison": [asdict(item) for item in comparison],
        "walk_forward": summarize_walk_forward(windows),
        "variants": list(VARIANTS),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "comparison_full_train_oos.csv",
        comparison,
    )
    write_csv(
        args.output_dir / "walk_forward_windows.csv",
        windows,
    )
    write_json(args.output_dir / "summary.json", summary)
    write_json(
        args.output_dir / "metadata.json",
        metadata(
            root=PROJECT_ROOT,
            data_path=args.data,
            data=data,
            config=config,
        ),
    )
    print_comparison(comparison)
    print(f"Reports: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
