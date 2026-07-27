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
from app.trade_accounting import (
    ClosedTradeAccounting,
    calculate_long_trade_accounting,
)
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
    virtual_balance: Decimal = Decimal("1000")
    total_fees: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    closed_trades: int = 0
    entry_fee: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.position_quantity < 0:
            raise ValueError(
                "position_quantity must not be negative"
            )

        if self.virtual_balance < 0:
            raise ValueError(
                "virtual_balance must not be negative"
            )

        if self.total_fees < 0:
            raise ValueError(
                "total_fees must not be negative"
            )

        if self.closed_trades < 0:
            raise ValueError(
                "closed_trades must not be negative"
            )

        if self.entry_fee < 0:
            raise ValueError(
                "entry_fee must not be negative"
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
                or self.entry_fee != 0
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
    accounting: ClosedTradeAccounting | None = None


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
        fee_rate: Decimal = Decimal("0.001"),
    ) -> None:
        if state is not None and state_store is not None:
            raise ValueError(
                "state and state_store must not "
                "be provided together"
            )

        if fee_rate < 0:
            raise ValueError(
                "fee_rate must not be negative"
            )

        self.runtime = runtime
        self.state_store = state_store
        self.fee_rate = fee_rate

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
            entry_notional = price * quantity
            entry_fee = entry_notional * self.fee_rate

            if entry_notional + entry_fee > (
                self._state.virtual_balance
            ):
                return TradingControllerResult(
                    action=action,
                    execution=None,
                    state=self._state,
                    skipped_reason="insufficient virtual balance",
                )

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

        state_changed, accounting = self._apply_execution(
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
            accounting=accounting,
        )

    def _apply_execution(
        self,
        *,
        action: TradeAction,
        execution: ExecutionResult | None,
        stop_loss: Decimal | None,
    ) -> tuple[bool, ClosedTradeAccounting | None]:
        if execution is None:
            return False, None

        if execution.status not in {
            ExecutionStatus.FILLED,
            ExecutionStatus.PARTIALLY_FILLED,
        }:
            return False, None

        executed_quantity = execution.executed_quantity

        if executed_quantity <= 0:
            return False, None

        if execution.average_price is None:
            return False, None

        if action == TradeAction.OPEN_LONG:
            entry_notional = (
                execution.average_price * executed_quantity
            )
            entry_fee = entry_notional * self.fee_rate
            self._state = TradingControllerState(
                position_quantity=executed_quantity,
                entry_price=execution.average_price,
                stop_loss=stop_loss,
                virtual_balance=(
                    self._state.virtual_balance
                    - entry_notional
                    - entry_fee
                ),
                total_fees=self._state.total_fees,
                realized_pnl=self._state.realized_pnl,
                closed_trades=self._state.closed_trades,
                entry_fee=entry_fee,
            )
            return True, None

        if action == TradeAction.CLOSE_LONG:
            accounting = None

            if self._state.entry_price is not None:
                accounting = calculate_long_trade_accounting(
                    entry_price=self._state.entry_price,
                    exit_price=execution.average_price,
                    quantity=executed_quantity,
                    fee_rate=self.fee_rate,
                )

            remaining_quantity = (
                self._state.position_quantity
                - executed_quantity
            )

            virtual_balance = self._state.virtual_balance
            total_fees = self._state.total_fees
            realized_pnl = self._state.realized_pnl
            closed_trades = self._state.closed_trades
            remaining_entry_fee = self._state.entry_fee

            if accounting is not None:
                virtual_balance += (
                    accounting.exit_notional
                    - accounting.exit_fee
                )
                total_fees += (
                    accounting.entry_fee
                    + accounting.exit_fee
                )
                realized_pnl += accounting.net_pnl
                closed_trades += 1
                remaining_entry_fee -= accounting.entry_fee

            if remaining_quantity <= 0:
                self._state = TradingControllerState(
                    virtual_balance=virtual_balance,
                    total_fees=total_fees,
                    realized_pnl=realized_pnl,
                    closed_trades=closed_trades,
                )
            else:
                self._state = TradingControllerState(
                    position_quantity=remaining_quantity,
                    entry_price=self._state.entry_price,
                    stop_loss=self._state.stop_loss,
                    virtual_balance=virtual_balance,
                    total_fees=total_fees,
                    realized_pnl=realized_pnl,
                    closed_trades=closed_trades,
                    entry_fee=remaining_entry_fee,
                )

            return True, accounting

        return False, None
