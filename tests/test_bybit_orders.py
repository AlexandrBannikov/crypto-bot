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
