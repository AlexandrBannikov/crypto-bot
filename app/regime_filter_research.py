from __future__ import annotations

import hashlib
import os
import statistics
import struct
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol

import pandas as pd

from app.candle import Candle
from app.candle_mapper import dataframe_to_candles
from app.ema_cross_strategy import EMACrossStrategy
from app.engine import BacktestEngine, BacktestResult
from app.market_regime import MarketRegime, MarketRegimeDetector
from app.regime_filtered_strategy import (
    EntryBlockReason,
    RegimeFilteredStrategy,
    StrategySignal,
)
from app.strategies import Signal
from app.trading_filter import TradingFilter


VARIANTS = ("baseline", "detector_only", "filtered")
MINIMUM_VERDICT_WINDOWS = 5
VERDICT_CRITERIA = {
    "minimum_windows": MINIMUM_VERDICT_WINDOWS,
    "return_better_fraction": 0.60,
    "drawdown_better_fraction": 0.60,
    "return_and_drawdown_better_fraction": 0.40,
    "maximum_worst_return_deficit_points": 5.0,
    "minimum_filtered_median_profit_factor_ratio": 1.0,
    "minimum_filtered_trades_per_window": 3.0,
}


class SignalStrategy(Protocol):
    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> StrategySignal:
        ...


@dataclass(frozen=True, slots=True)
class ResearchConfig:
    fast_ema: int = 20
    slow_ema: int = 50
    fee_rate: float = 0.001
    initial_balance: float = 1000.0
    train_months: int = 18
    test_months: int = 6
    step_months: int = 6
    adx_period: int = 14
    adx_threshold: float = 20.0
    atr_period: int = 14
    low_volatility_threshold: float = 0.005
    high_volatility_threshold: float = 0.02
    minimum_confidence: float = 0.0
    max_windows: int | None = None

    def validate(self) -> None:
        if self.fast_ema <= 0 or self.slow_ema <= 0:
            raise ValueError("EMA periods must be greater than zero")
        if self.fast_ema >= self.slow_ema:
            raise ValueError("fast EMA must be lower than slow EMA")
        if not 0 <= self.fee_rate < 1:
            raise ValueError("fee rate must be between 0 and 1")
        if self.initial_balance <= 0:
            raise ValueError("initial balance must be greater than zero")
        for name in ("train_months", "test_months", "step_months"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if self.max_windows is not None and self.max_windows <= 0:
            raise ValueError("max_windows must be greater than zero")
        make_detector(self)


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    number: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


@dataclass(frozen=True, slots=True)
class WindowResult:
    window_number: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_candles: int
    test_candles: int
    variant: str
    initial_balance: float
    final_balance: float
    return_percent: float
    maximum_drawdown_percent: float
    profit_factor: float
    win_rate_percent: float
    trade_count: int
    winning_trades: int
    losing_trades: int
    total_fees: float
    gross_profit: float
    gross_loss: float
    allowed_entries: int
    blocked_entries: int
    blocked_range: int
    blocked_downtrend: int
    blocked_high_volatility: int
    blocked_low_confidence: int
    blocked_unknown: int


class WarmupStrategy:
    """Warm strategy state while suppressing all pre-test trading."""

    def __init__(
        self,
        strategy: SignalStrategy,
        trade_start_index: int,
    ) -> None:
        self.strategy = strategy
        self.trade_start_index = trade_start_index

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> StrategySignal:
        signal = self.strategy.generate_signal(candles, index)
        if index < self.trade_start_index:
            return Signal.HOLD
        return signal


class CausalRegimeCache:
    """Index cache scoped to one immutable candle sequence."""

    def __init__(
        self,
        detector: MarketRegimeDetector,
        *,
        window_id: str = "standalone",
    ) -> None:
        self.detector = detector
        self.window_id = window_id
        self._source: Sequence[Candle] | None = None
        self._cache: dict[int, MarketRegime] = {}

    def detect(self, candles: Sequence[Candle]) -> MarketRegime:
        # Prefix provenance cannot be established cheaply here.
        return self.detector.detect(candles)

    def detect_at(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> MarketRegime:
        if candles is not self._source:
            self._source = candles
            self._cache = {}
        if index not in self._cache:
            self._cache[index] = self.detector.detect(
                candles[: index + 1]
            )
        return self._cache[index]


def fingerprint_candles(candles: Sequence[Candle]) -> str:
    digest = hashlib.sha256()
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
    return digest.hexdigest()


def make_detector(config: ResearchConfig) -> MarketRegimeDetector:
    return MarketRegimeDetector(
        fast_ema_period=config.fast_ema,
        slow_ema_period=config.slow_ema,
        adx_period=config.adx_period,
        adx_threshold=config.adx_threshold,
        atr_period=config.atr_period,
        low_volatility_threshold=config.low_volatility_threshold,
        high_volatility_threshold=config.high_volatility_threshold,
    )


def build_windows(
    data: pd.DataFrame,
    config: ResearchConfig,
) -> list[WalkForwardWindow]:
    config.validate()
    if data.empty:
        raise ValueError("market data is empty")
    first = pd.Timestamp(data["datetime"].min())
    last = pd.Timestamp(data["datetime"].max())
    ordered_datetimes = data["datetime"].sort_values()
    if len(ordered_datetimes) > 1:
        final_interval = (
            ordered_datetimes.iloc[-1] - ordered_datetimes.iloc[-2]
        )
    else:
        final_interval = pd.Timedelta(0)
    coverage_end = last + final_interval
    windows: list[WalkForwardWindow] = []
    train_start = first
    while True:
        train_end = train_start + pd.DateOffset(
            months=config.train_months
        )
        test_start = train_end
        test_end = test_start + pd.DateOffset(
            months=config.test_months
        )
        if test_end > coverage_end:
            break
        windows.append(
            WalkForwardWindow(
                number=len(windows) + 1,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        if (
            config.max_windows is not None
            and len(windows) >= config.max_windows
        ):
            break
        train_start += pd.DateOffset(months=config.step_months)
    if not windows:
        raise ValueError("not enough data for one complete walk-forward window")
    return windows


def _run_variant(
    history: list[Candle],
    *,
    trade_start_index: int,
    window: WalkForwardWindow,
    variant: str,
    config: ResearchConfig,
    cache: CausalRegimeCache,
    train_candles: int | None = None,
    test_candles: int | None = None,
) -> tuple[WindowResult, BacktestResult]:
    base = WarmupStrategy(
        EMACrossStrategy(config.fast_ema, config.slow_ema),
        trade_start_index,
    )
    wrapped: RegimeFilteredStrategy | None = None
    strategy: SignalStrategy = base
    if variant != "baseline":
        wrapped = RegimeFilteredStrategy(
            base,
            cache,
            TradingFilter(config.minimum_confidence),
            apply_filter=(variant == "filtered"),
        )
        strategy = wrapped
    result = BacktestEngine(
        initial_balance=config.initial_balance,
        commission_rate=config.fee_rate,
    ).run(history, strategy)
    reasons = {
        reason.value: 0 for reason in EntryBlockReason
    }
    allowed_entries = len(result.trades)
    blocked_entries = 0
    if wrapped is not None:
        stats = wrapped.statistics
        allowed_entries = stats.allowed_entries
        blocked_entries = stats.blocked_entries
        reasons = stats.blocked_by_reason
    if sum(reasons.values()) != blocked_entries:
        raise RuntimeError("blocked reason counts do not match blocked entries")
    if variant == "detector_only" and blocked_entries:
        raise RuntimeError("detector-only blocked an entry")
    total_fees = sum(
        trade.entry_fee + trade.exit_fee for trade in result.trades
    )
    item = WindowResult(
        window_number=window.number,
        train_start=window.train_start.isoformat(),
        train_end=window.train_end.isoformat(),
        test_start=window.test_start.isoformat(),
        test_end=window.test_end.isoformat(),
        train_candles=(
            trade_start_index
            if train_candles is None
            else train_candles
        ),
        test_candles=(
            len(history) - trade_start_index
            if test_candles is None
            else test_candles
        ),
        variant=variant,
        initial_balance=result.initial_balance,
        final_balance=result.final_balance,
        return_percent=result.total_return_percent,
        maximum_drawdown_percent=result.max_drawdown_percent,
        profit_factor=result.profit_factor,
        win_rate_percent=result.win_rate_percent,
        trade_count=len(result.trades),
        winning_trades=result.winning_trades,
        losing_trades=result.losing_trades,
        total_fees=total_fees,
        gross_profit=result.gross_profit,
        gross_loss=result.gross_loss,
        allowed_entries=allowed_entries,
        blocked_entries=blocked_entries,
        blocked_range=reasons[EntryBlockReason.RANGE.value],
        blocked_downtrend=reasons[EntryBlockReason.DOWNTREND.value],
        blocked_high_volatility=reasons[
            EntryBlockReason.HIGH_VOLATILITY.value
        ],
        blocked_low_confidence=reasons[
            EntryBlockReason.LOW_CONFIDENCE.value
        ],
        blocked_unknown=reasons[
            EntryBlockReason.UNKNOWN_REGIME.value
        ],
    )
    return item, result


def run_walk_forward(
    data: pd.DataFrame,
    config: ResearchConfig,
) -> list[WindowResult]:
    windows = build_windows(data, config)
    output: list[WindowResult] = []
    for window in windows:
        train = data[
            (data["datetime"] >= window.train_start)
            & (data["datetime"] < window.train_end)
        ]
        test = data[
            (data["datetime"] >= window.test_start)
            & (data["datetime"] < window.test_end)
        ]
        if train.empty or test.empty:
            raise ValueError(f"window {window.number} has an empty interval")
        history = dataframe_to_candles(pd.concat([train, test]))
        cache = CausalRegimeCache(
            make_detector(config),
            window_id=(
                f"{window.number}:{window.train_start.isoformat()}:"
                f"{window.test_end.isoformat()}"
            ),
        )
        runs = [
            _run_variant(
                history,
                trade_start_index=len(train),
                window=window,
                variant=variant,
                config=config,
                cache=cache,
                train_candles=len(train),
                test_candles=len(test),
            )
            for variant in VARIANTS
        ]
        if runs[0][1] != runs[1][1]:
            raise RuntimeError(
                "detector-only BacktestResult differs from baseline "
                f"in window {window.number}"
            )
        baseline, detector_only, filtered = (
            item for item, _ in runs
        )
        potential_entries = detector_only.allowed_entries
        if baseline.allowed_entries != potential_entries:
            baseline = replace(
                baseline,
                allowed_entries=potential_entries,
            )
            runs[0] = (baseline, runs[0][1])
        if baseline.blocked_entries or detector_only.blocked_entries:
            raise RuntimeError("unfiltered variant blocked an entry")
        if (
            filtered.allowed_entries + filtered.blocked_entries
            != potential_entries
        ):
            raise RuntimeError(
                "filtered entry accounting differs from baseline"
            )
        test_start_timestamp = int(window.test_start.timestamp())
        if any(
            trade.entry_timestamp < test_start_timestamp
            for _, result in runs
            for trade in result.trades
        ):
            raise RuntimeError("pre-test trade leaked into test statistics")
        output.extend(item for item, _ in runs)
    return output


def summarize(
    results: list[WindowResult],
    variant: str,
) -> dict[str, float | int]:
    items = [item for item in results if item.variant == variant]
    returns = [item.return_percent for item in items]
    drawdowns = [item.maximum_drawdown_percent for item in items]
    # BacktestEngine defines PF as 0 with no trades and +inf when there
    # are profits but no losing trades.  fmean intentionally propagates
    # +inf; JSON serialization represents non-finite diagnostics as null.
    factors = [item.profit_factor for item in items]
    trades = [item.trade_count for item in items]
    fees = [item.total_fees for item in items]
    count = len(items)
    blocked_reasons = {
        "range": sum(item.blocked_range for item in items),
        "downtrend": sum(item.blocked_downtrend for item in items),
        "high_volatility": sum(
            item.blocked_high_volatility for item in items
        ),
        "low_confidence": sum(
            item.blocked_low_confidence for item in items
        ),
        "unknown": sum(item.blocked_unknown for item in items),
    }
    total_blocked = sum(item.blocked_entries for item in items)
    if sum(blocked_reasons.values()) != total_blocked:
        raise RuntimeError("aggregate blocked reasons do not match total")
    return {
        "windows": count,
        "profitable_windows": sum(value > 0 for value in returns),
        "losing_windows": sum(value < 0 for value in returns),
        "profitable_fraction": sum(value > 0 for value in returns) / count,
        "mean_return_percent": statistics.fmean(returns),
        "median_return_percent": statistics.median(returns),
        "worst_return_percent": min(returns),
        "best_return_percent": max(returns),
        "return_standard_deviation": (
            statistics.pstdev(returns) if count > 1 else 0.0
        ),
        "mean_maximum_drawdown_percent": statistics.fmean(drawdowns),
        "median_maximum_drawdown_percent": statistics.median(drawdowns),
        "worst_maximum_drawdown_percent": max(drawdowns),
        "mean_profit_factor": statistics.fmean(factors),
        "median_profit_factor": statistics.median(factors),
        "total_trades": sum(trades),
        "mean_trades_per_window": statistics.fmean(trades),
        "total_fees": sum(fees),
        "mean_fees_per_window": statistics.fmean(fees),
        "total_blocked_entries": total_blocked,
        "blocked_by_reason": blocked_reasons,
    }


def compare_variants(
    results: list[WindowResult],
) -> dict[str, int | float]:
    pairs = []
    for number in sorted({item.window_number for item in results}):
        items = {
            item.variant: item
            for item in results
            if item.window_number == number
        }
        pairs.append((items["baseline"], items["filtered"]))
    return {
        "filtered_better_return": sum(
            filtered.return_percent > baseline.return_percent
            for baseline, filtered in pairs
        ),
        "filtered_worse_return": sum(
            filtered.return_percent < baseline.return_percent
            for baseline, filtered in pairs
        ),
        "filtered_equal_return": sum(
            filtered.return_percent == baseline.return_percent
            for baseline, filtered in pairs
        ),
        "filtered_lower_drawdown": sum(
            filtered.maximum_drawdown_percent
            < baseline.maximum_drawdown_percent
            for baseline, filtered in pairs
        ),
        "filtered_better_profit_factor": sum(
            filtered.profit_factor > baseline.profit_factor
            for baseline, filtered in pairs
        ),
        "filtered_better_return_and_drawdown": sum(
            filtered.return_percent > baseline.return_percent
            and filtered.maximum_drawdown_percent
            < baseline.maximum_drawdown_percent
            for baseline, filtered in pairs
        ),
        "filtered_profit_when_baseline_loses": sum(
            filtered.return_percent > 0 > baseline.return_percent
            for baseline, filtered in pairs
        ),
        "filtered_loss_when_baseline_profits": sum(
            filtered.return_percent < 0 < baseline.return_percent
            for baseline, filtered in pairs
        ),
    }


def compounded_diagnostics(
    results: list[WindowResult],
    initial_balance: float,
) -> dict[str, float]:
    output: dict[str, float] = {}
    for variant in ("baseline", "filtered"):
        balance = initial_balance
        for item in results:
            if item.variant == variant:
                balance *= 1 + item.return_percent / 100
        output[f"{variant}_compounded_final_balance"] = balance
        output[f"{variant}_compounded_return_percent"] = (
            balance / initial_balance - 1
        ) * 100
    return output


def research_verdict(
    baseline: dict[str, float | int],
    filtered: dict[str, float | int],
    comparison: dict[str, int],
) -> str:
    count = int(baseline["windows"])
    if count < MINIMUM_VERDICT_WINDOWS:
        return "INCONCLUSIVE"
    promising = (
        comparison["filtered_better_return"] / count
        >= VERDICT_CRITERIA["return_better_fraction"]
        and comparison["filtered_lower_drawdown"] / count
        >= VERDICT_CRITERIA["drawdown_better_fraction"]
        and comparison["filtered_better_return_and_drawdown"] / count
        >= VERDICT_CRITERIA["return_and_drawdown_better_fraction"]
        and float(filtered["worst_return_percent"])
        >= float(baseline["worst_return_percent"])
        - VERDICT_CRITERIA["maximum_worst_return_deficit_points"]
        and float(filtered["median_profit_factor"])
        >= float(baseline["median_profit_factor"])
        * VERDICT_CRITERIA[
            "minimum_filtered_median_profit_factor_ratio"
        ]
        and float(filtered["mean_trades_per_window"])
        >= VERDICT_CRITERIA["minimum_filtered_trades_per_window"]
    )
    if promising:
        return "PROMISING"
    return "REJECTED"


def build_analysis(
    results: list[WindowResult],
    initial_balance: float,
) -> dict[str, object]:
    baseline = summarize(results, "baseline")
    filtered = summarize(results, "filtered")
    comparison = compare_variants(results)
    compounded = compounded_diagnostics(results, initial_balance)
    baseline["compounded_return_percent"] = compounded[
        "baseline_compounded_return_percent"
    ]
    filtered["compounded_return_percent"] = compounded[
        "filtered_compounded_return_percent"
    ]
    comparison["compounded_return_difference_points"] = (
        compounded["filtered_compounded_return_percent"]
        - compounded["baseline_compounded_return_percent"]
    )
    comparison["mean_drawdown_difference_points"] = (
        filtered["mean_maximum_drawdown_percent"]
        - baseline["mean_maximum_drawdown_percent"]
    )
    return {
        "summary": {
            "baseline": baseline,
            "filtered": filtered,
        },
        "comparison": comparison,
        "compounded_diagnostics": compounded,
        "verdict_criteria": VERDICT_CRITERIA,
        "verdict": research_verdict(
            baseline, filtered, comparison
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


def config_dict(config: ResearchConfig) -> dict[str, object]:
    return asdict(config)
