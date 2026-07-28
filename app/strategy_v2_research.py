from __future__ import annotations

import hashlib
import statistics
import struct
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pandas as pd

from app.candle import Candle
from app.candle_mapper import dataframe_to_candles
from app.ema_cross_strategy import EMACrossStrategy
from app.engine import BacktestEngine, BacktestResult
from app.regime_filter_research import atomic_write
from app.strategies import Signal
from app.strategy_v2_filters import (
    ADXFilterConfig,
    ADXStrengthFilter,
    ATRFilterConfig,
    ATRVolatilityFilter,
    AllEntryFilters,
    EntryFilterReason,
    PullbackEntryFilter,
    PullbackFilterConfig,
    PullbackTouchMode,
    ResearchEntryFilteredStrategy,
)


VARIANTS = ("baseline", "atr", "adx", "atr_adx")
PULLBACK_VARIANTS = (
    "baseline",
    "atr",
    "adx",
    "atr_adx",
    "pullback",
    "atr_pullback",
    "adx_pullback",
    "atr_adx_pullback",
)


@dataclass(frozen=True, slots=True)
class StrategyV2Config:
    fast_ema: int = 20
    slow_ema: int = 50
    fee_rate: float = 0.001
    initial_balance: float = 1000.0
    train_end: str = "2025-01-01"
    train_months: int = 18
    test_months: int = 6
    step_months: int = 6
    atr: ATRFilterConfig = ATRFilterConfig(
        enabled=True,
        period=14,
        minimum_relative_atr=0.005,
        maximum_relative_atr=0.020,
    )
    adx: ADXFilterConfig = ADXFilterConfig(
        enabled=True,
        period=14,
        minimum_adx=20.0,
    )
    pullback: PullbackFilterConfig = PullbackFilterConfig(
        enabled=True,
        max_wait_bars=5,
        touch_mode=PullbackTouchMode.LOW_TOUCH,
    )

    def __post_init__(self) -> None:
        if self.fast_ema <= 0 or self.slow_ema <= 0:
            raise ValueError("EMA periods must be greater than zero")
        if self.fast_ema >= self.slow_ema:
            raise ValueError("fast EMA must be lower than slow EMA")
        if not 0 <= self.fee_rate < 1:
            raise ValueError("fee rate must be between zero and one")
        if self.initial_balance <= 0:
            raise ValueError("initial balance must be positive")
        for name in ("train_months", "test_months", "step_months"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        pd.Timestamp(self.train_end)


@dataclass(frozen=True, slots=True)
class PeriodResult:
    period: str
    variant: str
    start: str
    end: str
    candles: int
    initial_balance: float
    final_balance: float
    total_return_percent: float
    annualized_return_percent: float
    maximum_drawdown_percent: float
    profit_factor: float
    win_rate_percent: float
    trades: int
    average_trade: float
    exposure_percent: float
    total_fees: float
    blocked_by_atr: int
    blocked_by_adx: int
    insufficient_history: int
    invalid_indicator_value: int


@dataclass(frozen=True, slots=True)
class PullbackPeriodResult:
    period: str
    variant: str
    start: str
    end: str
    candles: int
    initial_balance: float
    final_balance: float
    total_return_percent: float
    annualized_return_percent: float
    maximum_drawdown_percent: float
    profit_factor: float
    win_rate_percent: float
    trades: int
    average_trade: float
    exposure_percent: float
    total_fees: float
    blocked_entries: int
    blocked_by_atr: int
    blocked_by_adx: int
    waiting_entries: int
    pullback_confirmed: int
    timed_out_entries: int
    cancelled_entries: int
    pullback_rate_percent: float
    average_wait_bars: float
    average_entry_price_improvement_percent: float


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    number: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


class WarmupStrategy:
    def __init__(self, strategy, trade_start_index: int) -> None:
        self.strategy = strategy
        self.trade_start_index = trade_start_index

    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ):
        signal = self.strategy.generate_signal(candles, index)
        if index < self.trade_start_index:
            return Signal.HOLD
        return signal


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


