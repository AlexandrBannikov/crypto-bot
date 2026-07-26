from decimal import Decimal

import pytest

from app.bybit_executor import BybitExecutor
from app.bybit_orders import (
    CancelOrderResult,
    OrderResult,
    OrderStatus,
)
from app.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionStatus,
    TradeExecutor,
)
from app.trading_types import PositionSide


class FakeBybitOrderClient:
    def __init__(self) -> None:
        self.created_orders = []
        self.cancelled_orders = []
        self.status_requests = []
        self.create_result = OrderResult(
            order_id="order-123",
            order_link_id="client-123",
            dry_run=False,
            payload={},
        )
        self.order_status = OrderStatus(
            order_id="order-123",
            order_link_id="client-123",
            symbol="ETHUSDT",
            side="Buy",
            order_type="Limit",
            order_status="New",
            price=Decimal("3000"),
            quantity=Decimal("0.02"),
            executed_quantity=Decimal("0"),
            remaining_quantity=Decimal("0.02"),
        )

    def create_limit_order(
        self,
        order,
        *,
        order_link_id=None,
        dry_run=True,
    ):
        self.created_orders.append(
            {
                "order": order,
                "order_link_id": order_link_id,
                "dry_run": dry_run,
            }
        )

        if dry_run:
            return OrderResult(
                order_id=None,
                order_link_id=order_link_id,
                dry_run=True,
                payload=order.to_bybit_payload(),
            )

        return self.create_result

    def get_order(
        self,
        *,
        symbol,
        order_id=None,
        order_link_id=None,
    ):
        self.status_requests.append(
            {
                "symbol": symbol,
                "order_id": order_id,
                "order_link_id": order_link_id,
            }
        )
        return self.order_status

    def cancel_order(
        self,
        *,
        symbol,
        order_id=None,
        order_link_id=None,
        dry_run=True,
    ):
        self.cancelled_orders.append(
            {
                "symbol": symbol,
                "order_id": order_id,
                "order_link_id": order_link_id,
                "dry_run": dry_run,
            }
        )
        return CancelOrderResult(
            order_id=order_id,
            order_link_id=order_link_id,
            dry_run=dry_run,
            payload={},
        )


def make_request(
    *,
    side: PositionSide = PositionSide.LONG,
    client_order_id: str | None = "client-123",
) -> ExecutionRequest:
    return ExecutionRequest(
        symbol="ETHUSDT",
        side=side,
        quantity=Decimal("0.02"),
        price=Decimal("3000"),
        client_order_id=client_order_id,
    )


def test_bybit_executor_implements_trade_executor() -> None:
    executor = BybitExecutor(
        FakeBybitOrderClient(),
        dry_run=False,
    )

    assert isinstance(executor, TradeExecutor)
    assert executor.mode == ExecutionMode.LIVE


def test_dry_run_executor_has_dry_run_mode() -> None:
    executor = BybitExecutor(
        FakeBybitOrderClient(),
        dry_run=True,
    )

    assert executor.mode == ExecutionMode.DRY_RUN


def test_open_position_creates_buy_order() -> None:
    client = FakeBybitOrderClient()
    executor = BybitExecutor(client, dry_run=False)

    result = executor.open_position(make_request())

    assert result.mode == ExecutionMode.LIVE
    assert result.status == ExecutionStatus.ACCEPTED
    assert result.order_id == "order-123"
    assert result.client_order_id == "client-123"

    assert len(client.created_orders) == 1
    created = client.created_orders[0]

    assert created["order"].side == "Buy"
    assert created["order"].symbol == "ETHUSDT"
    assert created["order"].quantity == Decimal("0.02")
    assert created["order"].price == Decimal("3000")
    assert created["dry_run"] is False


def test_close_position_creates_sell_order() -> None:
    client = FakeBybitOrderClient()
    executor = BybitExecutor(client, dry_run=False)

    result = executor.close_position(
        make_request(client_order_id="close-123")
    )

    assert result.status == ExecutionStatus.ACCEPTED

    created = client.created_orders[0]
    assert created["order"].side == "Sell"
    assert created["order_link_id"] == "close-123"


def test_dry_run_order_is_not_submitted() -> None:
    client = FakeBybitOrderClient()
    executor = BybitExecutor(client, dry_run=True)

    result = executor.open_position(make_request())

    assert result.mode == ExecutionMode.DRY_RUN
    assert result.status == ExecutionStatus.OPEN
    assert result.order_id is None
    assert result.client_order_id == "client-123"
    assert result.message == "dry-run order was not submitted"
    assert client.created_orders[0]["dry_run"] is True


