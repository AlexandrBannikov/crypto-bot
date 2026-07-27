from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.candle_mapper import dataframe_to_candles
from app.candle import Candle
from app.data_loader import load_market_data
from app.ema_cross_strategy import EMACrossStrategy
from app.engine import BacktestEngine, BacktestResult
from app.market_regime import MarketRegime, MarketRegimeDetector
from app.regime_filtered_strategy import (
    EntryBlockReason,
    RegimeFilteredStrategy,
)
from app.trading_filter import TradingFilter


DEFAULT_DATA_PATH = PROJECT_ROOT / "data/eth_usdt_1h_full.csv"
DEFAULT_FAST_EMA = 20
DEFAULT_SLOW_EMA = 50
DEFAULT_COMMISSION = 0.001
DEFAULT_INITIAL_BALANCE = 1000.0
DEFAULT_ADX_PERIOD = 14
DEFAULT_ADX_THRESHOLD = 20.0
DEFAULT_ATR_PERIOD = 14
DEFAULT_LOW_VOLATILITY_THRESHOLD = 0.005
DEFAULT_HIGH_VOLATILITY_THRESHOLD = 0.02
DEFAULT_MINIMUM_CONFIDENCE = 0.0
TEST_START = pd.Timestamp("2025-01-01", tz="UTC")


class CachingRegimeDetector:
    def __init__(self, detector: MarketRegimeDetector) -> None:
        self.detector = detector
        self._cache: dict[bytes, MarketRegime] = {}

    def detect(
        self,
        candles: Sequence[Candle],
    ) -> MarketRegime:
        key = self._fingerprint(candles)
        if key not in self._cache:
            self._cache[key] = self.detector.detect(candles)
        return self._cache[key]

    @staticmethod
    def _fingerprint(candles: Sequence[Candle]) -> bytes:
        digest = hashlib.blake2b(digest_size=20)
        for candle in candles:
            digest.update(
                struct.pack(
                    "!q5d",
                    candle.timestamp,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                )
            )
        return digest.digest()


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    period: str
    variant: str
    final_balance: float
    return_percent: float
    trades: int
    win_rate_percent: float
    profit_factor: float
    maximum_drawdown_percent: float
    total_fees: float
    allowed_entries: int
    blocked_entries: int
    blocked_range: int
    blocked_downtrend: int
    blocked_high_volatility: int
    blocked_low_confidence: int
    blocked_unknown_regime: int


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            "must be greater than zero"
        )
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(
            "must not be negative"
        )
    return parsed


def confidence(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(
            "must be between 0 and 1"
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare EMA strategy market-regime entry filters"
        ),
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_PATH,
    )
    parser.add_argument(
        "--fast-ema",
        type=positive_int,
        default=DEFAULT_FAST_EMA,
    )
    parser.add_argument(
        "--slow-ema",
        type=positive_int,
        default=DEFAULT_SLOW_EMA,
    )
    parser.add_argument(
        "--commission",
        type=non_negative_float,
        default=DEFAULT_COMMISSION,
    )
    parser.add_argument(
        "--initial-balance",
        type=float,
        default=DEFAULT_INITIAL_BALANCE,
    )
    parser.add_argument(
        "--adx-period",
        type=positive_int,
        default=DEFAULT_ADX_PERIOD,
    )
    parser.add_argument(
        "--adx-threshold",
        type=non_negative_float,
        default=DEFAULT_ADX_THRESHOLD,
    )
    parser.add_argument(
        "--atr-period",
        type=positive_int,
        default=DEFAULT_ATR_PERIOD,
    )
    parser.add_argument(
        "--low-volatility-threshold",
        type=non_negative_float,
        default=DEFAULT_LOW_VOLATILITY_THRESHOLD,
    )
    parser.add_argument(
        "--high-volatility-threshold",
        type=non_negative_float,
        default=DEFAULT_HIGH_VOLATILITY_THRESHOLD,
    )
    parser.add_argument(
        "--minimum-confidence",
        type=confidence,
        default=DEFAULT_MINIMUM_CONFIDENCE,
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional .json or .csv report path",
    )
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    if args.fast_ema >= args.slow_ema:
        raise ValueError("fast EMA must be lower than slow EMA")
    if args.commission >= 1:
        raise ValueError("commission must be lower than 1")
    if args.initial_balance <= 0:
        raise ValueError("initial balance must be greater than zero")
    if args.high_volatility_threshold <= 0:
        raise ValueError(
            "high volatility threshold must be greater than zero"
        )
    if (
        args.low_volatility_threshold
        >= args.high_volatility_threshold
    ):
        raise ValueError(
            "low volatility threshold must be lower than "
            "high volatility threshold"
        )
    if args.output is not None:
        suffix = args.output.suffix.lower()
        if suffix not in {".json", ".csv"}:
            raise ValueError("output path must end with .json or .csv")


