import hashlib
import hmac

import pytest

from app.bybit_account import (
    BYBIT_MAINNET_API_URL,
    BYBIT_TESTNET_API_URL,
    BybitAccountConfig,
)
from app.bybit_order_executor import (
    ORDER_CREATE_PATH,
    BybitOrderExecutor,
    BybitOrderExecutorConfig,
)
from app.order_executor import (
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)


def make_account(
    *,
    testnet: bool = True,
) -> BybitAccountConfig:
    return BybitAccountConfig(
        api_key="test-key",
        api_secret="test-secret",
        testnet=testnet,
        recv_window=5000,
        timeout_seconds=3,
    )


def test_disabled_executor_rejects_without_http_call() -> None:
    called = False

    def fake_post(*_):
        nonlocal called
        called = True
        return {}

    executor = BybitOrderExecutor(
        BybitOrderExecutorConfig(
            account=make_account(),
            enable_trading=False,
        ),
        http_post_json=fake_post,
    )
    request = OrderRequest(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        quantity=1,
    )

    result = executor.submit_order(request)

    assert result.status == OrderStatus.REJECTED
    assert "disabled" in result.message
    assert called is False


def test_enabled_executor_submits_signed_market_order() -> None:
    captured = {}

    def fake_post(
        url,
        body,
        headers,
        timeout_seconds,
    ):
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        captured["timeout"] = timeout_seconds

        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": "order-123",
            },
        }

    executor = BybitOrderExecutor(
        BybitOrderExecutorConfig(
            account=make_account(),
            category="linear",
            enable_trading=True,
        ),
        http_post_json=fake_post,
        clock_ms=lambda: 1234567890,
    )
    request = OrderRequest(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        quantity=0.5,
        stop_loss=95,
    )

    result = executor.submit_order(request)

    expected_body = {
        "category": "linear",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "orderType": "Market",
        "qty": "0.5",
        "timeInForce": "IOC",
        "positionIdx": 0,
        "reduceOnly": False,
        "stopLoss": "95",
    }
    body_string = (
        '{"category":"linear","orderType":"Market",'
        '"positionIdx":0,"qty":"0.5","reduceOnly":false,'
        '"side":"Buy","stopLoss":"95","symbol":"ETHUSDT",'
        '"timeInForce":"IOC"}'
    )
    expected_signature = hmac.new(
        b"test-secret",
        (
            "1234567890"
            "test-key"
            "5000"
            + body_string
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert captured["url"] == (
        BYBIT_TESTNET_API_URL
        + ORDER_CREATE_PATH
    )
    assert captured["body"] == expected_body
    assert captured["headers"]["X-BAPI-SIGN"] == (
        expected_signature
    )
    assert captured["headers"]["X-BAPI-TIMESTAMP"] == "1234567890"
    assert captured["timeout"] == 3
    assert result.status == OrderStatus.ACCEPTED
    assert result.order_id == "order-123"


def test_limit_reduce_only_order_body() -> None:
    captured = {}

    def fake_post(url, body, headers, timeout_seconds):
        captured["body"] = body

        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"orderId": "close-1"},
        }

    executor = BybitOrderExecutor(
        BybitOrderExecutorConfig(
            account=make_account(),
            enable_trading=True,
        ),
        http_post_json=fake_post,
    )
    request = OrderRequest(
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        quantity=2,
        order_type=OrderType.LIMIT,
        price=110,
        reduce_only=True,
    )

    result = executor.submit_order(request)

    assert result.status == OrderStatus.ACCEPTED
    assert captured["body"]["side"] == "Sell"
    assert captured["body"]["orderType"] == "Limit"
    assert captured["body"]["timeInForce"] == "GTC"
    assert captured["body"]["price"] == "110"
    assert captured["body"]["reduceOnly"] is True


def test_bybit_error_returns_rejected_result() -> None:
    executor = BybitOrderExecutor(
        BybitOrderExecutorConfig(
            account=make_account(),
            enable_trading=True,
        ),
        http_post_json=lambda *_: {
            "retCode": 10001,
            "retMsg": "bad order",
            "result": {},
        },
    )

    result = executor.submit_order(
        OrderRequest(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            quantity=1,
        )
    )

    assert result.status == OrderStatus.REJECTED
    assert result.message == "bad order"


def test_rejects_reduce_only_with_stop_loss() -> None:
    executor = BybitOrderExecutor(
        BybitOrderExecutorConfig(
            account=make_account(),
            enable_trading=True,
        ),
        http_post_json=lambda *_: {},
    )

    with pytest.raises(
        ValueError,
        match="reduce_only",
    ):
        executor.submit_order(
            OrderRequest(
                symbol="ETHUSDT",
                side=OrderSide.SELL,
                quantity=1,
                stop_loss=95,
                reduce_only=True,
            )
        )


def test_mainnet_requires_explicit_allow_mainnet() -> None:
    account = make_account(testnet=False)

    assert account.base_url == BYBIT_MAINNET_API_URL

    with pytest.raises(
        ValueError,
        match="mainnet",
    ):
        BybitOrderExecutorConfig(
            account=account,
            enable_trading=True,
        )


def test_mainnet_can_be_explicitly_allowed() -> None:
    config = BybitOrderExecutorConfig(
        account=make_account(testnet=False),
        enable_trading=True,
        allow_mainnet=True,
    )

    assert config.allow_mainnet is True