def test_short_position_is_rejected() -> None:
    executor = BybitExecutor(
        FakeBybitOrderClient(),
        dry_run=False,
    )

    with pytest.raises(
        ValueError,
        match="LONG positions only",
    ):
        executor.open_position(
            make_request(side=PositionSide.SHORT)
        )


def test_create_order_failure_returns_failed_result() -> None:
    class FailingClient(FakeBybitOrderClient):
        def create_limit_order(
            self,
            order,
            *,
            order_link_id=None,
            dry_run=True,
        ):
            raise RuntimeError("exchange unavailable")

    executor = BybitExecutor(
        FailingClient(),
        dry_run=False,
    )

    result = executor.open_position(make_request())

    assert result.status == ExecutionStatus.FAILED
    assert result.message == "exchange unavailable"
    assert result.order_id is None


@pytest.mark.parametrize(
    ("bybit_status", "expected_status"),
    [
        ("Created", ExecutionStatus.ACCEPTED),
        ("New", ExecutionStatus.OPEN),
        (
            "PartiallyFilled",
            ExecutionStatus.PARTIALLY_FILLED,
        ),
        ("Filled", ExecutionStatus.FILLED),
        ("Cancelled", ExecutionStatus.CANCELLED),
        ("Rejected", ExecutionStatus.REJECTED),
    ],
)
def test_get_order_status_maps_bybit_status(
    bybit_status: str,
    expected_status: ExecutionStatus,
) -> None:
    client = FakeBybitOrderClient()
    client.order_status = OrderStatus(
        order_id="order-123",
        order_link_id="client-123",
        symbol="ETHUSDT",
        side="Buy",
        order_type="Limit",
        order_status=bybit_status,
        price=Decimal("3000"),
        quantity=Decimal("0.02"),
        executed_quantity=(
            Decimal("0.02")
            if bybit_status == "Filled"
            else Decimal("0")
        ),
        remaining_quantity=(
            Decimal("0")
            if bybit_status == "Filled"
            else Decimal("0.02")
        ),
    )
    executor = BybitExecutor(client, dry_run=False)

    result = executor.get_order_status(
        symbol="ETHUSDT",
        order_id="order-123",
    )

    assert result.status == expected_status
    assert result.order_id == "order-123"
    assert result.client_order_id == "client-123"


def test_filled_order_contains_execution_data() -> None:
    client = FakeBybitOrderClient()
    client.order_status = OrderStatus(
        order_id="order-123",
        order_link_id="client-123",
        symbol="ETHUSDT",
        side="Buy",
        order_type="Limit",
        order_status="Filled",
        price=Decimal("3000"),
        quantity=Decimal("0.02"),
        executed_quantity=Decimal("0.02"),
        remaining_quantity=Decimal("0"),
    )
    executor = BybitExecutor(client, dry_run=False)

    result = executor.get_order_status(
        symbol="ETHUSDT",
        order_id="order-123",
    )

    assert result.executed_quantity == Decimal("0.02")
    assert result.average_price == Decimal("3000")


def test_cancel_order_returns_cancelled_result() -> None:
    client = FakeBybitOrderClient()
    executor = BybitExecutor(client, dry_run=False)

    result = executor.cancel_order(
        symbol="ETHUSDT",
        order_id="order-123",
    )

    assert result.status == ExecutionStatus.CANCELLED
    assert result.order_id == "order-123"

    assert client.cancelled_orders == [
        {
            "symbol": "ETHUSDT",
            "order_id": "order-123",
            "order_link_id": None,
            "dry_run": False,
        }
    ]


@pytest.mark.parametrize(
    "method_name",
    [
        "get_order_status",
        "cancel_order",
    ],
)
def test_dry_run_rejects_remote_order_operations(
    method_name: str,
) -> None:
    executor = BybitExecutor(
        FakeBybitOrderClient(),
        dry_run=True,
    )
    method = getattr(executor, method_name)

    with pytest.raises(
        RuntimeError,
        match="unavailable in dry-run mode",
    ):
        method(
            symbol="ETHUSDT",
            order_id="order-123",
        )


def test_unknown_bybit_status_becomes_failed() -> None:
    client = FakeBybitOrderClient()
    client.order_status = OrderStatus(
        order_id="order-123",
        order_link_id=None,
        symbol="ETHUSDT",
        side="Buy",
        order_type="Limit",
        order_status="MysteryStatus",
        price=Decimal("3000"),
        quantity=Decimal("0.02"),
        executed_quantity=Decimal("0"),
        remaining_quantity=Decimal("0.02"),
    )
    executor = BybitExecutor(client, dry_run=False)

    result = executor.get_order_status(
        symbol="ETHUSDT",
        order_id="order-123",
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.message == (
        "unsupported Bybit order status: MysteryStatus"
    )
