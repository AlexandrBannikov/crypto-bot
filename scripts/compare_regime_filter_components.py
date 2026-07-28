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
    build_component_analysis,
    config_dict,
    fingerprint_candles,
    run_policy_walk_forward,
)
from app.regime_filtered_strategy import (
    EntryBlockPolicy,
    EntryBlockReason,
)


DEFAULT_DATA_PATH = PROJECT_ROOT / "data/eth_usdt_1h_full.csv"
SELECTED_WINDOW_VARIANTS = (
    "range_only",
    "range_high_volatility",
    "filtered",
)


def policy(*names: str) -> EntryBlockPolicy:
    reasons = []
    for name in names:
        try:
            reasons.append(EntryBlockReason(name))
        except ValueError as exc:
            raise ValueError(f"unknown block reason: {name}") from exc
    return EntryBlockPolicy(frozenset(reasons))


VARIANT_POLICIES = {
    "baseline": None,
    "detector_only": EntryBlockPolicy.empty(),
    "range_only": policy("range"),
    "high_volatility_only": policy("high_volatility"),
    "downtrend_only": policy("downtrend"),
    "low_confidence_only": policy("low_confidence"),
    "unknown_only": policy("unknown_regime"),
    "range_high_volatility": policy("range", "high_volatility"),
    "filtered": EntryBlockPolicy.full(),
}


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


def build_parser() -> argparse.ArgumentParser:
    defaults = ResearchConfig()
    parser = argparse.ArgumentParser(
        description="Component ablation for the EMA regime filter",
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
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
        "--fast-period",
        type=positive_int,
        default=defaults.fast_ema,
    )
    parser.add_argument(
        "--slow-period",
        type=positive_int,
        default=defaults.slow_ema,
    )
    parser.add_argument(
        "--initial-balance",
        type=float,
        default=defaults.initial_balance,
    )
    parser.add_argument(
        "--fee-rate",
        type=non_negative_float,
        default=defaults.fee_rate,
    )
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-csv", type=Path)
    return parser


def config_from_args(args: argparse.Namespace) -> ResearchConfig:
    return ResearchConfig(
        fast_ema=args.fast_period,
        slow_ema=args.slow_period,
        fee_rate=args.fee_rate,
        initial_balance=args.initial_balance,
        train_months=args.train_months,
        test_months=args.test_months,
        step_months=args.step_months,
    )


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def build_report(data, data_path: Path, config: ResearchConfig, results):
    variants = tuple(VARIANT_POLICIES)
    return {
        "parameters": {
            **config_dict(config),
            "data": str(data_path.resolve()),
        },
        "data_fingerprint_sha256": fingerprint_candles(
            dataframe_to_candles(data)
        ),
        "variants": {
            name: (
                None
                if block_policy is None
                else sorted(
                    reason.value
                    for reason in block_policy.blocked_reasons
                )
            )
            for name, block_policy in VARIANT_POLICIES.items()
        },
        "window_results": [asdict(item) for item in results],
        **build_component_analysis(
            results,
            variants,
            config.initial_balance,
        ),
    }


def save_json(path: Path, report: dict[str, object]) -> None:
    content = json.dumps(
        json_safe(report),
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
    print("Component aggregates")
    print(
        f"{'Variant':<24}{'Compound':>11}{'Mean DD':>10}"
        f"{'Max DD':>10}{'Trades':>9}{'Fees':>11}{'Blocked':>10}"
    )
    for variant, summary in report["summary"].items():
        print(
            f"{variant:<24}"
            f"{summary['compounded_return_percent']:>+10.2f}%"
            f"{summary['mean_maximum_drawdown_percent']:>9.2f}%"
            f"{summary['worst_maximum_drawdown_percent']:>9.2f}%"
            f"{summary['total_trades']:>9}"
            f"{summary['total_fees']:>11.2f}"
            f"{summary['total_blocked_entries']:>10}"
        )
        reasons = summary["blocked_by_reason"]
        if summary["total_blocked_entries"]:
            print(
                "  reasons: "
                + ", ".join(
                    f"{name}={count}"
                    for name, count in reasons.items()
                )
            )

    print("\nComparison to baseline")
    print(
        f"{'Variant':<24}{'Better':>8}{'Worse':>8}{'Lower DD':>10}"
        f"{'Both':>8}{'ΔCompound':>12}{'ΔMean DD':>11}"
        f"{'ΔFees':>11}{'ΔTrades':>10}"
    )
    for variant, item in report["comparison_to_baseline"].items():
        print(
            f"{variant:<24}"
            f"{item['better_return_windows']:>8}"
            f"{item['worse_return_windows']:>8}"
            f"{item['lower_drawdown_windows']:>10}"
            f"{item['better_return_and_drawdown_windows']:>8}"
            f"{item['compounded_return_difference_points']:>+11.2f}"
            f"{item['mean_drawdown_difference_points']:>+10.2f}"
            f"{item['fees_difference']:>+11.2f}"
            f"{item['trades_difference']:>+10}"
        )

    print("\nSelected component windows")
    print(
        f"{'Win':>3} {'Test':<23} {'Variant':<24}"
        f"{'Return':>10}{'DD':>9}{'Trades':>9}{'Blocked':>10}"
    )
    for item in report["window_results"]:
        if item["variant"] not in SELECTED_WINDOW_VARIANTS:
            continue
        period = f"{item['test_start'][:10]}..{item['test_end'][:10]}"
        print(
            f"{item['window_number']:>3} {period:<23}"
            f" {item['variant']:<24}"
            f"{item['return_percent']:>+9.2f}%"
            f"{item['maximum_drawdown_percent']:>8.2f}%"
            f"{item['trade_count']:>9}"
            f"{item['blocked_entries']:>10}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = config_from_args(args)
        config.validate()
        data = load_market_data(args.data)
        results = run_policy_walk_forward(
            data,
            config,
            VARIANT_POLICIES,
        )
        report = build_report(data, args.data, config, results)
        print_report(report)
        if args.output_json:
            save_json(args.output_json, report)
        if args.output_csv:
            save_csv(args.output_csv, results)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
