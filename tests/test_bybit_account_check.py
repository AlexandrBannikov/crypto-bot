from decimal import Decimal
import socket
from urllib.error import URLError

from app.bybit_account import (
    BybitAPIError,
    BybitAccountClient,
    BybitAccountConfig,
    BybitApiKeyInfo,
    WalletBalance,
)
from app.bybit_account_check import (
    AccountCheckStatus,
    BybitAccountChecker,
)


class FakeClient(BybitAccountClient):
    def __init__(
        self,
        *,
        key_info=None,
        balance=None,
        error=None,
        testnet=False,
        base_url=None,
    ) -> None:
        super().__init__(
            BybitAccountConfig(
                api_key="api-key",
                api_secret="api-secret",
                testnet=testnet,
                base_url=base_url,
            )
        )
        self.key_info = key_info
        self.balance = balance
        self.error = error

    def get_api_key_info(self):
        if self.error is not None:
            raise self.error

        return self.key_info

    def get_wallet_balance(self, *, account_type="UNIFIED", coin="USDT"):
        if self.error is not None:
            raise self.error

        return self.balance


def make_key_info(*, read_only=False):
    return BybitApiKeyInfo(
        account_type="UNIFIED",
        read_only=read_only,
        permissions={"Spot": ["SpotTrade"]},
    )


def make_balance(wallet="25.5", available="20"):
    return WalletBalance(
        coin="USDT",
        wallet_balance=Decimal(wallet),
        available_balance=Decimal(available),
    )


def test_account_checker_returns_ok_result() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            key_info=make_key_info(),
            balance=make_balance(),
            testnet=True,
        )
    )

    result = checker.check()

    assert result.ok is True
    assert result.status is AccountCheckStatus.OK
    assert result.environment == "testnet"
    assert result.api_key_valid is True
    assert result.api_secret_valid is True
    assert result.account_type == "UNIFIED"
    assert result.usdt_wallet_balance == Decimal("25.5")
    assert result.usdt_available_balance == Decimal("20")
    assert result.usdt_balance_empty is False
    assert result.read_only is False
    assert result.trading_operations_allowed is True


def test_account_checker_disables_trading_for_read_only_key() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            key_info=make_key_info(read_only=True),
            balance=make_balance(),
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.OK
    assert result.read_only is True
    assert result.trading_operations_allowed is False


def test_account_checker_detects_empty_balance() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            key_info=make_key_info(),
            balance=make_balance(wallet="0", available="0"),
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.EMPTY_BALANCE
    assert result.api_key_valid is True
    assert result.api_secret_valid is True
    assert result.usdt_balance_empty is True


def test_account_checker_detects_missing_usdt() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            error=LookupError("USDT balance not found"),
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.MISSING_USDT
    assert result.api_key_valid is True
    assert result.api_secret_valid is True
    assert result.safe_message == (
        "USDT balance is missing from Bybit response."
    )


def test_account_checker_detects_invalid_credentials() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            error=BybitAPIError(
                ret_code=10004,
                ret_msg="invalid sign",
            )
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.INVALID_CREDENTIALS
    assert result.api_key_valid is False
    assert result.api_secret_valid is False
    assert "api-secret" not in result.safe_message


def test_account_checker_detects_generic_api_error() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            error=BybitAPIError(
                ret_code=110001,
                ret_msg="safe upstream message",
            )
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.API_ERROR
    assert result.trading_operations_allowed is False


def test_account_checker_detects_timeout() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            error=TimeoutError("timed out"),
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.TIMEOUT


def test_account_checker_detects_url_timeout() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            error=URLError(socket.timeout("timed out")),
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.TIMEOUT


def test_account_checker_detects_network_error() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            error=URLError("network unavailable"),
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.NETWORK_ERROR


def test_account_checker_detects_unexpected_response() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            error=ValueError("unexpected response with no secret"),
        )
    )

    result = checker.check()

    assert result.status is AccountCheckStatus.UNEXPECTED_RESPONSE


def test_account_checker_detects_mainnet_from_custom_url() -> None:
    checker = BybitAccountChecker(
        FakeClient(
            key_info=make_key_info(),
            balance=make_balance(),
            base_url="https://api.bybit.com",
        )
    )

    result = checker.check()

    assert result.environment == "mainnet"
