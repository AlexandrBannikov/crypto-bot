from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_loader import load_market_data
from app.strategy_v2_filters import (
    PullbackFilterConfig,
    PullbackTouchMode,
)
from app.strategy_v2_research import (
    PULLBACK_VARIANTS,
    StrategyV2Config,
    metadata,
    run_pullback_comparison,
    run_pullback_period,
    run_pullback_walk_forward,
    summarize_pullback_walk_forward,
)
from scripts.compare_strategy_v2_filters import write_csv, write_json


DEFAULT_DATA = PROJECT_ROOT / "data/eth_usdt_1h_full.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "reports/strategy_v2"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare Strategy v2 ATR/ADX/pullback entry filters"
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser


def run_sensitivity(data, config: StrategyV2Config) -> list[dict]:
    rows: list[dict] = []
    boundary = data["datetime"] < config.train_end
    trade_start_index = int(boundary.sum())
    for touch_mode in PullbackTouchMode:
        for max_wait_bars in (3, 5, 8):
            candidate = replace(
                config,
                pullback=PullbackFilterConfig(
                    enabled=True,
                    max_wait_bars=max_wait_bars,
                    touch_mode=touch_mode,
                ),
            )
            for period, start_index in (
                ("full", 0),
                ("oos", trade_start_index),
            ):
                result, _ = run_pullback_period(
                    data,
                    period=period,
                    variant="pullback",
                    config=candidate,
                    trade_start_index=start_index,
                )
                rows.append(
                    {
                        "period": period,
                        "max_wait_bars": max_wait_bars,
                        "touch_mode": touch_mode.value,
                        **asdict(result),
                    }
                )
    return rows


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = StrategyV2Config()
    data = load_market_data(args.data).iloc[:-1].copy()
    comparison = run_pullback_comparison(data, config)
    windows = run_pullback_walk_forward(data, config)
    sensitivity = run_sensitivity(data, config)
    summary = {
        "variants": list(PULLBACK_VARIANTS),
        "fixed_pullback": {
            "max_wait_bars": config.pullback.max_wait_bars,
            "touch_mode": config.pullback.touch_mode.value,
        },
        "comparison": [asdict(item) for item in comparison],
        "walk_forward": summarize_pullback_walk_forward(windows),
        "sensitivity": sensitivity,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "pullback_comparison.csv",
        comparison,
    )
    write_csv(
        args.output_dir / "pullback_walk_forward_windows.csv",
        windows,
    )
    write_json(args.output_dir / "pullback_summary.json", summary)
    write_json(
        args.output_dir / "metadata.json",
        metadata(
            root=PROJECT_ROOT,
            data_path=args.data,
            data=data,
            config=config,
        ),
    )
    print(
        json.dumps(
            {
                "comparison_rows": len(comparison),
                "walk_forward_rows": len(windows),
                "sensitivity_rows": len(sensitivity),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
