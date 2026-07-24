import hashlib
import hmac
from urllib.parse import urlencode

import pytest

from app.bybit_account import (
    BYBIT_TESTNET_API_URL,
    POSITION_LIST_PATH,
    WALLET_BALANCE_PATH,
    BybitAccountClient,
    BybitAccountConfig,
)
from app.trading_types import PositionSide


def make_config() -> BybitAccountConfig:
    return BybitAccountConfig(
        api_key="test-key",
        api_secret="test-secret",
        recv_window=5000,
        timeout_seconds=3,
    )


def test_config_defaults_to_testnet() -> None:
    config = make_config()

    assert config.base_url == BYBIT_TESTNET_API_URL


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("api_key", ""),
        ("api_secret", ""),
        ("recv_window", 0),
        ("timeout_seconds", 0),
        ("base_url", ""),
    ],
)
def test_rejects_invalid_config(
    field: str,
    value,
) -> None:
    kwargs = {
        "api_key": "key",
        "api_secret": "secret",
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        BybitAccountConfig(**kwargs)


def test_wallet_balance_uses_signed_request() -> None:
    captured = {}

    def fake_http_get_json(
        url,
        params,
        headers,
        timeout_seconds,
    ):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout_seconds

        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "accountType": "UNIFIED",
                        "totalEquity": "1000.5",
                        "totalWalletBalance": "900.25",
                        "totalAvailableBalance": "800",
                        "coin": [
                            {
                                "coin": "USDT",
                                "walletBalance": "900.25",
                                "availableToWithdraw": "",
                                "usdValue": "900.25",
                            }
                        ],
                    }
                ]
            },
        }

    client = BybitAccountClient(
        make_config(),
        http_get_json=fake_http_get_json,
        clock_ms=lambda: 1234567890,
    )

    balance = client.get_wallet_balance(
        account_type="unified",
        coin="usdt",
    )

    query_string = urlencode(
        {
            "accountType": "UNIFIED",
            "coin": "USDT",
        }
    )
    expected_signature = hmac.new(
        b"test-secret",
        (
            "1234567890"
            "test-key"
            "5000"
            + query_string
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert captured["url"].endswith(
        WALLET_BALANCE_PATH
    )
    assert captured["params"] == {
        "accountType": "UNIFIED",
        "coin": "USDT",
    }
    assert captured["headers"]["X-BAPI-SIGN"] == (
        expected_signature
    )
    assert captured["headers"]["X-BAPI-API-KEY"] == "test-key"
    assert captured["headers"]["X-BAPI-TIMESTAMP"] == "1234567890"
    assert captured["headers"]["X-BAPI-RECV-WINDOW"] == "5000"
    assert captured["timeout"] == 3
    assert balance.account_type == "UNIFIED"
    assert balance.total_equity == pytest.approx(1000.5)
    assert balance.total_wallet_balance == pytest.approx(900.25)
    assert balance.total_available_balance == pytest.approx(800)
    assert balance.coins[0].coin == "USDT"
    assert balance.coins[0].wallet_balance == pytest.approx(900.25)
    assert balance.coins[0].available_to_withdraw is None


def test_positions_request_and_parse_open_positions() -> None:
    captured = {}

    def fake_http_get_json(
        url,
        params,
        headers,
        timeout_seconds,
    ):
        captured["url"] = url
        captured["params"] = params

        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": "ETHUSDT",
                        "side": "Buy",
                        "size": "0.5",
                        "avgPrice": "2500",
                        "unrealisedPnl": "12.3",
                        "leverage": "1",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "side": "Sell",
                        "size": "0",
                        "avgPrice": "",
                    },
                ]
            },
        }

    client = BybitAccountClient(
        make_config(),
        http_get_json=fake_http_get_json,
        clock_ms=lambda: 1,
    )

    positions = client.get_positions(
        category="linear",
        symbol="ethusdt",
    )

    assert captured["url"].endswith(
        POSITION_LIST_PATH
    )
    assert captured["params"] == {
        "category": "linear",
        "symbol": "ETHUSDT",
    }
    assert len(positions) == 1
    assert positions[0].symbol == "ETHUSDT"
    assert positions[0].side == PositionSide.LONG
    assert positions[0].size == pytest.approx(0.5)
    assert positions[0].average_price == pytest.approx(2500)
    assert positions[0].unrealised_pnl == pytest.approx(12.3)
    assert positions[0].leverage == pytest.approx(1)


def test_positions_support_settle_coin() -> None:
    def fake_http_get_json(
        url,
        params,
        headers,
        timeout_seconds,
    ):
        assert params == {
            "category": "linear",
            "settleCoin": "USDT",
        }

        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"list": []},
        }

    client = BybitAccountClient(
        make_config(),
        http_get_json=fake_http_get_json,
    )

    assert (
        client.get_positions(
            category="linear",
            settle_coin="usdt",
        )
        == ()
    )


def test_rejects_linear_positions_without_symbol_or_settle_coin() -> None:
    client = BybitAccountClient(make_config())

    with pytest.raises(
        ValueError,
        match="symbol or settle_coin",
    ):
        client.get_positions(category="linear")


def test_rejects_bybit_error() -> None:
    client = BybitAccountClient(
        make_config(),
        http_get_json=lambda *_: {
            "retCode": 10001,
            "retMsg": "bad request",
            "result": {},
        },
    )

    with pytest.raises(
        RuntimeError,
        match="bad request",
    ):
        client.get_wallet_balance()


def test_rejects_invalid_wallet_payload() -> None:
    client = BybitAccountClient(
        make_config(),
        http_get_json=lambda *_: {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"list": []},
        },
    )

    with pytest.raises(ValueError, match="wallet"):
        client.get_wallet_balance()


def test_rejects_invalid_position_side() -> None:
    client = BybitAccountClient(
        make_config(),
        http_get_json=lambda *_: {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": "ETHUSDT",
                        "side": "None",
                        "size": "1",
                    }
                ]
            },
        },
    )

    with pytest.raises(
        ValueError,
        match="position side",
    ):
        client.get_positions(
            category="linear",
            symbol="ETHUSDT",
        )
