from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

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


_TERMINAL = {
    ExecutionStatus.FILLED, ExecutionStatus.CANCELLED,
    ExecutionStatus.REJECTED, ExecutionStatus.FAILED,
}
_STATUS_RANK = {
    ExecutionStatus.ACCEPTED: 0,
    ExecutionStatus.OPEN: 1,
    ExecutionStatus.PARTIALLY_FILLED: 2,
    ExecutionStatus.FILLED: 3,
    ExecutionStatus.CANCELLED: 3,
    ExecutionStatus.REJECTED: 3,
    ExecutionStatus.FAILED: 3,
}


@dataclass(slots=True)
class _OrderLifecycle:
    request: ExecutionRequest
    bybit_side: str
    result: ExecutionResult
    cumulative_quantity: Decimal = Decimal("0")
    cumulative_value: Decimal = Decimal("0")
    status: ExecutionStatus = ExecutionStatus.ACCEPTED


class BybitExecutor(TradeExecutor):
    def __init__(
        self,
        client: BybitOrderClient,
        *,
        dry_run: bool = False,
    ) -> None:
        self.client = client
        self.dry_run = dry_run
        self._by_client_id: dict[str, _OrderLifecycle] = {}
        self._by_order_id: dict[str, _OrderLifecycle] = {}

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
        if request.client_order_id is not None:
            existing = self._by_client_id.get(request.client_order_id)
            if existing is not None:
                if existing.request != request or existing.bybit_side != bybit_side:
                    raise ValueError("client_order_id already belongs to a different order")
                return existing.result

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

        execution = ExecutionResult(
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
        lifecycle = _OrderLifecycle(request, bybit_side, execution, status=execution.status)
        if execution.client_order_id is not None:
            self._by_client_id[execution.client_order_id] = lifecycle
        if execution.order_id is not None:
            self._by_order_id[execution.order_id] = lifecycle
        return execution

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

        reconciled = self._status_to_execution_result(current)
        lifecycle = self._find_lifecycle(current)
        if lifecycle is not None:
            lifecycle.status = ExecutionStatus.CANCELLED
            lifecycle.result = replace(reconciled, status=ExecutionStatus.CANCELLED)
        return replace(reconciled, status=ExecutionStatus.CANCELLED)

    def _status_to_execution_result(
        self,
        status: OrderStatus,
    ) -> ExecutionResult:
        execution_status = _BYBIT_STATUS_MAP.get(
            status.order_status,
            ExecutionStatus.FAILED,
        )

        lifecycle = self._find_lifecycle(status)
        previous_quantity = lifecycle.cumulative_quantity if lifecycle else Decimal("0")
        previous_value = lifecycle.cumulative_value if lifecycle else Decimal("0")
        if status.executed_quantity < previous_quantity:
            raise RuntimeError("Bybit cumulative fill quantity regressed")
        cumulative_value = status.cumulative_execution_value
        if cumulative_value == 0 and status.average_price is not None:
            cumulative_value = status.average_price * status.executed_quantity
        if cumulative_value < previous_value:
            raise RuntimeError("Bybit cumulative execution value regressed")
        if lifecycle is not None and lifecycle.status in _TERMINAL:
            if execution_status != lifecycle.status:
                raise RuntimeError("Bybit order lifecycle regressed after terminal state")
        if (
            lifecycle is not None
            and _STATUS_RANK[execution_status] < _STATUS_RANK[lifecycle.status]
        ):
            raise RuntimeError("Bybit order lifecycle status regressed")
        delta_quantity = status.executed_quantity - previous_quantity
        delta_value = cumulative_value - previous_value
        if delta_quantity > 0 and delta_value <= 0:
            raise RuntimeError("Bybit actual average fill price is unavailable")
        delta_average = (
            delta_value / delta_quantity if delta_quantity > 0 else None
        )
        result = ExecutionResult(
            mode=self.mode,
            status=execution_status,
            symbol=status.symbol,
            side=self._position_side_from_order(status),
            requested_quantity=status.quantity,
            requested_price=status.price,
            executed_quantity=delta_quantity,
            average_price=delta_average,
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
        if lifecycle is not None:
            lifecycle.cumulative_quantity = status.executed_quantity
            lifecycle.cumulative_value = cumulative_value
            lifecycle.status = execution_status
            lifecycle.result = result
        return result

    def _find_lifecycle(self, status: OrderStatus) -> _OrderLifecycle | None:
        lifecycle = self._by_order_id.get(status.order_id)
        if lifecycle is None and status.order_link_id is not None:
            lifecycle = self._by_client_id.get(status.order_link_id)
        if lifecycle is not None:
            self._by_order_id.setdefault(status.order_id, lifecycle)
            if status.order_link_id is not None:
                self._by_client_id.setdefault(status.order_link_id, lifecycle)
        return lifecycle

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
