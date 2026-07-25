from __future__ import annotations

from dataclasses import replace
from itertools import count

from app.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    TradeExecutor,
)


class PaperExecutor(TradeExecutor):
    def __init__(self) -> None:
        self._orders: dict[str, ExecutionResult] = {}
        self._order_sequence = count(1)

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.PAPER

    def open_position(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        return self._execute(request)

    def close_position(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        return self._execute(request)

    def _execute(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        order_id = (
            f"paper-{next(self._order_sequence):08d}"
        )

        result = ExecutionResult(
            mode=self.mode,
            status=ExecutionStatus.FILLED,
            symbol=request.symbol,
            side=request.side,
            requested_quantity=request.quantity,
            requested_price=request.price,
            executed_quantity=request.quantity,
            average_price=request.price,
            order_id=order_id,
            client_order_id=request.client_order_id,
        )

        self._orders[order_id] = result
        return result

    def get_order_status(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> ExecutionResult:
        order = self._find_order(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
        )

        if order is None:
            raise ValueError("order not found")

        return order

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> ExecutionResult:
        order = self._find_order(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
        )

        if order is None:
            raise ValueError("order not found")

        cancelled = replace(
            order,
            status=ExecutionStatus.CANCELLED,
        )

        assert cancelled.order_id is not None
        self._orders[cancelled.order_id] = cancelled
        return cancelled

    def _find_order(
        self,
        *,
        symbol: str,
        order_id: str | None,
        client_order_id: str | None,
    ) -> ExecutionResult | None:
        normalized_symbol = symbol.strip().upper()

        if order_id is not None:
            normalized_order_id = order_id.strip()
            order = self._orders.get(normalized_order_id)

            if (
                order is not None
                and order.symbol == normalized_symbol
            ):
                return order

        if client_order_id is not None:
            normalized_client_order_id = (
                client_order_id.strip()
            )

            for order in self._orders.values():
                if (
                    order.symbol == normalized_symbol
                    and order.client_order_id
                    == normalized_client_order_id
                ):
                    return order

        return None
