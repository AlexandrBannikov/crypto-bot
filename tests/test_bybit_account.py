import pytest

from app.bybit_account import BybitAccountConfig


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
