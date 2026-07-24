from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import hmac
import json
import time
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BYBIT_MAINNET_API_URL = "https://api.bybit.com"
BYBIT_TESTNET_API_URL = "https://api-testnet.bybit.com"
WALLET_BALANCE_PATH = "/v5/account/wallet-balance"
API_KEY_INFO_PATH = "/v5/user/query-api"


@dataclass(frozen=True, slots=True)
class BybitAccountConfig:
    api_key: str
    api_secret: str
    testnet: bool = False
    recv_window: int = 5000
    timeout_seconds: float = 10.0
    base_url: str | None = None

    def __post_init__(self) -> None:
        api_key = self.api_key.strip()
        api_secret = self.api_secret.strip()

        if not api_key:
            raise ValueError("api_key must not be empty")

        if not api_secret:
            raise ValueError("api_secret must not be empty")

        if self.recv_window <= 0:
            raise ValueError(
                "recv_window must be greater than zero"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
            )

        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "api_secret", api_secret)


@dataclass(frozen=True, slots=True)
class WalletBalance:
    coin: str
    wallet_balance: Decimal
    available_balance: Decimal

    def __post_init__(self) -> None:
        coin = self.coin.strip().upper()

        if not coin:
            raise ValueError("coin must not be empty")

        if self.wallet_balance < 0 or self.available_balance < 0:
            raise ValueError("balance must not be negative")

        if self.available_balance > self.wallet_balance:
            raise ValueError(
                "available_balance must not exceed wallet_balance"
            )

        object.__setattr__(self, "coin", coin)


@dataclass(frozen=True, slots=True)
class BybitApiKeyInfo:
    account_type: str | None
    read_only: bool
    permissions: dict[str, list[str]]


class BybitAPIError(RuntimeError):
    def __init__(
        self,
        ret_code: int | None,
        ret_msg: str,
    ) -> None:
        super().__init__(ret_msg)
        self.ret_code = ret_code
        self.ret_msg = ret_msg


HttpGetJSON = Callable[
    [str, dict[str, str], float],
    dict[str, Any],
]
ClockMS = Callable[[], int]


class BybitAccountClient:
    def __init__(
        self,
        config: BybitAccountConfig,
        *,
        http_get_json: HttpGetJSON | None = None,
        clock_ms: ClockMS | None = None,
    ) -> None:
        self.config = config
        self._http_get_json = (
            http_get_json or self._default_http_get_json
        )
        self._clock_ms = clock_ms or (
            lambda: int(time.time() * 1000)
        )

    @property
    def base_url(self) -> str:
        if self.config.base_url is not None:
            return self.config.base_url.rstrip("/")

        if self.config.testnet:
            return BYBIT_TESTNET_API_URL

        return BYBIT_MAINNET_API_URL

    def get_wallet_balance(
        self,
        *,
        account_type: str = "UNIFIED",
        coin: str = "USDT",
    ) -> WalletBalance:
        payload = self._signed_get(
            WALLET_BALANCE_PATH,
            {
                "accountType": account_type,
                "coin": coin.upper(),
            },
        )
        result = payload.get("result")

        if not isinstance(result, dict):
            raise ValueError("unexpected wallet balance response")

        accounts = result.get("list")

        if not isinstance(accounts, list) or not accounts:
            raise ValueError("unexpected wallet balance response")

        coins = accounts[0].get("coin")

        if not isinstance(coins, list):
            raise ValueError("unexpected wallet balance response")

        for coin_payload in coins:
            if not isinstance(coin_payload, dict):
                raise ValueError("unexpected wallet balance response")

            if coin_payload.get("coin") != coin.upper():
                continue

            return WalletBalance(
                coin=coin,
                wallet_balance=Decimal(
                    str(coin_payload.get("walletBalance", "0"))
                ),
                available_balance=Decimal(
                    str(
                        coin_payload.get(
                            "availableToWithdraw",
                            coin_payload.get(
                                "availableBalance",
                                coin_payload.get("walletBalance", "0"),
                            ),
                        )
                    )
                ),
            )

        raise LookupError(f"{coin.upper()} balance not found")

    def get_api_key_info(self) -> BybitApiKeyInfo:
        payload = self._signed_get(API_KEY_INFO_PATH, {})
        result = payload.get("result")

        if not isinstance(result, dict):
            raise ValueError("unexpected api key response")

        raw_permissions = result.get("permissions", {})

        if not isinstance(raw_permissions, dict):
            raise ValueError("unexpected api key response")

        permissions: dict[str, list[str]] = {}

        for key, value in raw_permissions.items():
            if isinstance(value, list):
                permissions[str(key)] = [str(item) for item in value]

        read_only_raw = result.get("readOnly")
        read_only = str(read_only_raw).lower() in {"1", "true", "yes"}

        account_type_raw = result.get("accountType")
        account_type = (
            str(account_type_raw)
            if account_type_raw is not None
            else None
        )

        return BybitApiKeyInfo(
            account_type=account_type,
            read_only=read_only,
            permissions=permissions,
        )

    def _signed_get(
        self,
        path: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        timestamp = str(self._clock_ms())
        recv_window = str(self.config.recv_window)
        query = urlencode(sorted(params.items()))
        signature = self._sign_get(timestamp, recv_window, query)

        headers = {
            "X-BAPI-API-KEY": self.config.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        }

        url = f"{self.base_url}{path}"

        if query:
            url = f"{url}?{query}"

        payload = self._http_get_json(
            url,
            headers,
            self.config.timeout_seconds,
        )
        ret_code = payload.get("retCode")

        if ret_code != 0:
            raise BybitAPIError(
                ret_code=(
                    int(ret_code)
                    if isinstance(ret_code, int | str)
                    and str(ret_code).lstrip("-").isdigit()
                    else None
                ),
                ret_msg=str(payload.get("retMsg", "Bybit API error")),
            )

        return payload

    def _sign_get(
        self,
        timestamp: str,
        recv_window: str,
        query: str,
    ) -> str:
        payload = (
            f"{timestamp}{self.config.api_key}{recv_window}{query}"
        )

        return hmac.new(
            self.config.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            sha256,
        ).hexdigest()

    @staticmethod
    def _default_http_get_json(
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        request = Request(
            url,
            headers=headers,
            method="GET",
        )

        with urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")

        payload = json.loads(raw_body)

        if not isinstance(payload, dict):
            raise ValueError("unexpected Bybit response")

        return payload
