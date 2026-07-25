from decimal import Decimal

import pytest

from app.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionStatus,
    TradeExecutor,
)
from app.paper_executor import PaperExecutor
from app.trading_types import PositionSide


def make_request(
    *,
    side: PositionSide = PositionSide.LONG,
    client_order_id: str | None = "client-001",
) -> ExecutionRequest:
    return ExecutionRequest(
        symbol="ETHUSDT",
        side=side,
        quantity=Decimal("0.02"),
        price=Decimal("3000"),
        client_order_id=client_order_id,
    )


def test_paper_executor_implements_trade_executor() -> None:
    executor = PaperExecutor()

    assert isinstance(executor, TradeExecutor)
    assert executor.mode == ExecutionMode.PAPER


def test_open_position_returns_filled_result() -> None:
    executor = PaperExecutor()

    result = executor.open_position(make_request())

    assert result.mode == ExecutionMode.PAPER
    assert result.status == ExecutionStatus.FILLED
    assert result.symbol == "ETHUSDT"
    assert result.side == PositionSide.LONG
    assert result.requested_quantity == Decimal("0.02")
    assert result.executed_quantity == Decimal("0.02")
    assert result.requested_price == Decimal("3000")
    assert result.average_price == Decimal("3000")
    assert result.order_id == "paper-00000001"
    assert result.client_order_id == "client-001"


def test_close_position_returns_filled_result() -> None:
    executor = PaperExecutor()

    result = executor.close_position(
        make_request(
            side=PositionSide.SHORT,
            client_order_id="close-001",
        )
    )

    assert result.status == ExecutionStatus.FILLED
    assert result.side == PositionSide.SHORT
    assert result.order_id == "paper-00000001"
    assert result.client_order_id == "close-001"


def test_order_ids_are_sequential() -> None:
    executor = PaperExecutor()

    first = executor.open_position(
        make_request(client_order_id="first")
    )
    second = executor.close_position(
        make_request(client_order_id="second")
    )

    assert first.order_id == "paper-00000001"
    assert second.order_id == "paper-00000002"


def test_get_order_status_by_order_id() -> None:
    executor = PaperExecutor()
    created = executor.open_position(make_request())

    result = executor.get_order_status(
        symbol=" ethusdt ",
        order_id=created.order_id,
    )

    assert result == created


def test_get_order_status_by_client_order_id() -> None:
    executor = PaperExecutor()
    created = executor.open_position(make_request())

    result = executor.get_order_status(
        symbol="ETHUSDT",
        client_order_id=" client-001 ",
    )

    assert result == created


def test_cancel_order_returns_cancelled_result() -> None:
    executor = PaperExecutor()
    created = executor.open_position(make_request())

    result = executor.cancel_order(
        symbol="ETHUSDT",
        order_id=created.order_id,
    )

    assert result.status == ExecutionStatus.CANCELLED
    assert result.order_id == created.order_id
    assert result.executed_quantity == created.executed_quantity
    assert result.average_price == created.average_price

    stored = executor.get_order_status(
        symbol="ETHUSDT",
        order_id=created.order_id,
    )
    assert stored == result


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        (
            "get_order_status",
            {
                "symbol": "ETHUSDT",
                "order_id": "paper-99999999",
            },
        ),
        (
            "cancel_order",
            {
                "symbol": "ETHUSDT",
                "client_order_id": "unknown",
            },
        ),
    ],
)
def test_unknown_order_raises_error(
    method_name: str,
    kwargs: dict[str, str],
) -> None:
    executor = PaperExecutor()
    method = getattr(executor, method_name)

    with pytest.raises(ValueError, match="order not found"):
        method(**kwargs)


def test_order_lookup_rejects_wrong_symbol() -> None:
    executor = PaperExecutor()
    created = executor.open_position(make_request())

    with pytest.raises(ValueError, match="order not found"):
        executor.get_order_status(
            symbol="BTCUSDT",
            order_id=created.order_id,
        )