def make_detector(args: argparse.Namespace) -> MarketRegimeDetector:
    return MarketRegimeDetector(
        fast_ema_period=args.fast_ema,
        slow_ema_period=args.slow_ema,
        adx_period=args.adx_period,
        adx_threshold=args.adx_threshold,
        atr_period=args.atr_period,
        low_volatility_threshold=(
            args.low_volatility_threshold
        ),
        high_volatility_threshold=(
            args.high_volatility_threshold
        ),
    )


def run_variant(
    data: pd.DataFrame,
    *,
    period: str,
    variant: str,
    args: argparse.Namespace,
    regime_detector: CachingRegimeDetector | None = None,
) -> ComparisonResult:
    comparison, _ = _execute_variant(
        data,
        period=period,
        variant=variant,
        args=args,
        regime_detector=regime_detector,
    )
    return comparison


def _execute_variant(
    data: pd.DataFrame,
    *,
    period: str,
    variant: str,
    args: argparse.Namespace,
    regime_detector: CachingRegimeDetector | None = None,
) -> tuple[ComparisonResult, BacktestResult]:
    if variant not in {"baseline", "detector_only", "filtered"}:
        raise ValueError(f"unknown comparison variant: {variant}")

    candles = dataframe_to_candles(data)
    base_strategy = EMACrossStrategy(
        short_period=args.fast_ema,
        long_period=args.slow_ema,
    )
    wrapped: RegimeFilteredStrategy | None = None

    if variant != "baseline":
        wrapped = RegimeFilteredStrategy(
            base_strategy=base_strategy,
            regime_detector=(
                regime_detector
                if regime_detector is not None
                else make_detector(args)
            ),
            trading_filter=TradingFilter(
                minimum_confidence=args.minimum_confidence,
            ),
            apply_filter=(variant == "filtered"),
        )
        strategy = wrapped
    else:
        strategy = base_strategy

    engine = BacktestEngine(
        initial_balance=args.initial_balance,
        commission_rate=args.commission,
    )
    result = engine.run(candles=candles, strategy=strategy)

    if wrapped is None:
        allowed_entries = len(result.trades)
        blocked_entries = 0
        reasons = {
            reason.value: 0 for reason in EntryBlockReason
        }
    else:
        statistics = wrapped.statistics
        allowed_entries = statistics.allowed_entries
        blocked_entries = statistics.blocked_entries
        reasons = statistics.blocked_by_reason

    return (
        build_result(
            period=period,
            variant=variant,
            result=result,
            allowed_entries=allowed_entries,
            blocked_entries=blocked_entries,
            reasons=reasons,
        ),
        result,
    )


def build_result(
    *,
    period: str,
    variant: str,
    result: BacktestResult,
    allowed_entries: int,
    blocked_entries: int,
    reasons: dict[str, int],
) -> ComparisonResult:
    total_fees = sum(
        trade.entry_fee + trade.exit_fee
        for trade in result.trades
    )
    return ComparisonResult(
        period=period,
        variant=variant,
        final_balance=result.final_balance,
        return_percent=result.total_return_percent,
        trades=len(result.trades),
        win_rate_percent=result.win_rate_percent,
        profit_factor=result.profit_factor,
        maximum_drawdown_percent=result.max_drawdown_percent,
        total_fees=total_fees,
        allowed_entries=allowed_entries,
        blocked_entries=blocked_entries,
        blocked_range=reasons[EntryBlockReason.RANGE.value],
        blocked_downtrend=reasons[
            EntryBlockReason.DOWNTREND.value
        ],
        blocked_high_volatility=reasons[
            EntryBlockReason.HIGH_VOLATILITY.value
        ],
        blocked_low_confidence=reasons[
            EntryBlockReason.LOW_CONFIDENCE.value
        ],
        blocked_unknown_regime=reasons[
            EntryBlockReason.UNKNOWN_REGIME.value
        ],
    )


