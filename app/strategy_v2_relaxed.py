from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import statistics
from time import perf_counter
from typing import Sequence

import pandas as pd

from app.candle import Candle
from app.engine import BacktestEngine, BacktestResult, Trade
from app.indicators import adx, atr
from app.trading_types import ExitReason


class RelaxedPullbackMode(str, Enum):
    LOW_TOUCH_CLOSE_ABOVE = "LOW_TOUCH_CLOSE_ABOVE"
    LOW_TOUCH = "LOW_TOUCH"
    CLOSE_NEAR_EMA = "CLOSE_NEAR_EMA"
    PERCENT_RETRACE = "PERCENT_RETRACE"
    HYBRID = "HYBRID"


@dataclass(frozen=True, slots=True)
class RelaxedPullbackConfig:
    mode: RelaxedPullbackMode
    max_wait_bars: int
    tolerance: float | None = None
    retrace_pct: float | None = None

    def __post_init__(self) -> None:
        if self.max_wait_bars not in {2, 3, 5, 8}:
            raise ValueError("max_wait_bars must be one of 2, 3, 5, 8")
        if self.mode in {
            RelaxedPullbackMode.CLOSE_NEAR_EMA,
            RelaxedPullbackMode.HYBRID,
        }:
            if self.tolerance is None or self.tolerance <= 0:
                raise ValueError("positive tolerance is required")
        elif self.tolerance is not None:
            raise ValueError("tolerance is not used by this mode")
        if self.mode in {
            RelaxedPullbackMode.PERCENT_RETRACE,
            RelaxedPullbackMode.HYBRID,
        }:
            if self.retrace_pct is None or self.retrace_pct <= 0:
                raise ValueError("positive retrace_pct is required")
        elif self.retrace_pct is not None:
            raise ValueError("retrace_pct is not used by this mode")

    @property
    def identifier(self) -> str:
        tolerance = (
            f"{self.tolerance:.4f}" if self.tolerance is not None else "-"
        )
        retrace = (
            f"{self.retrace_pct:.4f}"
            if self.retrace_pct is not None
            else "-"
        )
        return (
            f"{self.mode.value}|wait={self.max_wait_bars}"
            f"|tol={tolerance}|retrace={retrace}"
        )


def relaxed_grid() -> tuple[RelaxedPullbackConfig, ...]:
    waits = (2, 3, 5, 8)
    tolerances = (0.0025, 0.0050, 0.0075)
    retraces = (0.0025, 0.0050, 0.0075)
    configs: list[RelaxedPullbackConfig] = []
    for mode in (
        RelaxedPullbackMode.LOW_TOUCH_CLOSE_ABOVE,
        RelaxedPullbackMode.LOW_TOUCH,
    ):
        for wait in waits:
            configs.append(RelaxedPullbackConfig(mode, wait))
    for tolerance in tolerances:
        for wait in waits:
            configs.append(
                RelaxedPullbackConfig(
                    RelaxedPullbackMode.CLOSE_NEAR_EMA,
                    wait,
                    tolerance=tolerance,
                )
            )
    for retrace in retraces:
        for wait in waits:
            configs.append(
                RelaxedPullbackConfig(
                    RelaxedPullbackMode.PERCENT_RETRACE,
                    wait,
                    retrace_pct=retrace,
                )
            )
    for tolerance in tolerances:
        for retrace in retraces:
            for wait in waits:
                configs.append(
                    RelaxedPullbackConfig(
                        RelaxedPullbackMode.HYBRID,
                        wait,
                        tolerance=tolerance,
                        retrace_pct=retrace,
                    )
                )
    return tuple(configs)


@dataclass(frozen=True, slots=True)
class ResearchFeatures:
    candles: tuple[Candle, ...]
    fast_ema: tuple[float, ...]
    slow_ema: tuple[float, ...]
    atr_relative: tuple[float, ...]
    adx: tuple[float, ...]
    cross_up: tuple[bool, ...]
    cross_down: tuple[bool, ...]