def _variant_configs(
    variant: str,
    config: StrategyV2Config,
) -> tuple[ATRFilterConfig, ADXFilterConfig]:
    if variant not in VARIANTS:
        raise ValueError(f"unknown Strategy v2 variant: {variant}")
    atr_config = ATRFilterConfig(
        enabled=variant in {"atr", "atr_adx"},
        period=config.atr.period,
        minimum_relative_atr=config.atr.minimum_relative_atr,
        maximum_relative_atr=config.atr.maximum_relative_atr,
    )
    adx_config = ADXFilterConfig(
        enabled=variant in {"adx", "atr_adx"},
        period=config.adx.period,
        minimum_adx=config.adx.minimum_adx,
    )
    return atr_config, adx_config


def _pullback_variant_configs(
    variant: str,
    config: StrategyV2Config,
) -> tuple[ATRFilterConfig, ADXFilterConfig, PullbackFilterConfig]:
    if variant not in PULLBACK_VARIANTS:
        raise ValueError(f"unknown pullback variant: {variant}")
    parts = frozenset(variant.split("_"))
    atr_config = ATRFilterConfig(
        enabled="atr" in parts,
        period=config.atr.period,
        minimum_relative_atr=config.atr.minimum_relative_atr,
        maximum_relative_atr=config.atr.maximum_relative_atr,
    )
    adx_config = ADXFilterConfig(
        enabled="adx" in parts,
        period=config.adx.period,
        minimum_adx=config.adx.minimum_adx,
    )
    pullback_config = PullbackFilterConfig(
        enabled="pullback" in parts,
        max_wait_bars=config.pullback.max_wait_bars,
        touch_mode=config.pullback.touch_mode,
    )
    return atr_config, adx_config, pullback_config


def build_strategy(
    variant: str,
    config: StrategyV2Config,
    *,
    trade_start_index: int,
) -> ResearchEntryFilteredStrategy:
    base = WarmupStrategy(
        EMACrossStrategy(config.fast_ema, config.slow_ema),
        trade_start_index,
    )
    atr_config, adx_config = _variant_configs(variant, config)
    return ResearchEntryFilteredStrategy(
        base,
        AllEntryFilters(
            (
                ATRVolatilityFilter(atr_config),
                ADXStrengthFilter(adx_config),
            )
        ),
    )


def build_pullback_strategy(
    variant: str,
    config: StrategyV2Config,
    *,
    trade_start_index: int,
) -> ResearchEntryFilteredStrategy:
    base = WarmupStrategy(
        EMACrossStrategy(config.fast_ema, config.slow_ema),
        trade_start_index,
    )
    atr_config, adx_config, pullback_config = (
        _pullback_variant_configs(variant, config)
    )
    return ResearchEntryFilteredStrategy(
        base,
        AllEntryFilters(
            (
                ATRVolatilityFilter(atr_config),
                ADXStrengthFilter(adx_config),
                PullbackEntryFilter(
                    pullback_config,
                    fast_ema_period=config.fast_ema,
                    slow_ema_period=config.slow_ema,
                ),
            )
        ),
    )
def _metrics(
    *,
    period: str,
    variant: str,
    candles: list[Candle],
    trade_start_index: int,
    result: BacktestResult,
    strategy: ResearchEntryFilteredStrategy,
) -> PeriodResult:
    start_timestamp = candles[trade_start_index].timestamp
    end_timestamp = candles[-1].timestamp
    seconds = max(1, end_timestamp - start_timestamp)
    years = seconds / (365.2425 * 24 * 60 * 60)
    annualized = (
        (
            result.final_balance / result.initial_balance
        ) ** (1 / years)
        - 1
    ) * 100
    profits = [trade.profit for trade in result.trades]
    average_trade = (
        sum(profits) / len(profits) if profits else 0.0
    )
    held_seconds = sum(
        max(
            0,
            trade.exit_timestamp
            - max(trade.entry_timestamp, start_timestamp),
        )
        for trade in result.trades
    )
    counts = strategy.reason_counts
    return PeriodResult(
        period=period,
        variant=variant,
        start=datetime.fromtimestamp(
            start_timestamp, timezone.utc
        ).isoformat(),
        end=datetime.fromtimestamp(
            end_timestamp, timezone.utc
        ).isoformat(),
        candles=len(candles) - trade_start_index,
        initial_balance=result.initial_balance,
        final_balance=result.final_balance,
        total_return_percent=result.total_return_percent,
        annualized_return_percent=annualized,
        maximum_drawdown_percent=result.max_drawdown_percent,
        profit_factor=result.profit_factor,
        win_rate_percent=result.win_rate_percent,
        trades=len(result.trades),
        average_trade=average_trade,
        exposure_percent=held_seconds / seconds * 100,
        total_fees=sum(
            trade.entry_fee + trade.exit_fee
            for trade in result.trades
        ),
        blocked_by_atr=counts["blocked_by_atr"],
        blocked_by_adx=counts["blocked_by_adx"],
        insufficient_history=counts["insufficient_history"],
        invalid_indicator_value=counts["invalid_indicator_value"],
    )


