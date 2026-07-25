import json
from decimal import Decimal

import pytest

from app.bybit_account import (
    BybitAPIError,
    BybitAccountConfig,
)
from app.bybit_orders import (
    CREATE_ORDER_PATH,
    BybitOrderClient,
)
from app.order_builder import SpotLimitOrder


@pytest.fixture
def order() -> SpotLimitOrder:
    return SpotLimitOrder(
        symbol="ETHUSDT",
        side="Buy",
        quantity=Decimal("0.00200"),
        price=Decimal("3000.00"),
    )


def test_create_limit_order_dry_run_does_not_send_request(
    order: SpotLimitOrder,
) -> None:
    calls = []

    def fake_post_json(url, headers, body, timeout_seconds):
        calls.append((url, headers, body, timeout_seconds))
        raise AssertionError("HTTP request must not be sent")

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
        ),
        http_post_json=fake_post_json,
    )

    result = client.create_limit_order(
        order,
        order_link_id="dry-run-1",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.order_id is None
    assert result.order_link_id == "dry-run-1"
    assert result.payload == {
        "category": "spot",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "orderType": "Limit",
        "qty": "0.00200",
        "price": "3000.00",
        "orderLinkId": "dry-run-1",
    }
    assert calls == []


def test_create_limit_order_sends_signed_request(
    order: SpotLimitOrder,
) -> None:
    calls = []

    def fake_post_json(url, headers, body, timeout_seconds):
        calls.append((url, headers, body, timeout_seconds))
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": "123456",
                "orderLinkId": "client-order-1",
            },
        }

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="visible-key",
            api_secret="hidden-secret",
            base_url="https://example.test",
            timeout_seconds=3,
        ),
        http_post_json=fake_post_json,
        clock_ms=lambda: 1000,
    )

    result = client.create_limit_order(
        order,
        order_link_id="client-order-1",
        dry_run=False,
    )

    assert result.dry_run is False
    assert result.order_id == "123456"
    assert result.order_link_id == "client-order-1"

    assert len(calls) == 1
    url, headers, body, timeout_seconds = calls[0]

    assert url == (
        f"https://example.test{CREATE_ORDER_PATH}"
    )
    assert headers["X-BAPI-API-KEY"] == "visible-key"
    assert headers["X-BAPI-TIMESTAMP"] == "1000"
    assert headers["X-BAPI-RECV-WINDOW"] == "5000"
    assert "X-BAPI-SIGN" in headers
    assert timeout_seconds == 3

    payload = json.loads(body.decode("utf-8"))

    assert payload == {
        "category": "spot",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "orderType": "Limit",
        "qty": "0.00200",
        "price": "3000.00",
        "orderLinkId": "client-order-1",
    }


def test_create_limit_order_raises_safe_api_error(
    order: SpotLimitOrder,
) -> None:
    def fake_post_json(url, headers, body, timeout_seconds):
        return {
            "retCode": 10004,
            "retMsg": "invalid sign",
        }

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="visible-key",
            api_secret="hidden-secret",
        ),
        http_post_json=fake_post_json,
    )

    with pytest.raises(BybitAPIError) as exc:
        client.create_limit_order(
            order,
            dry_run=False,
        )

    assert exc.value.ret_code == 10004
    assert "hidden-secret" not in str(exc.value)


def test_create_limit_order_rejects_unexpected_response(
    order: SpotLimitOrder,
) -> None:
    def fake_post_json(url, headers, body, timeout_seconds):
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {},
        }

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
        ),
        http_post_json=fake_post_json,
    )

    with pytest.raises(
        ValueError,
        match="unexpected create order response",
    ):
        client.create_limit_order(
            order,
            dry_run=False,
        )


@pytest.mark.parametrize(
    "order_link_id",
    ["", "   "],
)
def test_create_limit_order_rejects_empty_order_link_id(
    order: SpotLimitOrder,
    order_link_id: str,
) -> None:
    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
        )
    )

    with pytest.raises(
        ValueError,
        match="order_link_id must not be empty",
    ):
        client.create_limit_order(
            order,
            order_link_id=order_link_id,
        )


def test_order_client_uses_testnet_url() -> None:
    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            testnet=True,
        )
    )

    assert client.base_url == "https://api-testnet.bybit.com"


from app.bybit_orders import (
    CANCEL_ORDER_PATH,
    REALTIME_ORDER_PATH,
)


