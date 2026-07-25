from decimal import Decimal

import pytest

from app.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    TradeExecutor,
)
from app.trading_types import PositionSide


def make_request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol=" ethusdt ",
        side=PositionSide.LONG,
        quantity=Decimal("0.01"),
        price=Decimal("3000"),
        client_order_id=" order-001 ",
    )


def test_execution_request_normalizes_values() -> None:
    request = make_request()

    assert request.symbol == "ETHUSDT"
    assert request.client_order_id == "order-001"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("symbol", " ", "symbol must not be empty"),
        (
            "quantity",
            Decimal("0"),
            "quantity must be greater than zero",
        ),
        (
            "price",
            Decimal("-1"),
            "price must be greater than zero",
        ),
        (
            "client_order_id",
            " ",
            "client_order_id must not be empty",
        ),
    ],
)
def test_execution_request_rejects_invalid_values(
    field: str,
    value: object,
    message: str,
) -> None:
    values = {
        "symbol": "ETHUSDT",
        "side": PositionSide.LONG,
        "quantity": Decimal("0.01"),
        "price": Decimal("3000"),
        "client_order_id": "order-001",
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        ExecutionRequest(**values)


def test_execution_result_reports_success_and_completion() -> None:
    result = ExecutionResult(
        mode=ExecutionMode.PAPER,
        status=ExecutionStatus.FILLED,
        symbol="ethusdt",
        side=PositionSide.LONG,
        requested_quantity=Decimal("0.01"),
        requested_price=Decimal("3000"),
        executed_quantity=Decimal("0.01"),
        average_price=Decimal("3001"),
        order_id=" paper-001 ",
    )

    assert result.symbol == "ETHUSDT"
    assert result.order_id == "paper-001"
    assert result.is_successful is True
    assert result.is_complete is True


def test_failed_execution_is_not_successful() -> None:
    result = ExecutionResult(
        mode=ExecutionMode.LIVE,
        status=ExecutionStatus.FAILED,
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        requested_quantity=Decimal("0.01"),
        requested_price=Decimal("3000"),
        message="exchange unavailable",
    )

    assert result.is_successful is False
    assert result.is_complete is True


def test_open_execution_is_successful_but_incomplete() -> None:
    result = ExecutionResult(
        mode=ExecutionMode.DRY_RUN,
        status=ExecutionStatus.OPEN,
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        requested_quantity=Decimal("0.01"),
        requested_price=Decimal("3000"),
    )

    assert result.is_successful is True
    assert result.is_complete is False


def test_execution_result_requires_average_price_for_fill() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "average_price is required when "
            "executed_quantity is greater than zero"
        ),
    ):
        ExecutionResult(
            mode=ExecutionMode.PAPER,
            status=ExecutionStatus.PARTIALLY_FILLED,
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            requested_quantity=Decimal("0.01"),
            requested_price=Decimal("3000"),
            executed_quantity=Decimal("0.005"),
        )


def test_execution_result_rejects_overfill() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "executed_quantity must not exceed "
            "requested_quantity"
        ),
    ):
        ExecutionResult(
            mode=ExecutionMode.LIVE,
            status=ExecutionStatus.FILLED,
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            requested_quantity=Decimal("0.01"),
            requested_price=Decimal("3000"),
            executed_quantity=Decimal("0.02"),
            average_price=Decimal("3000"),
        )


def test_trade_executor_protocol_accepts_implementation() -> None:
    class StubExecutor:
        @property
        def mode(self) -> ExecutionMode:
            return ExecutionMode.DRY_RUN

        def open_position(
            self,
            request: ExecutionRequest,
        ) -> ExecutionResult:
            return self._result(request)

        def close_position(
            self,
            request: ExecutionRequest,
        ) -> ExecutionResult:
            return self._result(request)

        def cancel_order(
            self,
            *,
            symbol: str,
            order_id: str | None = None,
            client_order_id: str | None = None,
        ) -> ExecutionResult:
            return self._empty_result(symbol)

        def get_order_status(
            self,
            *,
            symbol: str,
            order_id: str | None = None,
            client_order_id: str | None = None,
        ) -> ExecutionResult:
            return self._empty_result(symbol)

        def _result(
            self,
            request: ExecutionRequest,
        ) -> ExecutionResult:
            return ExecutionResult(
                mode=self.mode,
                status=ExecutionStatus.ACCEPTED,
                symbol=request.symbol,
                side=request.side,
                requested_quantity=request.quantity,
                requested_price=request.price,
            )

        def _empty_result(
            self,
            symbol: str,
        ) -> ExecutionResult:
            return ExecutionResult(
                mode=self.mode,
                status=ExecutionStatus.ACCEPTED,
                symbol=symbol,
                side=PositionSide.LONG,
                requested_quantity=Decimal("0.01"),
                requested_price=Decimal("1"),
            )

    assert isinstance(StubExecutor(), TradeExecutor)