def run_period(
    data: pd.DataFrame,
    *,
    period: str,
    variant: str,
    config: StrategyV2Config,
    trade_start_index: int = 0,
) -> tuple[PeriodResult, BacktestResult]:
    candles = dataframe_to_candles(data)
    strategy = build_strategy(
        variant, config, trade_start_index=trade_start_index
    )
    result = BacktestEngine(
        initial_balance=config.initial_balance,
        commission_rate=config.fee_rate,
    ).run(candles, strategy)
    return (
        _metrics(
            period=period,
            variant=variant,
            candles=candles,
            trade_start_index=trade_start_index,
            result=result,
            strategy=strategy,
        ),
        result,
    )


def _pullback_metrics(
    *,
    period: str,
    variant: str,
    candles: list[Candle],
    trade_start_index: int,
    result: BacktestResult,
    strategy: ResearchEntryFilteredStrategy,
) -> PullbackPeriodResult:
    common = _metrics(
        period=period,
        variant=variant,
        candles=candles,
        trade_start_index=trade_start_index,
        result=result,
        strategy=strategy,
    )
    events = strategy.pullback.events if strategy.pullback else []
    confirmed = [
        event
        for event in events
        if event.reason is EntryFilterReason.PULLBACK_CONFIRMED
    ]
    resolved_waits = [
        event.wait_bars
        for event in confirmed
        if event.wait_bars is not None
    ]
    entry_prices = {
        trade.entry_timestamp: trade.entry_price
        for trade in result.trades
    }
    improvements: list[float] = []
    for event in confirmed:
        if not event.entry_allowed or event.resolution_index is None:
            continue
        entry_index = event.resolution_index + 1
        if entry_index >= len(candles):
            continue
        entry_price = entry_prices.get(candles[entry_index].timestamp)
        if entry_price is not None and event.cross_price > 0:
            improvements.append(
                (event.cross_price - entry_price)
                / event.cross_price
                * 100
            )
    counts = strategy.reason_counts
    return PullbackPeriodResult(
        **{
            key: getattr(common, key)
            for key in (
                "period",
                "variant",
                "start",
                "end",
                "candles",
                "initial_balance",
                "final_balance",
                "total_return_percent",
                "annualized_return_percent",
                "maximum_drawdown_percent",
                "profit_factor",
                "win_rate_percent",
                "trades",
                "average_trade",
                "exposure_percent",
                "total_fees",
                "blocked_by_atr",
                "blocked_by_adx",
            )
        },
        blocked_entries=strategy.blocked_entries,
        waiting_entries=len(events),
        pullback_confirmed=len(confirmed),
        timed_out_entries=sum(
            event.reason is EntryFilterReason.PULLBACK_TIMEOUT
            for event in events
        ),
        cancelled_entries=sum(
            event.reason is EntryFilterReason.PULLBACK_CANCELLED
            for event in events
        ),
        pullback_rate_percent=(
            len(confirmed) / len(events) * 100 if events else 0.0
        ),
        average_wait_bars=(
            statistics.fmean(resolved_waits)
            if resolved_waits
            else 0.0
        ),
        average_entry_price_improvement_percent=(
            statistics.fmean(improvements) if improvements else 0.0
        ),
    )


def run_pullback_period(
    data: pd.DataFrame,
    *,
    period: str,
    variant: str,
    config: StrategyV2Config,
    trade_start_index: int = 0,
) -> tuple[PullbackPeriodResult, BacktestResult]:
    candles = dataframe_to_candles(data)
    strategy = build_pullback_strategy(
        variant, config, trade_start_index=trade_start_index
    )
    result = BacktestEngine(
        initial_balance=config.initial_balance,
        commission_rate=config.fee_rate,
    ).run(candles, strategy)
    strategy.finish(len(candles) - 1)
    return (
        _pullback_metrics(
            period=period,
            variant=variant,
            candles=candles,
            trade_start_index=trade_start_index,
            result=result,
            strategy=strategy,
        ),
        result,
    )


