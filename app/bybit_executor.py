from __future__ import annotations

from app.bybit_orders import BybitOrderClient, OrderStatus
from app.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    TradeExecutor,
)
from app.order_builder import SpotLimitOrder
from app.trading_types import PositionSide


_BYBIT_STATUS_MAP = {
    "Created": ExecutionStatus.ACCEPTED,
    "New": ExecutionStatus.OPEN,
    "Untriggered": ExecutionStatus.OPEN,
    "PartiallyFilled": ExecutionStatus.PARTIALLY_FILLED,
    "Filled": ExecutionStatus.FILLED,
    "Cancelled": ExecutionStatus.CANCELLED,
    "PartiallyFilledCanceled": ExecutionStatus.CANCELLED,
    "Rejected": ExecutionStatus.REJECTED,
    "Deactivated": ExecutionStatus.REJECTED,
}


class BybitExecutor(TradeExecutor):
    def __init__(
        self,
        client: BybitOrderClient,
        *,
        dry_run: bool = False,
    ) -> None:
        self.client = client
        self.dry_run = dry_run

    @property
    def mode(self) -> ExecutionMode:
        if self.dry_run:
            return ExecutionMode.DRY_RUN

        return ExecutionMode.LIVE

    def open_position(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        self._require_long_position(request)
        return self._submit(request, bybit_side="Buy")

    def close_position(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        self._require_long_position(request)
        return self._submit(request, bybit_side="Sell")

    def _submit(
        self,
        request: ExecutionRequest,
        *,
        bybit_side: str,
    ) -> ExecutionResult:
        order = SpotLimitOrder(
            symbol=request.symbol,
            side=bybit_side,
            quantity=request.quantity,
            price=request.price,
        )

        try:
            result = self.client.create_limit_order(
                order,
                order_link_id=request.client_order_id,
                dry_run=self.dry_run,
            )
        except Exception as exc:
            return ExecutionResult(
                mode=self.mode,
                status=ExecutionStatus.FAILED,
                symbol=request.symbol,
                side=request.side,
                requested_quantity=request.quantity,
                requested_price=request.price,
                client_order_id=request.client_order_id,
                message=str(exc),
            )

        return ExecutionResult(
            mode=self.mode,
            status=(
                ExecutionStatus.ACCEPTED
                if not result.dry_run
                else ExecutionStatus.OPEN
            ),
            symbol=request.symbol,
            side=request.side,
            requested_quantity=request.quantity,
            requested_price=request.price,
            order_id=result.order_id,
            client_order_id=result.order_link_id,
            message=(
                "dry-run order was not submitted"
                if result.dry_run
                else None
            ),
        )

    def get_order_status(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> ExecutionResult:
        if self.dry_run:
            raise RuntimeError(
                "order status is unavailable in dry-run mode"
            )

        status = self.client.get_order(
            symbol=symbol,
            order_id=order_id,
            order_link_id=client_order_id,
        )

        return self._status_to_execution_result(status)

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> ExecutionResult:
        if self.dry_run:
            raise RuntimeError(
                "order cancellation is unavailable "
                "in dry-run mode"
            )

        current = self.client.get_order(
            symbol=symbol,
            order_id=order_id,
            order_link_id=client_order_id,
        )

        self.client.cancel_order(
            symbol=symbol,
            order_id=order_id,
            order_link_id=client_order_id,
            dry_run=False,
        )

        return ExecutionResult(
            mode=self.mode,
            status=ExecutionStatus.CANCELLED,
            symbol=current.symbol,
            side=self._position_side_from_order(current),
            requested_quantity=current.quantity,
            requested_price=current.price,
            executed_quantity=current.executed_quantity,
            average_price=(
                current.price
                if current.executed_quantity > 0
                else None
            ),
            order_id=current.order_id,
            client_order_id=current.order_link_id,
        )

    def _status_to_execution_result(
        self,
        status: OrderStatus,
    ) -> ExecutionResult:
        execution_status = _BYBIT_STATUS_MAP.get(
            status.order_status,
            ExecutionStatus.FAILED,
        )

        return ExecutionResult(
            mode=self.mode,
            status=execution_status,
            symbol=status.symbol,
            side=self._position_side_from_order(status),
            requested_quantity=status.quantity,
            requested_price=status.price,
            executed_quantity=status.executed_quantity,
            average_price=(
                status.price
                if status.executed_quantity > 0
                else None
            ),
            order_id=status.order_id,
            client_order_id=status.order_link_id,
            message=(
                None
                if status.order_status in _BYBIT_STATUS_MAP
                else (
                    "unsupported Bybit order status: "
                    f"{status.order_status}"
                )
            ),
        )

    @staticmethod
    def _require_long_position(
        request: ExecutionRequest,
    ) -> None:
        if request.side != PositionSide.LONG:
            raise ValueError(
                "Bybit spot executor supports "
                "LONG positions only"
            )

    @staticmethod
    def _position_side_from_order(
        status: OrderStatus,
    ) -> PositionSide:
        if status.side not in {"Buy", "Sell"}:
            raise ValueError(
                f"unsupported Bybit order side: {status.side}"
            )

        return PositionSide.LONG
