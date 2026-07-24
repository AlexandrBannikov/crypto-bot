import pytest

from app.bybit_account import (
    API_KEY_INFO_PATH,
    WALLET_BALANCE_PATH,
    BybitAPIError,
    BybitAccountClient,
    BybitAccountConfig,
)


def test_bybit_account_config_normalizes_credentials() -> None:
    config = BybitAccountConfig(
        api_key="  test-key  ",
        api_secret="  test-secret  ",
    )

    assert config.api_key == "test-key"
    assert config.api_secret == "test-secret"
    assert config.testnet is False
    assert config.recv_window == 5000
    assert config.timeout_seconds == 10.0
    assert config.base_url is None


@pytest.mark.parametrize(
    ("api_key", "api_secret"),
    [
        ("", "secret"),
        ("   ", "secret"),
        ("key", ""),
        ("key", "   "),
    ],
)
def test_bybit_account_config_rejects_empty_credentials(
    api_key: str,
    api_secret: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        BybitAccountConfig(
            api_key=api_key,
            api_secret=api_secret,
        )


def test_bybit_account_config_rejects_invalid_recv_window() -> None:
    with pytest.raises(
        ValueError,
        match="recv_window must be greater than zero",
    ):
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            recv_window=0,
        )


def test_bybit_account_config_rejects_invalid_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout_seconds must be greater than zero",
    ):
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            timeout_seconds=0,
        )


from decimal import Decimal

from app.bybit_account import WalletBalance


def test_wallet_balance_normalizes_coin_name() -> None:
    balance = WalletBalance(
        coin=" eth ",
        wallet_balance=Decimal("1.2500"),
        available_balance=Decimal("1.1000"),
    )

    assert balance.coin == "ETH"
    assert balance.wallet_balance == Decimal("1.2500")
    assert balance.available_balance == Decimal("1.1000")


def test_wallet_balance_rejects_empty_coin() -> None:
    with pytest.raises(ValueError, match="coin must not be empty"):
        WalletBalance(
            coin="   ",
            wallet_balance=Decimal("1"),
            available_balance=Decimal("1"),
        )


@pytest.mark.parametrize(
    ("wallet_balance", "available_balance"),
    [
        (Decimal("-1"), Decimal("0")),
        (Decimal("1"), Decimal("-0.1")),
    ],
)
def test_wallet_balance_rejects_negative_values(
    wallet_balance: Decimal,
    available_balance: Decimal,
) -> None:
    with pytest.raises(
        ValueError,
        match="balance must not be negative",
    ):
        WalletBalance(
            coin="ETH",
            wallet_balance=wallet_balance,
            available_balance=available_balance,
        )


def test_wallet_balance_rejects_available_above_wallet_balance() -> None:
    with pytest.raises(
        ValueError,
        match="available_balance must not exceed wallet_balance",
    ):
        WalletBalance(
            coin="USDT",
            wallet_balance=Decimal("100"),
            available_balance=Decimal("101"),
        )


def test_bybit_account_client_uses_testnet_base_url() -> None:
    client = BybitAccountClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            testnet=True,
        )
    )

    assert client.base_url == "https://api-testnet.bybit.com"


def test_bybit_account_client_uses_custom_base_url() -> None:
    client = BybitAccountClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            base_url="https://example.test/",
        )
    )

    assert client.base_url == "https://example.test"


def test_bybit_account_client_gets_wallet_balance() -> None:
    calls = []

    def fake_get_json(url, headers, timeout_seconds):
        calls.append((url, headers, timeout_seconds))
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "coin": [
                            {
                                "coin": "USDT",
                                "walletBalance": "15.50",
                                "availableToWithdraw": "12.25",
                            }
                        ]
                    }
                ]
            },
        }

    client = BybitAccountClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            base_url="https://example.test",
            timeout_seconds=3,
        ),
        http_get_json=fake_get_json,
        clock_ms=lambda: 1000,
    )

    balance = client.get_wallet_balance()

    assert balance.coin == "USDT"
    assert balance.wallet_balance == Decimal("15.50")
    assert balance.available_balance == Decimal("12.25")
    assert calls[0][0].startswith(
        f"https://example.test{WALLET_BALANCE_PATH}?"
    )
    assert calls[0][1]["X-BAPI-API-KEY"] == "key"
    assert "X-BAPI-SIGN" in calls[0][1]
    assert calls[0][2] == 3


def test_bybit_account_client_reports_missing_usdt() -> None:
    def fake_get_json(url, headers, timeout_seconds):
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "coin": [
                            {
                                "coin": "BTC",
                                "walletBalance": "1",
                            }
                        ]
                    }
                ]
            },
        }

    client = BybitAccountClient(
        BybitAccountConfig(api_key="key", api_secret="secret"),
        http_get_json=fake_get_json,
    )

    with pytest.raises(LookupError, match="USDT balance not found"):
        client.get_wallet_balance()


def test_bybit_account_client_rejects_unexpected_wallet_response() -> None:
    def fake_get_json(url, headers, timeout_seconds):
        return {"retCode": 0, "result": {"list": []}}

    client = BybitAccountClient(
        BybitAccountConfig(api_key="key", api_secret="secret"),
        http_get_json=fake_get_json,
    )

    with pytest.raises(
        ValueError,
        match="unexpected wallet balance response",
    ):
        client.get_wallet_balance()


def test_bybit_account_client_gets_api_key_info() -> None:
    calls = []

    def fake_get_json(url, headers, timeout_seconds):
        calls.append(url)
        return {
            "retCode": 0,
            "result": {
                "accountType": "UNIFIED",
                "readOnly": 0,
                "permissions": {
                    "Spot": ["SpotTrade"],
                    "Wallet": ["AccountTransfer"],
                },
            },
        }

    client = BybitAccountClient(
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            base_url="https://example.test",
        ),
        http_get_json=fake_get_json,
    )

    key_info = client.get_api_key_info()

    assert key_info.account_type == "UNIFIED"
    assert key_info.read_only is False
    assert key_info.permissions == {
        "Spot": ["SpotTrade"],
        "Wallet": ["AccountTransfer"],
    }
    assert calls == [f"https://example.test{API_KEY_INFO_PATH}"]


def test_bybit_account_client_raises_safe_api_error() -> None:
    def fake_get_json(url, headers, timeout_seconds):
        return {
            "retCode": 10004,
            "retMsg": "invalid sign",
        }

    client = BybitAccountClient(
        BybitAccountConfig(
            api_key="visible-key",
            api_secret="hidden-secret",
        ),
        http_get_json=fake_get_json,
    )

    with pytest.raises(BybitAPIError) as exc:
        client.get_api_key_info()

    assert exc.value.ret_code == 10004
    assert "hidden-secret" not in str(exc.value)


def test_wallet_balance_parses_empty_available_balance_as_zero() -> None:
    def fake_get_json(url, headers, timeout_seconds):
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "coin": [
                            {
                                "coin": "USDT",
                                "walletBalance": "0",
                                "availableToWithdraw": "",
                            }
                        ]
                    }
                ]
            },
        }

    client = BybitAccountClient(
        BybitAccountConfig(
            api_key="test-key",
            api_secret="test-secret",
            testnet=False,
        ),
        http_get_json=fake_get_json,
        clock_ms=lambda: 1000,
    )

    balance = client.get_wallet_balance()

    assert balance.wallet_balance == Decimal("0")
    assert balance.available_balance == Decimal("0")