def run_pullback_comparison(
    data: pd.DataFrame,
    config: StrategyV2Config,
) -> list[PullbackPeriodResult]:
    boundary = pd.Timestamp(config.train_end)
    datetimes = pd.DatetimeIndex(data["datetime"])
    if datetimes.tz is not None:
        boundary = boundary.tz_localize("UTC").tz_convert(datetimes.tz)
    train = data[data["datetime"] < boundary].copy()
    if train.empty or len(train) == len(data):
        raise ValueError("train/OOS split must contain both periods")
    periods = (
        ("full", data, 0),
        ("train", train, 0),
        ("oos", data, len(train)),
    )
    rows: list[PullbackPeriodResult] = []
    for period, frame, trade_start_index in periods:
        for variant in PULLBACK_VARIANTS:
            row, _ = run_pullback_period(
                frame,
                period=period,
                variant=variant,
                config=config,
                trade_start_index=trade_start_index,
            )
            rows.append(row)
    return rows


def run_comparison(
    data: pd.DataFrame,
    config: StrategyV2Config,
) -> list[PeriodResult]:
    boundary = pd.Timestamp(config.train_end)
    datetimes = pd.DatetimeIndex(data["datetime"])
    if datetimes.tz is not None:
        boundary = boundary.tz_localize("UTC").tz_convert(datetimes.tz)
    train = data[data["datetime"] < boundary].copy()
    if train.empty or len(train) == len(data):
        raise ValueError("train/OOS split must contain both periods")
    periods = (
        ("full", data, 0),
        ("train", train, 0),
        ("oos", data, len(train)),
    )
    rows: list[PeriodResult] = []
    for period, frame, trade_start_index in periods:
        for variant in VARIANTS:
            row, result = run_period(
                frame,
                period=period,
                variant=variant,
                config=config,
                trade_start_index=trade_start_index,
            )
            rows.append(row)
            if variant == "baseline":
                repeated = run_period(
                    frame,
                    period=period,
                    variant=variant,
                    config=config,
                    trade_start_index=trade_start_index,
                )[1]
                if repeated != result:
                    raise RuntimeError(
                        f"baseline is not reproducible for {period}"
                    )
    return rows


def build_windows(
    data: pd.DataFrame,
    config: StrategyV2Config,
) -> list[WalkForwardWindow]:
    first = pd.Timestamp(data["datetime"].min())
    ordered = data["datetime"].sort_values()
    interval = ordered.iloc[-1] - ordered.iloc[-2]
    coverage_end = pd.Timestamp(ordered.iloc[-1]) + interval
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
                len(windows) + 1,
                train_start,
                train_end,
                test_start,
                test_end,
            )
        )
        train_start += pd.DateOffset(months=config.step_months)
    if not windows:
        raise ValueError("not enough data for walk-forward")
    return windows


def run_walk_forward(
    data: pd.DataFrame,
    config: StrategyV2Config,
) -> list[PeriodResult]:
    rows: list[PeriodResult] = []
    for window in build_windows(data, config):
        history = data[
            (data["datetime"] >= window.train_start)
            & (data["datetime"] < window.test_end)
        ].copy()
        trade_start_index = int(
            (history["datetime"] < window.test_start).sum()
        )
        for variant in VARIANTS:
            row, _ = run_period(
                history,
                period=f"wf_{window.number}",
                variant=variant,
                config=config,
                trade_start_index=trade_start_index,
            )
            rows.append(row)
    return rows


def run_pullback_walk_forward(
    data: pd.DataFrame,
    config: StrategyV2Config,
) -> list[PullbackPeriodResult]:
    rows: list[PullbackPeriodResult] = []
    for window in build_windows(data, config):
        history = data[
            (data["datetime"] >= window.train_start)
            & (data["datetime"] < window.test_end)
        ].copy()
        trade_start_index = int(
            (history["datetime"] < window.test_start).sum()
        )
        for variant in PULLBACK_VARIANTS:
            row, _ = run_pullback_period(
                history,
                period=f"wf_{window.number}",
                variant=variant,
                config=config,
                trade_start_index=trade_start_index,
            )
            rows.append(row)
    return rows


