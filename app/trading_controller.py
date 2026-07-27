from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

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
    entry_price: Decimal | None = None
    stop_loss: Decimal | None = None

    def __post_init__(self) -> None:
        if self.position_quantity < 0:
            raise ValueError(
                "position_quantity must not be negative"
            )

        if (
            self.entry_price is not None
            and self.entry_price <= 0
        ):
            raise ValueError(
                "entry_price must be greater than zero"
            )

        if (
            self.stop_loss is not None
            and self.stop_loss <= 0
        ):
            raise ValueError(
                "stop_loss must be greater than zero"
            )

        if (
            self.entry_price is not None
            and self.stop_loss is not None
            and self.stop_loss >= self.entry_price
        ):
            raise ValueError(
                "LONG stop_loss must be below entry_price"
            )

        if (
            self.position_quantity == 0
            and (
                self.entry_price is not None
                or self.stop_loss is not None
            )
        ):
            raise ValueError(
                "flat position must not have "
                "entry_price or stop_loss"
            )

    @property
    def has_open_position(self) -> bool:
        return self.position_quantity > 0


class TradingControllerStateStoreProtocol(Protocol):
    def load(self) -> TradingControllerState:
        ...

    def save(
        self,
        state: TradingControllerState,
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class TradingControllerResult:
    action: TradeAction
    execution: ExecutionResult | None
    state: TradingControllerState
    skipped_reason: str | None = None


class TradingController:
    """
    Управляет состоянием одной LONG-позиции.

    Контроллер хранит:
    - количество открытой позиции;
    - фактическую цену входа;
    - активный стоп-лосс.
    """

    def __init__(
        self,
        runtime: TradingRuntime,
        *,
        state: TradingControllerState | None = None,
        state_store: (
            TradingControllerStateStoreProtocol | None
        ) = None,
    ) -> None:
        if state is not None and state_store is not None:
            raise ValueError(
                "state and state_store must not "
                "be provided together"
            )

        self.runtime = runtime
        self.state_store = state_store

        if state_store is not None:
            self._state = state_store.load()
        else:
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

        stop_loss = (
            Decimal(str(normalized.stop_loss))
            if normalized.stop_loss is not None
            else None
        )

        if (
            action == TradeAction.OPEN_LONG
            and stop_loss is not None
            and stop_loss >= price
        ):
            raise ValueError(
                "LONG stop_loss must be below entry price"
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

        state_changed = self._apply_execution(
            action=action,
            execution=execution,
            stop_loss=stop_loss,
        )

        if state_changed and self.state_store is not None:
            self.state_store.save(self._state)

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
        stop_loss: Decimal | None,
    ) -> bool:
        if execution is None:
            return False

        if execution.status != ExecutionStatus.FILLED:
            return False

        executed_quantity = execution.executed_quantity

        if executed_quantity <= 0:
            return False

        if execution.average_price is None:
            return False

        if action == TradeAction.OPEN_LONG:
            self._state = TradingControllerState(
                position_quantity=executed_quantity,
                entry_price=execution.average_price,
                stop_loss=stop_loss,
            )
            return True

        if action == TradeAction.CLOSE_LONG:
            remaining_quantity = (
                self._state.position_quantity
                - executed_quantity
            )

            if remaining_quantity <= 0:
                self._state = TradingControllerState()
            else:
                self._state = TradingControllerState(
                    position_quantity=remaining_quantity,
                    entry_price=self._state.entry_price,
                    stop_loss=self._state.stop_loss,
                )

            return True

        return False
