from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from app.signal_normalizer import normalize_signal
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_runtime import (
    RuntimeRequest,
    TradingRuntime,
)
from app.trading_types import TradeAction


@dataclass(frozen=True, slots=True)
class TradingControllerState:
    position_quantity: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.position_quantity < 0:
            raise ValueError(
                "position_quantity must not be negative"
            )

    @property
    def has_open_position(self) -> bool:
        return self.position_quantity > 0


@dataclass(frozen=True, slots=True)
class TradingControllerResult:
    action: TradeAction
    execution: ExecutionResult | None
    state: TradingControllerState
    skipped_reason: str | None = None


class TradingController:
    """
    Управляет состоянием LONG-позиции и передаёт команды
    в TradingRuntime.

    На текущем этапе:
    - поддерживается одна LONG-позиция;
    - OPEN_LONG использует переданный entry_quantity;
    - CLOSE_LONG закрывает весь сохранённый объём;
    - повторное открытие и закрытие без позиции пропускаются.
    """

    def __init__(
        self,
        runtime: TradingRuntime,
        *,
        state: TradingControllerState | None = None,
    ) -> None:
        self.runtime = runtime
        self._state = state or TradingControllerState()

    @property
    def state(self) -> TradingControllerState:
        return self._state

    def process_signal(
        self,
        *,
        symbol: str,
        signal: Signal | TradeSignal | TradeAction,
        entry_quantity: Decimal,
        price: Decimal,
        client_order_id: str | None = None,
    ) -> TradingControllerResult:
        if entry_quantity <= 0:
            raise ValueError(
                "entry_quantity must be greater than zero"
            )

        if price <= 0:
            raise ValueError(
                "price must be greater than zero"
            )

        normalized = normalize_signal(signal)
        action = normalized.action

        if not isinstance(action, TradeAction):
            raise TypeError(
                "normalized signal action must be TradeAction"
            )

        if action == TradeAction.HOLD:
            return TradingControllerResult(
                action=action,
                execution=None,
                state=self._state,
                skipped_reason="hold signal",
            )

        if action == TradeAction.OPEN_LONG:
            if self._state.has_open_position:
                return TradingControllerResult(
                    action=action,
                    execution=None,
                    state=self._state,
                    skipped_reason="long position already open",
                )

            quantity = entry_quantity

        elif action == TradeAction.CLOSE_LONG:
            if not self._state.has_open_position:
                return TradingControllerResult(
                    action=action,
                    execution=None,
                    state=self._state,
                    skipped_reason="no long position to close",
                )

            quantity = self._state.position_quantity

        else:
            raise ValueError(
                f"unsupported controller action: {action}"
            )

        execution = self.runtime.process_signal(
            RuntimeRequest(
                symbol=symbol,
                signal=action,
                quantity=quantity,
                price=price,
                client_order_id=client_order_id,
            )
        )

        self._apply_execution(
            action=action,
            execution=execution,
        )

        return TradingControllerResult(
            action=action,
            execution=execution,
            state=self._state,
        )

    def _apply_execution(
        self,
        *,
        action: TradeAction,
        execution: ExecutionResult | None,
    ) -> None:
        if execution is None:
            return

        if execution.status != ExecutionStatus.FILLED:
            return

        executed_quantity = execution.executed_quantity

        if executed_quantity <= 0:
            return

        if action == TradeAction.OPEN_LONG:
            self._state = TradingControllerState(
                position_quantity=executed_quantity,
            )
            return

        if action == TradeAction.CLOSE_LONG:
            remaining_quantity = (
                self._state.position_quantity
                - executed_quantity
            )

            if remaining_quantity < 0:
                remaining_quantity = Decimal("0")

            self._state = TradingControllerState(
                position_quantity=remaining_quantity,
            )