def summarize_walk_forward(
    rows: Sequence[PeriodResult],
) -> dict[str, dict[str, float | int]]:
    summary: dict[str, dict[str, float | int]] = {}
    for variant in VARIANTS:
        selected = [row for row in rows if row.variant == variant]
        returns = [row.total_return_percent for row in selected]
        drawdowns = [
            row.maximum_drawdown_percent for row in selected
        ]
        profit_factors = [row.profit_factor for row in selected]
        compounded = 1.0
        for value in returns:
            compounded *= 1 + value / 100
        summary[variant] = {
            "windows": len(selected),
            "compounded_return_percent": (compounded - 1.0) * 100,
            "mean_return_percent": statistics.fmean(returns),
            "median_return_percent": statistics.median(returns),
            "best_return_percent": max(returns),
            "worst_return_percent": min(returns),
            "mean_maximum_drawdown_percent": statistics.fmean(
                drawdowns
            ),
            "worst_maximum_drawdown_percent": max(drawdowns),
            "median_profit_factor": statistics.median(profit_factors),
            "total_trades": sum(row.trades for row in selected),
            "profitable_window_fraction": sum(
                value > 0 for value in returns
            )
            / len(returns),
            "total_fees": sum(row.total_fees for row in selected),
            "blocked_by_atr": sum(
                row.blocked_by_atr for row in selected
            ),
            "blocked_by_adx": sum(
                row.blocked_by_adx for row in selected
            ),
        }
    return summary


def summarize_pullback_walk_forward(
    rows: Sequence[PullbackPeriodResult],
) -> dict[str, dict[str, float | int]]:
    summary: dict[str, dict[str, float | int]] = {}
    for variant in PULLBACK_VARIANTS:
        selected = [row for row in rows if row.variant == variant]
        returns = [row.total_return_percent for row in selected]
        drawdowns = [
            row.maximum_drawdown_percent for row in selected
        ]
        summary[variant] = {
            "windows": len(selected),
            "compounded_return_percent": (
                _compounded_return(returns)
            ),
            "mean_return_percent": statistics.fmean(returns),
            "median_return_percent": statistics.median(returns),
            "best_return_percent": max(returns),
            "worst_return_percent": min(returns),
            "mean_maximum_drawdown_percent": statistics.fmean(
                drawdowns
            ),
            "worst_maximum_drawdown_percent": max(drawdowns),
            "median_profit_factor": statistics.median(
                row.profit_factor for row in selected
            ),
            "total_trades": sum(row.trades for row in selected),
            "profitable_window_fraction": sum(
                value > 0 for value in returns
            )
            / len(returns),
            "total_fees": sum(row.total_fees for row in selected),
            "waiting_entries": sum(
                row.waiting_entries for row in selected
            ),
            "pullback_confirmed": sum(
                row.pullback_confirmed for row in selected
            ),
            "timed_out_entries": sum(
                row.timed_out_entries for row in selected
            ),
            "average_entry_price_improvement_percent": (
                statistics.fmean(
                    row.average_entry_price_improvement_percent
                    for row in selected
                    if row.pullback_confirmed
                )
                if any(row.pullback_confirmed for row in selected)
                else 0.0
            ),
        }
    return summary


def _compounded_return(returns: Sequence[float]) -> float:
    compounded = 1.0
    for value in returns:
        compounded *= 1 + value / 100
    return (compounded - 1) * 100


def git_commit(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def metadata(
    *,
    root: Path,
    data_path: Path,
    data: pd.DataFrame,
    config: StrategyV2Config,
) -> dict[str, object]:
    candles = dataframe_to_candles(data)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(root),
        "data_path": str(data_path.resolve()),
        "data_fingerprint": fingerprint_candles(candles),
        "candles": len(candles),
        "data_start": data["datetime"].min().isoformat(),
        "data_end": data["datetime"].max().isoformat(),
        "symbol": "ETHUSDT",
        "timeframe": "1h",
        "fast_ema": config.fast_ema,
        "slow_ema": config.slow_ema,
        "fee_rate": config.fee_rate,
        "initial_balance": config.initial_balance,
        "atr": asdict(config.atr),
        "adx": asdict(config.adx),
        "pullback": {
            **asdict(config.pullback),
            "touch_mode": config.pullback.touch_mode.value,
        },
        "walk_forward": {
            "train_months": config.train_months,
            "test_months": config.test_months,
            "step_months": config.step_months,
        },
    }
