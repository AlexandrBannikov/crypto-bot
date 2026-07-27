from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.candle_mapper import dataframe_to_candles
from app.data_loader import load_market_data
from app.regime_filter_research import (
    ResearchConfig,
    atomic_write,
    build_analysis,
    config_dict,
    fingerprint_candles,
    run_walk_forward,
)


DEFAULT_DATA_PATH = PROJECT_ROOT / "data/eth_usdt_1h_full.csv"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return parsed


def confidence(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    defaults = ResearchConfig()
    parser = argparse.ArgumentParser(
        description="Rolling walk-forward research for EMA regime filter",
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument(
        "--fast-ema", type=positive_int, default=defaults.fast_ema
    )
    parser.add_argument(
        "--slow-ema", type=positive_int, default=defaults.slow_ema
    )
    parser.add_argument(
        "--fee-rate",
        type=non_negative_float,
        default=defaults.fee_rate,
    )
    parser.add_argument(
        "--initial-balance",
        type=float,
        default=defaults.initial_balance,
    )
    parser.add_argument(
        "--train-months",
        type=positive_int,
        default=defaults.train_months,
    )
    parser.add_argument(
        "--test-months",
        type=positive_int,
        default=defaults.test_months,
    )
    parser.add_argument(
        "--step-months",
        type=positive_int,
        default=defaults.step_months,
    )
    parser.add_argument(
        "--adx-period",
        type=positive_int,
        default=defaults.adx_period,
    )
    parser.add_argument(
        "--adx-threshold",
        type=non_negative_float,
        default=defaults.adx_threshold,
    )
    parser.add_argument(
        "--atr-period",
        type=positive_int,
        default=defaults.atr_period,
    )
    parser.add_argument(
        "--low-volatility-threshold",
        type=non_negative_float,
        default=defaults.low_volatility_threshold,
    )
    parser.add_argument(
        "--high-volatility-threshold",
        type=non_negative_float,
        default=defaults.high_volatility_threshold,
    )
    parser.add_argument(
        "--minimum-confidence",
        type=confidence,
        default=defaults.minimum_confidence,
    )
    parser.add_argument("--max-windows", type=positive_int)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    return parser


def config_from_args(args: argparse.Namespace) -> ResearchConfig:
    return ResearchConfig(
        fast_ema=args.fast_ema,
        slow_ema=args.slow_ema,
        fee_rate=args.fee_rate,
        initial_balance=args.initial_balance,
        train_months=args.train_months,
        test_months=args.test_months,
        step_months=args.step_months,
        adx_period=args.adx_period,
        adx_threshold=args.adx_threshold,
        atr_period=args.atr_period,
        low_volatility_threshold=args.low_volatility_threshold,
        high_volatility_threshold=args.high_volatility_threshold,
        minimum_confidence=args.minimum_confidence,
        max_windows=args.max_windows,
    )


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def build_report(data, data_path: Path, config: ResearchConfig, results):
    analysis = build_analysis(results, config.initial_balance)
    return {
        "parameters": {
            **config_dict(config),
            "data": str(data_path.resolve()),
        },
        "data_fingerprint_sha256": fingerprint_candles(
            dataframe_to_candles(data)
        ),
        "data_range": {
            "start": data["datetime"].min().isoformat(),
            "end": data["datetime"].max().isoformat(),
            "candles": len(data),
        },
        "strategies": {
            "baseline": f"EMACrossStrategy({config.fast_ema}/{config.slow_ema})",
            "detector_only": "RegimeFilteredStrategy(apply_filter=False)",
            "filtered": "RegimeFilteredStrategy(apply_filter=True)",
        },
        "window_results": [asdict(item) for item in results],
        **analysis,
    }


def save_json(path: Path, report: dict[str, object]) -> None:
    content = json.dumps(
        _json_safe(report),
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    atomic_write(path, content + "\n")


def save_csv(path: Path, results) -> None:
    rows = [asdict(item) for item in results]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, output.getvalue())


def print_report(report: dict[str, object]) -> None:
    results = report["window_results"]
    print(
        f"{'Win':>3} {'Test period':<23} {'Variant':<14} "
        f"{'Return':>9} {'DD':>8} {'PF':>8} {'Trades':>7} {'Blocked':>8}"
    )
    for item in results:
        period = f"{item['test_start'][:10]}..{item['test_end'][:10]}"
        print(
            f"{item['window_number']:>3} {period:<23} {item['variant']:<14} "
            f"{item['return_percent']:>+8.2f}% "
            f"{item['maximum_drawdown_percent']:>7.2f}% "
            f"{item['profit_factor']:>8.2f} "
            f"{item['trade_count']:>7} {item['blocked_entries']:>8}"
        )
    print()
    for variant, summary in report["summary"].items():
        print(
            f"{variant}: mean={summary['mean_return_percent']:+.2f}%, "
            f"median={summary['median_return_percent']:+.2f}%, "
            f"worst={summary['worst_return_percent']:+.2f}%, "
            f"trades={summary['total_trades']}"
        )
    compounded = report["compounded_diagnostics"]
    print(
        "Compounded diagnostic: "
        f"baseline={compounded['baseline_compounded_final_balance']:.2f}, "
        f"filtered={compounded['filtered_compounded_final_balance']:.2f}"
    )
    print(f"Verdict: {report['verdict']}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = config_from_args(args)
        config.validate()
        data = load_market_data(args.data)
        results = run_walk_forward(data, config)
        report = build_report(data, args.data, config, results)
        print_report(report)
        if args.json_output:
            save_json(args.json_output, report)
        if args.csv_output:
            save_csv(args.csv_output, results)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
