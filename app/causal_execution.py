"""Shared next-candle PAPER execution policy for live-like and replay paths."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from app.candle import Candle
from app.runtime_versions import EXECUTION_POLICY_VERSION
from app.trade_signal import TradeSignal
from app.trading_controller import TradingController, TradingControllerResult
from app.trading_types import TradeAction


D = Decimal
CAUSAL_POSITION_LIFECYCLE = "gap_stop_v1"
LEGACY_POSITION_LIFECYCLE = "legacy_close_stop_v1"


@dataclass(frozen=True, slots=True)
class CausalStepResult:
    executions: tuple[TradingControllerResult, ...]
    stop_triggered: bool
    stop_fill_price: Decimal | None
    opened_on_candle: bool


def queue_pending_action(
    controller: TradingController,
    *,
    action: TradeAction,
    signal_timestamp: int,
    signal_price: Decimal,
) -> None:
    if signal_timestamp < 0 or signal_price <= 0:
        raise ValueError("invalid signal metadata")
    state = controller.state
    if action == TradeAction.OPEN_LONG and state.has_open_position:
        action = TradeAction.HOLD
    if action == TradeAction.CLOSE_LONG and not state.has_open_position:
        action = TradeAction.HOLD
    controller._state = replace(
        state,
        pending_action=action,
        pending_signal_timestamp=(signal_timestamp if action != TradeAction.HOLD else None),
        pending_signal_price=(signal_price if action != TradeAction.HOLD else None),
        last_processed_candle_timestamp=signal_timestamp,
    )
    if controller.state_store is not None:
        controller.state_store.save(controller.state)


def process_candle_execution(
    controller: TradingController,
    *,
    symbol: str,
    candle: Candle,
    entry_quantity: Decimal,
    stop_distance_pct: Decimal = D("0.02"),
) -> CausalStepResult:
    """Execute prior intent at open, then apply only already-active stops."""
    if not D("0") < stop_distance_pct < D("1"):
        raise ValueError("stop_distance_pct must be in 0..1")
    state_before = controller.state
    pending = state_before.pending_action
    signal_timestamp = state_before.pending_signal_timestamp
    open_price = D(str(candle.open))
    executions: list[TradingControllerResult] = []
    opened_on_candle = False

    if pending != TradeAction.HOLD:
        signal = pending
        if pending == TradeAction.OPEN_LONG:
            stop = open_price * (D("1") - stop_distance_pct)
            signal = TradeSignal(action=TradeAction.OPEN_LONG, stop_loss=stop)
        result = controller.process_signal(
            symbol=symbol,
            signal=signal,
            entry_quantity=entry_quantity,
            price=open_price,
            client_order_id=f"controller-fill-{candle.timestamp}-{pending.value}",
            signal_timestamp=signal_timestamp,
            fill_timestamp=candle.timestamp,
            position_lifecycle_version=(
                CAUSAL_POSITION_LIFECYCLE
                if pending == TradeAction.OPEN_LONG else None
            ),
        )
        executions.append(result)
        opened_on_candle = (
            pending == TradeAction.OPEN_LONG
            and not state_before.has_open_position
            and result.state.has_open_position
        )

    # A stop created by an entry at this open starts with the next candle. This
    # prevents a fully-known candle from retroactively stopping its own fill.
    state = controller.state
    if not state.has_open_position or opened_on_candle or state.stop_loss is None:
        return CausalStepResult(tuple(executions), False, None, opened_on_candle)

    stop = state.stop_loss
    fill: Decimal | None = None
    if state.position_lifecycle_version == CAUSAL_POSITION_LIFECYCLE:
        candle_open = D(str(candle.open))
        candle_low = D(str(candle.low))
        if candle_open <= stop:
            fill = candle_open
        elif candle_low <= stop:
            fill = stop
    else:
        # Existing production positions retain their historical close-only
        # lifecycle until they close naturally.
        candle_close = D(str(candle.close))
        if candle_close <= stop:
            fill = candle_close

    if fill is not None:
        result = controller.process_signal(
            symbol=symbol,
            signal=TradeAction.CLOSE_LONG,
            entry_quantity=entry_quantity,
            price=fill,
            client_order_id=f"controller-stop-{candle.timestamp}",
            exit_reason="stop_loss",
            fill_timestamp=candle.timestamp,
        )
        executions.append(result)
        return CausalStepResult(tuple(executions), True, fill, opened_on_candle)
    return CausalStepResult(tuple(executions), False, None, opened_on_candle)


def execution_metadata(*, signal_timestamp: int, fill_timestamp: int,
                       signal_price: Decimal, fill_price: Decimal) -> dict:
    if fill_timestamp <= signal_timestamp:
        raise ValueError("fill must occur after the signal candle")
    return {
        "signal_timestamp": signal_timestamp,
        "fill_timestamp": fill_timestamp,
        "signal_price": str(signal_price),
        "fill_price": str(fill_price),
        "execution_policy_version": EXECUTION_POLICY_VERSION,
    }