def test_get_order_returns_parsed_status() -> None:
    calls = []

    def fake_get_json(url, headers, timeout_seconds):
        calls.append((url, headers, timeout_seconds))
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "orderId": "order-123",
                        "orderLinkId": "bot-123",
                        "symbol": "ETHUSDT",
                        "side": "Buy",
                        "orderType": "Limit",
                        "orderStatus": "New",
                        "price": "2500.12",
                        "qty": "0.00200",
                        "cumExecQty": "0",
                        "leavesQty": "0.00200",
                    }
                ]
            },
        }

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            base_url="https://example.test",
            timeout_seconds=3,
        ),
        http_get_json=fake_get_json,
        clock_ms=lambda: 1000,
    )

    status = client.get_order(
        symbol="ethusdt",
        order_id="order-123",
    )

    assert status.order_id == "order-123"
    assert status.order_link_id == "bot-123"
    assert status.symbol == "ETHUSDT"
    assert status.side == "Buy"
    assert status.order_type == "Limit"
    assert status.order_status == "New"
    assert status.price == Decimal("2500.12")
    assert status.quantity == Decimal("0.00200")
    assert status.executed_quantity == Decimal("0")
    assert status.remaining_quantity == Decimal("0.00200")

    assert len(calls) == 1
    url, headers, timeout_seconds = calls[0]

    assert url.startswith(
        f"https://example.test{REALTIME_ORDER_PATH}?"
    )
    assert "category=spot" in url
    assert "orderId=order-123" in url
    assert "symbol=ETHUSDT" in url
    assert headers["X-BAPI-API-KEY"] == "key"
    assert "X-BAPI-SIGN" in headers
    assert timeout_seconds == 3


def test_get_order_reports_missing_order() -> None:
    def fake_get_json(url, headers, timeout_seconds):
        return {
            "retCode": 0,
            "result": {
                "list": [],
            },
        }

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
        ),
        http_get_json=fake_get_json,
    )

    with pytest.raises(LookupError, match="order not found"):
        client.get_order(
            symbol="ETHUSDT",
            order_id="missing",
        )


def test_get_order_accepts_order_link_id() -> None:
    calls = []

    def fake_get_json(url, headers, timeout_seconds):
        calls.append(url)
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "orderId": "exchange-id",
                        "orderLinkId": "client-id",
                        "symbol": "ETHUSDT",
                        "side": "Sell",
                        "orderType": "Limit",
                        "orderStatus": "Filled",
                        "price": "3000",
                        "qty": "0.001",
                        "cumExecQty": "0.001",
                        "leavesQty": "",
                    }
                ]
            },
        }

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            base_url="https://example.test",
        ),
        http_get_json=fake_get_json,
    )

    status = client.get_order(
        symbol="ETHUSDT",
        order_link_id="client-id",
    )

    assert status.order_status == "Filled"
    assert status.remaining_quantity == Decimal("0")
    assert "orderLinkId=client-id" in calls[0]


def test_cancel_order_dry_run_does_not_send_request() -> None:
    calls = []

    def fake_post_json(url, headers, body, timeout_seconds):
        calls.append((url, headers, body, timeout_seconds))
        raise AssertionError("HTTP request must not be sent")

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
        ),
        http_post_json=fake_post_json,
    )

    result = client.cancel_order(
        symbol="ethusdt",
        order_id="order-123",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.order_id == "order-123"
    assert result.order_link_id is None
    assert result.payload == {
        "category": "spot",
        "symbol": "ETHUSDT",
        "orderId": "order-123",
    }
    assert calls == []


def test_cancel_order_sends_signed_request() -> None:
    calls = []

    def fake_post_json(url, headers, body, timeout_seconds):
        calls.append((url, headers, body, timeout_seconds))
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": "order-123",
                "orderLinkId": "bot-123",
            },
        }

    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            base_url="https://example.test",
            timeout_seconds=3,
        ),
        http_post_json=fake_post_json,
        clock_ms=lambda: 1000,
    )

    result = client.cancel_order(
        symbol="ETHUSDT",
        order_link_id="bot-123",
        dry_run=False,
    )

    assert result.dry_run is False
    assert result.order_id == "order-123"
    assert result.order_link_id == "bot-123"

    assert len(calls) == 1
    url, headers, body, timeout_seconds = calls[0]

    assert url == (
        f"https://example.test{CANCEL_ORDER_PATH}"
    )
    assert headers["X-BAPI-API-KEY"] == "key"
    assert headers["X-BAPI-TIMESTAMP"] == "1000"
    assert "X-BAPI-SIGN" in headers
    assert timeout_seconds == 3

    assert json.loads(body.decode("utf-8")) == {
        "category": "spot",
        "symbol": "ETHUSDT",
        "orderLinkId": "bot-123",
    }


@pytest.mark.parametrize(
    ("order_id", "order_link_id"),
    [
        (None, None),
        ("", None),
        (None, "   "),
    ],
)
def test_order_operations_require_identifier(
    order_id,
    order_link_id,
) -> None:
    client = BybitOrderClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
        )
    )

    with pytest.raises(ValueError):
        client.get_order(
            symbol="ETHUSDT",
            order_id=order_id,
            order_link_id=order_link_id,
        )

    with pytest.raises(ValueError):
        client.cancel_order(
            symbol="ETHUSDT",
            order_id=order_id,
            order_link_id=order_link_id,
        )