def precompute_features(
    candles: Sequence[Candle],
    *,
    fast_period: int = 20,
    slow_period: int = 50,
    atr_period: int = 14,
    adx_period: int = 14,
) -> ResearchFeatures:
    if not candles:
        raise ValueError("candles must not be empty")
    close = pd.Series([item.close for item in candles], dtype=float)
    frame = pd.DataFrame(
        {
            "high": [item.high for item in candles],
            "low": [item.low for item in candles],
            "close": close,
        }
    )
    fast = close.ewm(span=fast_period, adjust=False).mean()
    slow = close.ewm(span=slow_period, adjust=False).mean()
    atr_values = atr(frame, atr_period) / close
    adx_values = adx(frame, adx_period)
    cross_up = [False] * len(candles)
    cross_down = [False] * len(candles)
    for index in range(slow_period, len(candles)):
        cross_up[index] = (
            fast.iloc[index - 1] <= slow.iloc[index - 1]
            and fast.iloc[index] > slow.iloc[index]
        )
        cross_down[index] = (
            fast.iloc[index - 1] >= slow.iloc[index - 1]
            and fast.iloc[index] < slow.iloc[index]
        )
    return ResearchFeatures(
        tuple(candles),
        tuple(float(value) for value in fast),
        tuple(float(value) for value in slow),
        tuple(float(value) for value in atr_values),
        tuple(float(value) for value in adx_values),
        tuple(cross_up),
        tuple(cross_down),
    )


def confirms_pullback(
    config: RelaxedPullbackConfig,
    *,
    low: float,
    close: float,
    fast_ema: float,
    cross_price: float,
) -> bool:
    if not all(
        math.isfinite(value)
        for value in (low, close, fast_ema, cross_price)
    ):
        return False
    low_touch = low <= fast_ema
    close_near = (
        config.tolerance is not None
        and abs(close - fast_ema) / fast_ema <= config.tolerance
    )
    retraced = (
        config.retrace_pct is not None
        and (cross_price - close) / cross_price >= config.retrace_pct
    )
    if config.mode is RelaxedPullbackMode.LOW_TOUCH_CLOSE_ABOVE:
        return low_touch and close > fast_ema
    if config.mode is RelaxedPullbackMode.LOW_TOUCH:
        return low_touch
    if config.mode is RelaxedPullbackMode.CLOSE_NEAR_EMA:
        return close_near
    if config.mode is RelaxedPullbackMode.PERCENT_RETRACE:
        return retraced
    return low_touch or close_near or retraced


@dataclass(frozen=True, slots=True)
class PullbackStats:
    ema_signals: int
    confirmed: int
    timed_out: int
    cancelled: int
    wait_bars: tuple[int, ...]
    improvements: tuple[float, ...]
    worse_entries: int
    blocked_entries: int


@dataclass(frozen=True, slots=True)
class Simulation:
    result: BacktestResult
    stats: PullbackStats
    exposure_percent: float
    total_fees: float
    average_trade: float


