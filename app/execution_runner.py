from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    TradeExecutor,
)
from app.trading_types import (
    PositionSide,
    TradeAction,
)


class ExecutionRunnerError(RuntimeError):
    """Ошибка координации исполнения торгового действия."""


@dataclass(frozen=True, slots=True)
class ExecutionCommand:
    symbol: str
    action: TradeAction
    quantity: Decimal
    price: Decimal
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        if self.quantity <= 0:
            raise ValueError(
                "quantity must be greater than zero"
            )

        if self.price <= 0:
            raise ValueError(
                "price must be greater than zero"
            )

        object.__setattr__(
            self,
            "symbol",
            normalized_symbol,
        )


class ExecutionRunner:
    """
    Координатор между торговым действием и TradeExecutor.

    На текущем этапе поддерживается только LONG spot:
    - OPEN_LONG;
    - CLOSE_LONG;
    - HOLD.

    LIVE-исполнение заблокировано по умолчанию.
    """

    def __init__(
        self,
        executor: TradeExecutor,
        *,
        allow_live: bool = False,
    ) -> None:
        self.executor = executor
        self.allow_live = allow_live

    def execute(
        self,
        command: ExecutionCommand,
    ) -> ExecutionResult | None:
        if command.action == TradeAction.HOLD:
            return None

        self._ensure_safe_mode()

        request = ExecutionRequest(
            symbol=command.symbol,
            side=PositionSide.LONG,
            quantity=command.quantity,
            price=command.price,
            client_order_id=command.client_order_id,
        )

        if command.action == TradeAction.OPEN_LONG:
            return self.executor.open_position(request)

        if command.action == TradeAction.CLOSE_LONG:
            return self.executor.close_position(request)

        if command.action in {
            TradeAction.OPEN_SHORT,
            TradeAction.CLOSE_SHORT,
        }:
            raise ExecutionRunnerError(
                "SHORT execution is not supported "
                "for Bybit spot trading"
            )

        raise ExecutionRunnerError(
            f"unsupported trade action: {command.action}"
        )

    def _ensure_safe_mode(self) -> None:
        if (
            self.executor.mode == ExecutionMode.LIVE
            and not self.allow_live
        ):
            raise ExecutionRunnerError(
                "LIVE execution is blocked by ExecutionRunner"
            )
