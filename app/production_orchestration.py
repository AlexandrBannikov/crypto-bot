"""Sequential, causal orchestration for Production PAPER candles."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Sequence

import pandas as pd

from app.candle import Candle
from app.canonical_features import CanonicalFeatureSnapshot, CanonicalFeatureStore
from app.causal_execution import (
    CAUSAL_POSITION_LIFECYCLE,
    CausalStepResult,
    process_candle_execution,
    queue_pending_action,
)
from app.indicators import ema
from app.market_continuity import CandleContinuity, validate_candle_continuity
from app.paper_strategy_router import PaperStrategyDecision, PaperStrategyRouter
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_controller import TradingController, TradingControllerResult
from app.trading_types import TradeAction


SignalFunction = Callable[[Sequence[Candle]], tuple[Signal, float, float]]


@dataclass(frozen=True, slots=True)
class ProductionCandleCycle:
    candle: Candle
    score_snapshot: CanonicalFeatureSnapshot | None
    score_status: str
    unresolved_gap: bool
    strategy_signal: Signal
    fast_ema: float
    slow_ema: float
    decision: PaperStrategyDecision
    effective_action: TradeAction
    open_step: CausalStepResult
    close_execution: TradingControllerResult | None
    state_before: object
    state_after: object


def calculate_ema_signal(
    candles: Sequence[Candle], *, fast_period: int = 20, slow_period: int = 50,
) -> tuple[Signal, float, float]:
    if len(candles) < 2:
        raise RuntimeError("insufficient candles for EMA signal")
    close = pd.Series([item.close for item in candles], dtype="float64")
    fast = ema(close, fast_period)
    slow = ema(close, slow_period)
    if any(pd.isna(value) for value in (fast.iloc[-1], slow.iloc[-1])):
        raise RuntimeError("insufficient candles for EMA signal")
    previous_fast, previous_slow = fast.iloc[-2], slow.iloc[-2]
    current_fast, current_slow = fast.iloc[-1], slow.iloc[-1]
    if previous_fast <= previous_slow and current_fast > current_slow:
        signal = Signal.BUY
    elif previous_fast >= previous_slow and current_fast < current_slow:
        signal = Signal.SELL
    else:
        signal = Signal.HOLD
    return signal, float(current_fast), float(current_slow)


def select_unprocessed_candles(
    candles: Sequence[Candle], *, last_processed_timestamp: int | None,
    timeframe_seconds: int,
) -> tuple[tuple[Candle, ...], CandleContinuity]:
    continuity = validate_candle_continuity(
        candles, timeframe_seconds=timeframe_seconds,
        last_processed_timestamp=last_processed_timestamp,
    )
    if last_processed_timestamp is None:
        selected = continuity.candles[-1:]  # explicit startup baseline
    else:
        selected = tuple(
            item for item in continuity.candles
            if item.timestamp > last_processed_timestamp
        )
    return selected, continuity


def process_production_candles(
    candles: Sequence[Candle],
    *,
    last_processed_timestamp: int | None,
    timeframe_seconds: int,
    symbol: str,
    controller: TradingController,
    router: PaperStrategyRouter,
    feature_store: CanonicalFeatureStore,
    entry_quantity: Decimal,
    signal_function: SignalFunction = calculate_ema_signal,
    entries_permitted: bool = True,
) -> tuple[ProductionCandleCycle, ...]:
    state_cursor = controller.state.last_processed_candle_timestamp
    effective_cursor = max(
        (value for value in (last_processed_timestamp, state_cursor) if value is not None),
        default=None,
    )
    selected, continuity = select_unprocessed_candles(
        candles, last_processed_timestamp=effective_cursor,
        timeframe_seconds=timeframe_seconds,
    )
    if not selected:
        return ()
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    cycles: list[ProductionCandleCycle] = []
    for candle in selected:
        history = tuple(item for item in ordered if item.timestamp <= candle.timestamp)
        state_before = controller.state
        open_step = process_candle_execution(
            controller, symbol=symbol, candle=candle,
            entry_quantity=entry_quantity,
        )
        strategy_signal, fast, slow = signal_function(history)
        decision = router.route(strategy_signal, history)
        snapshot = feature_store.exact(candle.timestamp)
        score_status = "READY" if snapshot is not None else "PENDING"
        action = decision.execution_signal.action
        if action == TradeAction.OPEN_LONG and (
            not entries_permitted
            or continuity.unresolved_gap
            or snapshot is None
        ):
            action = TradeAction.HOLD

        close_execution: TradingControllerResult | None = None
        if (
            action == TradeAction.CLOSE_LONG
            and controller.state.has_open_position
            and controller.state.position_lifecycle_version
            != CAUSAL_POSITION_LIFECYCLE
        ):
            # Preserve the existing Production position's legacy same-close
            # signal exit until that exact position closes naturally.
            close_execution = controller.process_signal(
                symbol=symbol, signal=TradeAction.CLOSE_LONG,
                entry_quantity=entry_quantity,
                price=Decimal(str(candle.close)),
                client_order_id=f"controller-legacy-close-{candle.timestamp}",
                fill_timestamp=candle.timestamp,
            )
            action = TradeAction.HOLD

        queue_pending_action(
            controller, action=action,
            signal_timestamp=candle.timestamp,
            signal_price=Decimal(str(candle.close)),
        )
        cycles.append(ProductionCandleCycle(
            candle=candle,
            score_snapshot=snapshot,
            score_status=score_status,
            unresolved_gap=continuity.unresolved_gap,
            strategy_signal=strategy_signal,
            fast_ema=fast,
            slow_ema=slow,
            decision=decision,
            effective_action=action,
            open_step=open_step,
            close_execution=close_execution,
            state_before=state_before,
            state_after=controller.state,
        ))
    return tuple(cycles)