def run_comparison(
    data: pd.DataFrame,
    args: argparse.Namespace,
) -> list[ComparisonResult]:
    train = data[data["datetime"] < TEST_START].copy()
    test = data[data["datetime"] >= TEST_START].copy()
    if train.empty:
        raise ValueError("train period has no candles")
    if test.empty:
        raise ValueError("test period has no candles")

    periods = [
        ("full", data),
        ("train", train),
        ("test", test),
    ]
    results: list[ComparisonResult] = []
    for period, period_data in periods:
        regime_detector = CachingRegimeDetector(make_detector(args))
        period_runs = [
            _execute_variant(
                period_data,
                period=period,
                variant=variant,
                args=args,
                regime_detector=regime_detector,
            )
            for variant in ("baseline", "detector_only", "filtered")
        ]
        baseline_result = period_runs[0][1]
        detector_only_result = period_runs[1][1]
        if detector_only_result != baseline_result:
            raise RuntimeError(
                "detector-only changed baseline backtest results "
                f"for period {period}"
            )
        results.extend(comparison for comparison, _ in period_runs)

    return results


def sorted_results(
    results: list[ComparisonResult],
) -> list[ComparisonResult]:
    return sorted(
        results,
        key=lambda item: (
            -item.return_percent,
            item.maximum_drawdown_percent,
            -item.profit_factor,
        ),
    )


def print_results(results: list[ComparisonResult]) -> None:
    for period in ("full", "train", "test"):
        period_results = sorted_results(
            [item for item in results if item.period == period]
        )
        print()
        print(f"Period: {period}")
        print(
            f"{'Variant':<15}{'Return':>10}{'DD':>9}"
            f"{'PF':>9}{'Trades':>9}{'Win':>9}"
            f"{'Balance':>12}{'Fees':>10}"
            f"{'Allowed':>10}{'Blocked':>10}"
        )
        for item in period_results:
            print(
                f"{item.variant:<15}"
                f"{item.return_percent:>+9.2f}%"
                f"{item.maximum_drawdown_percent:>8.2f}%"
                f"{item.profit_factor:>9.2f}"
                f"{item.trades:>9}"
                f"{item.win_rate_percent:>8.2f}%"
                f"{item.final_balance:>12.2f}"
                f"{item.total_fees:>10.2f}"
                f"{item.allowed_entries:>10}"
                f"{item.blocked_entries:>10}"
            )
            if item.blocked_entries:
                print(
                    "  blocked: "
                    f"range={item.blocked_range}, "
                    f"downtrend={item.blocked_downtrend}, "
                    f"high_volatility="
                    f"{item.blocked_high_volatility}, "
                    f"low_confidence="
                    f"{item.blocked_low_confidence}, "
                    f"unknown={item.blocked_unknown_regime}"
                )


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
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def save_report(
    path: Path,
    results: list[ComparisonResult],
    args: argparse.Namespace,
) -> None:
    rows = [asdict(item) for item in results]
    if path.suffix.lower() == ".json":
        content = json.dumps(
            {
                "parameters": {
                    "data": str(args.data),
                    "fast_ema": args.fast_ema,
                    "slow_ema": args.slow_ema,
                    "commission": args.commission,
                    "initial_balance": args.initial_balance,
                    "adx_period": args.adx_period,
                    "adx_threshold": args.adx_threshold,
                    "atr_period": args.atr_period,
                    "low_volatility_threshold": (
                        args.low_volatility_threshold
                    ),
                    "high_volatility_threshold": (
                        args.high_volatility_threshold
                    ),
                    "minimum_confidence": args.minimum_confidence,
                    "test_start": str(TEST_START),
                },
                "results": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        atomic_write(path, content + "\n")
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, output.getvalue())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_arguments(args)
        data = load_market_data(args.data)
        data = data.iloc[:-1].copy()
        results = run_comparison(data, args)
        print_results(results)
        if args.output is not None:
            save_report(args.output, results, args)
            print(f"\nReport: {args.output}")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
