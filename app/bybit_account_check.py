from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import socket
from urllib.error import URLError

from app.bybit_account import (
    BYBIT_TESTNET_API_URL,
    BybitAPIError,
    BybitAccountClient,
)


class AccountCheckStatus(str, Enum):
    OK = "OK"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    API_ERROR = "API_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    MISSING_USDT = "MISSING_USDT"
    EMPTY_BALANCE = "EMPTY_BALANCE"
    UNEXPECTED_RESPONSE = "UNEXPECTED_RESPONSE"


@dataclass(frozen=True, slots=True)
class BybitAccountCheckResult:
    status: AccountCheckStatus
    environment: str
    api_key_valid: bool
    api_secret_valid: bool
    account_type: str | None
    usdt_wallet_balance: Decimal | None
    usdt_available_balance: Decimal | None
    usdt_balance_empty: bool
    read_only: bool | None
    trading_operations_allowed: bool
    safe_message: str

    @property
    def ok(self) -> bool:
        return self.status is AccountCheckStatus.OK


class BybitAccountChecker:
    _INVALID_CREDENTIAL_CODES = {
        10003,
        10004,
        10005,
        10007,
        33004,
    }

    def __init__(self, client: BybitAccountClient) -> None:
        self.client = client

    def check(self) -> BybitAccountCheckResult:
        environment = self._detect_environment()

        try:
            key_info = self.client.get_api_key_info()
            balance = self.client.get_wallet_balance(
                account_type="UNIFIED",
                coin="USDT",
            )
        except BybitAPIError as exc:
            if exc.ret_code in self._INVALID_CREDENTIAL_CODES:
                return self._result(
                    status=AccountCheckStatus.INVALID_CREDENTIALS,
                    environment=environment,
                    safe_message="Bybit API credentials are invalid.",
                )

            return self._result(
                status=AccountCheckStatus.API_ERROR,
                environment=environment,
                safe_message="Bybit returned an account check error.",
            )
        except LookupError:
            return self._result(
                status=AccountCheckStatus.MISSING_USDT,
                environment=environment,
                api_key_valid=True,
                api_secret_valid=True,
                safe_message="USDT balance is missing from Bybit response.",
            )
        except (TimeoutError, socket.timeout):
            return self._result(
                status=AccountCheckStatus.TIMEOUT,
                environment=environment,
                safe_message="Bybit account check timed out.",
            )
        except URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                return self._result(
                    status=AccountCheckStatus.TIMEOUT,
                    environment=environment,
                    safe_message="Bybit account check timed out.",
                )

            return self._result(
                status=AccountCheckStatus.NETWORK_ERROR,
                environment=environment,
                safe_message="Network error during Bybit account check.",
            )
        except (KeyError, TypeError, ValueError):
            return self._result(
                status=AccountCheckStatus.UNEXPECTED_RESPONSE,
                environment=environment,
                safe_message="Bybit returned an unexpected response.",
            )

        trading_allowed = self._trading_allowed(
            read_only=key_info.read_only,
            permissions=key_info.permissions,
        )
        balance_empty = (
            balance.wallet_balance <= Decimal("0")
            and balance.available_balance <= Decimal("0")
        )

        if balance_empty:
            status = AccountCheckStatus.EMPTY_BALANCE
            message = "USDT balance is empty."
        else:
            status = AccountCheckStatus.OK
            message = "Bybit account check completed."

        return BybitAccountCheckResult(
            status=status,
            environment=environment,
            api_key_valid=True,
            api_secret_valid=True,
            account_type=key_info.account_type,
            usdt_wallet_balance=balance.wallet_balance,
            usdt_available_balance=balance.available_balance,
            usdt_balance_empty=balance_empty,
            read_only=key_info.read_only,
            trading_operations_allowed=trading_allowed,
            safe_message=message,
        )

    def _detect_environment(self) -> str:
        base_url = self.client.base_url.lower()

        if self.client.config.testnet or BYBIT_TESTNET_API_URL in base_url:
            return "testnet"

        return "mainnet"

    @staticmethod
    def _trading_allowed(
        *,
        read_only: bool,
        permissions: dict[str, list[str]],
    ) -> bool:
        if read_only:
            return False

        trading_permissions = {
            "Order",
            "Position",
            "Trade",
            "SpotTrade",
            "ContractTrade",
            "DerivativesTrade",
        }

        for values in permissions.values():
            if trading_permissions.intersection(values):
                return True

        return False

    @staticmethod
    def _result(
        *,
        status: AccountCheckStatus,
        environment: str,
        safe_message: str,
        api_key_valid: bool = False,
        api_secret_valid: bool = False,
    ) -> BybitAccountCheckResult:
        return BybitAccountCheckResult(
            status=status,
            environment=environment,
            api_key_valid=api_key_valid,
            api_secret_valid=api_secret_valid,
            account_type=None,
            usdt_wallet_balance=None,
            usdt_available_balance=None,
            usdt_balance_empty=False,
            read_only=None,
            trading_operations_allowed=False,
            safe_message=safe_message,
        )
