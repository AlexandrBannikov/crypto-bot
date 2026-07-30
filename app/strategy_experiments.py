from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Sequence

from app.ema_cross_stop_strategy import EMACrossStopStrategy
from app.engine import BacktestEngine, Candle
from app.strategy_diagnostics import PositionState


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    name: str
    short_period: int
    long_period: int
    stop_loss_percent: float = 2.0
    price_confirmation_percent: float = 0.0
    minimum_trend_spread_percent: float = 0.0

    def build_strategy(self) -> EMACrossStopStrategy:
        return EMACrossStopStrategy(
            short_period=self.short_period,
            long_period=self.long_period,
            stop_loss_percent=self.stop_loss_percent,
            price_confirmation_percent=self.price_confirmation_percent,
            minimum_trend_spread_percent=(
                self.minimum_trend_spread_percent
            ),
        )


DEFAULT_EXPERIMENTS = (
    ExperimentConfig("control_ema_20_50", 20, 50),
    ExperimentConfig("faster_ema_10_30", 10, 30),
    ExperimentConfig("slower_ema_40_100", 40, 100),
    ExperimentConfig("relaxed_filters", 15, 40),
    ExperimentConfig(
        "strengthened_filters",
        20,
        50,
        price_confirmation_percent=0.25,
        minimum_trend_spread_percent=0.10,
    ),
)


@dataclass(frozen=True, slots=True)
class PeriodMetrics:
    return_percent: float
    max_drawdown_percent: float
    trades: int
    win_rate_percent: float
    profit_factor: float
    fees: float
    average_hours_in_position: float
    average_days_between_entries: float | None
    months_without_trades: int
    blocked_entry_reasons: dict[str, int]
    monthly_returns_percent: dict[str, float]


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    name: str
    parameters: dict[str, Any]
    full: PeriodMetrics
    train: PeriodMetrics
    test: PeriodMetrics
    train_test_warning: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_experiments(
    candles: Sequence[Candle],
    *,
    configs: Sequence[ExperimentConfig] = DEFAULT_EXPERIMENTS,
    initial_balance: float = 1000.0,
    commission_rate: float = 0.001,
    train_fraction: float = 0.7,
) -> tuple[ExperimentResult, ...]:
    if len(candles) < 2:
        raise ValueError("at least two candles are required")
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between zero and one")
    split = max(1, min(len(candles) - 1, int(len(candles) * train_fraction)))
    train = candles[:split]
    test = candles[split:]
    results = []
    for config in configs:
        full_metrics = _run_period(
            candles, config, initial_balance, commission_rate
        )
        train_metrics = _run_period(
            train, config, initial_balance, commission_rate
        )
        test_metrics = _run_period(
            test, config, initial_balance, commission_rate
        )
        results.append(
            ExperimentResult(
                name=config.name,
                parameters=asdict(config),
                full=full_metrics,
                train=train_metrics,
                test=test_metrics,
                train_test_warning=(
                    train_metrics.return_percent > 0
                    and test_metrics.return_percent < 0
                ),
            )
        )
    return tuple(results)


def _run_period(
    candles: Sequence[Candle],
    config: ExperimentConfig,
    initial_balance: float,
    commission_rate: float,
) -> PeriodMetrics:
    result = BacktestEngine(
        initial_balance=initial_balance,
        commission_rate=commission_rate,
    ).run(candles, config.build_strategy())
    trades = result.trades
    fees = sum(trade.entry_fee + trade.exit_fee for trade in trades)
    durations = [
        (trade.exit_timestamp - trade.entry_timestamp) / 3600
        for trade in trades
    ]
    entries = [trade.entry_timestamp for trade in trades]
    entry_gaps = [
        (right - left) / 86400
        for left, right in zip(entries, entries[1:])
    ]
    trade_months = {
        _month(trade.entry_timestamp) for trade in trades
    }
    all_months = {_month(candle.timestamp) for candle in candles}
    monthly_profit = Counter()
    for trade in trades:
        monthly_profit[_month(trade.exit_timestamp)] += trade.profit
    diagnostics = _blocked_reasons(candles, config)
    return PeriodMetrics(
        return_percent=result.total_return_percent,
        max_drawdown_percent=result.max_drawdown_percent,
        trades=len(trades),
        win_rate_percent=result.win_rate_percent,
        profit_factor=result.profit_factor,
        fees=fees,
        average_hours_in_position=mean(durations) if durations else 0.0,
        average_days_between_entries=mean(entry_gaps) if entry_gaps else None,
        months_without_trades=len(all_months - trade_months),
        blocked_entry_reasons=dict(diagnostics.most_common()),
        monthly_returns_percent={
            month: monthly_profit[month] / initial_balance * 100
            for month in sorted(all_months)
        },
    )


def _blocked_reasons(
    candles: Sequence[Candle],
    config: ExperimentConfig,
) -> Counter[str]:
    strategy = config.build_strategy()
    reasons: Counter[str] = Counter()
    position = PositionState.FLAT
    for index in range(len(candles)):
        decision = strategy.evaluate_with_diagnostics(
            candles, index, position_state=position
        )
        if position == PositionState.FLAT:
            if decision.decision.value == "buy":
                position = PositionState.LONG
            else:
                reasons.update(
                    reason.value for reason in decision.failed_conditions
                )
        elif decision.decision.value == "sell":
            position = PositionState.FLAT
    return reasons


def _month(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")


def format_experiment_table(
    results: Sequence[ExperimentResult],
) -> str:
    header = (
        "variant                  full %   dd % trades "
        "train %  test % stable warning"
    )
    rows = [header, "-" * len(header)]
    for item in results:
        stable_months = sum(
            value >= 0
            for value in item.full.monthly_returns_percent.values()
        )
        total_months = len(item.full.monthly_returns_percent)
        rows.append(
            f"{item.name:<24} "
            f"{item.full.return_percent:>7.2f} "
            f"{item.full.max_drawdown_percent:>6.2f} "
            f"{item.full.trades:>6} "
            f"{item.train.return_percent:>7.2f} "
            f"{item.test.return_percent:>7.2f} "
            f"{stable_months:>2}/{total_months:<2} "
            f"{'TRAIN+/TEST-' if item.train_test_warning else '-'}"
        )
    return "\n".join(rows)