def simulate(
    features: ResearchFeatures,
    *,
    initial_balance: float = 1000.0,
    fee_rate: float = 0.001,
    trade_start_index: int = 0,
    pullback: RelaxedPullbackConfig | None = None,
    use_atr: bool = False,
    use_adx: bool = False,
    atr_minimum: float = 0.005,
    atr_maximum: float = 0.020,
    adx_minimum: float = 20.0,
) -> Simulation:
    candles = features.candles
    balance = initial_balance
    quantity = 0.0
    entry_price: float | None = None
    entry_timestamp: int | None = None
    entry_fee = 0.0
    pending_open = False
    pending_close = False
    pending_cross: tuple[int, float] | None = None
    trades: list[Trade] = []
    equity_curve = [initial_balance]
    waits: list[int] = []
    improvements: list[float] = []
    ema_signals = confirmed = timed_out = cancelled = 0
    worse_entries = blocked_entries = 0
    held_seconds = 0
    trade_start_timestamp = candles[trade_start_index].timestamp

    def open_long(index: int, price: float) -> None:
        nonlocal balance, quantity, entry_price, entry_timestamp, entry_fee
        entry_fee = balance * fee_rate
        position_value = balance - entry_fee
        quantity = position_value / price
        balance = 0.0
        entry_price = price
        entry_timestamp = candles[index].timestamp

    def close_long(index: int, price: float, reason: ExitReason) -> None:
        nonlocal balance, quantity, entry_price, entry_timestamp, entry_fee
        assert entry_price is not None and entry_timestamp is not None
        exit_notional = quantity * price
        exit_fee = exit_notional * fee_rate
        released = exit_notional - exit_fee
        profit = released - (quantity * entry_price + entry_fee)
        trades.append(
            Trade(
                entry_timestamp=entry_timestamp,
                exit_timestamp=candles[index].timestamp,
                entry_price=entry_price,
                exit_price=price,
                quantity=quantity,
                entry_fee=entry_fee,
                exit_fee=exit_fee,
                profit=profit,
                profit_percent=profit
                / (quantity * entry_price + entry_fee)
                * 100,
                exit_reason=reason,
            )
        )
        balance = released
        quantity = 0.0
        entry_price = None
        entry_timestamp = None
        entry_fee = 0.0

    for index, candle in enumerate(candles):
        if pending_open and entry_price is None:
            open_long(index, candle.open)
        pending_open = False
        if pending_close and entry_price is not None:
            close_long(index, candle.open, ExitReason.SIGNAL)
        pending_close = False

        if index >= trade_start_index:
            if features.cross_down[index]:
                if pending_cross is not None:
                    cancelled += 1
                    pending_cross = None
                if entry_price is not None:
                    pending_close = True
            elif features.cross_up[index] and entry_price is None:
                if pullback is None:
                    allowed = _indicators_allow(
                        features,
                        index,
                        use_atr,
                        use_adx,
                        atr_minimum,
                        atr_maximum,
                        adx_minimum,
                    )
                    if allowed:
                        pending_open = True
                    else:
                        blocked_entries += 1
                elif pending_cross is None:
                    ema_signals += 1
                    pending_cross = (index, candle.close)

            if pullback is not None and pending_cross is not None:
                cross_index, cross_price = pending_cross
                if index > cross_index:
                    indicator_values = (
                        features.fast_ema[index],
                        features.slow_ema[index],
                    )
                    if not all(math.isfinite(value) for value in indicator_values):
                        cancelled += 1
                        pending_cross = None
                    elif features.fast_ema[index] <= features.slow_ema[index]:
                        cancelled += 1
                        pending_cross = None
                    elif confirms_pullback(
                        pullback,
                        low=candle.low,
                        close=candle.close,
                        fast_ema=features.fast_ema[index],
                        cross_price=cross_price,
                    ):
                        confirmed += 1
                        wait = index - cross_index
                        waits.append(wait)
                        improvement = (
                            cross_price - candle.close
                        ) / cross_price * 100
                        if _indicators_allow(
                            features,
                            index,
                            use_atr,
                            use_adx,
                            atr_minimum,
                            atr_maximum,
                            adx_minimum,
                        ):
                            improvements.append(improvement)
                            worse_entries += improvement < 0
                            open_long(index, candle.close)
                        else:
                            blocked_entries += 1
                        pending_cross = None
                    elif index - cross_index >= pullback.max_wait_bars:
                        timed_out += 1
                        pending_cross = None

        if entry_price is None:
            equity_curve.append(balance)
        else:
            equity_curve.append(
                quantity * candle.close
            )

    if pending_cross is not None:
        cancelled += 1
    if entry_price is not None:
        close_long(len(candles) - 1, candles[-1].close, ExitReason.END_OF_DATA)
        equity_curve.append(balance)
    for trade in trades:
        held_seconds += max(
            0,
            trade.exit_timestamp
            - max(trade.entry_timestamp, trade_start_timestamp),
        )
    span = max(1, candles[-1].timestamp - trade_start_timestamp)
    engine = BacktestEngine(initial_balance, fee_rate)
    result = engine._build_result(
        final_balance=balance,
        trades=trades,
        equity_curve=equity_curve,
    )
    return Simulation(
        result=result,
        stats=PullbackStats(
            ema_signals,
            confirmed,
            timed_out,
            cancelled,
            tuple(waits),
            tuple(improvements),
            worse_entries,
            blocked_entries,
        ),
        exposure_percent=held_seconds / span * 100,
        total_fees=sum(
            trade.entry_fee + trade.exit_fee for trade in trades
        ),
        average_trade=(
            statistics.fmean(trade.profit for trade in trades)
            if trades
            else 0.0
        ),
    )


def _indicators_allow(
    features: ResearchFeatures,
    index: int,
    use_atr: bool,
    use_adx: bool,
    atr_minimum: float,
    atr_maximum: float,
    adx_minimum: float,
) -> bool:
    if use_atr:
        value = features.atr_relative[index]
        if not math.isfinite(value) or not atr_minimum <= value <= atr_maximum:
            return False
    if use_adx:
        value = features.adx[index]
        if not math.isfinite(value) or value < adx_minimum:
            return False
    return True


def timed_call(function, *args, **kwargs):
    started = perf_counter()
    result = function(*args, **kwargs)
    return result, perf_counter() - started
