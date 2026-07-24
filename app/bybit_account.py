from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.trading_types import PositionSide


BYBIT_MAINNET_API_URL = "https://api.bybit.com"
BYBIT_TESTNET_API_URL = "https://api-testnet.bybit.com"
WALLET_BALANCE_PATH = "/v5/account/wallet-balance"
POSITION_LIST_PATH = "/v5/position/list"

SUPPORTED_ACCOUNT_TYPES = {
    "UNIFIED",
    "CONTRACT",
    "SPOT",
}

SUPPORTED_POSITION_CATEGORIES = {
    "linear",
    "inverse",
    "option",
}


JsonObject = dict[str, Any]
HttpGetJson = Callable[
    [
        str,
        dict[str, str | int],
        dict[str, str],
        float,
    ],
    JsonObject,
]
ClockMilliseconds = Callable[[], int]


@dataclass(frozen=True, slots=True)
class BybitAccountConfig:
    api_key: str
    api_secret: str
    testnet: bool = True
    recv_window: int = 5000
    timeout_seconds: float = 10.0
    base_url: str | None = None

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("api_key must not be empty")

        if not self.api_secret.strip():
            raise ValueError(
                "api_secret must not be empty"
            )

        if self.recv_window <= 0:
            raise ValueError(
                "recv_window must be greater than zero"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
            )

        if self.base_url is not None:
            if not self.base_url.strip():
                raise ValueError(
                    "base_url must not be empty"
                )
            return

        object.__setattr__(
            self,
            "base_url",
            (
                BYBIT_TESTNET_API_URL
                if self.testnet
                else BYBIT_MAINNET_API_URL
            ),
        )


@dataclass(frozen=True, slots=True)
class WalletCoinBalance:
    coin: str
    wallet_balance: float
    available_to_withdraw: float | None = None
    usd_value: float | None = None


@dataclass(frozen=True, slots=True)
class WalletBalance:
    account_type: str
    total_equity: float | None
    total_wallet_balance: float | None
    total_available_balance: float | None
    coins: tuple[WalletCoinBalance, ...]


@dataclass(frozen=True, slots=True)
class BybitPosition:
    symbol: str
    side: PositionSide
    size: float
    average_price: float | None
    unrealised_pnl: float | None = None
    leverage: float | None = None


class BybitAccountClient:
    def __init__(
        self,
        config: BybitAccountConfig,
        *,
        http_get_json: HttpGetJson | None = None,
        clock_ms: ClockMilliseconds | None = None,
    ) -> None:
        self.config = config
        self._http_get_json = (
            http_get_json
            or self._default_http_get_json
        )
        self._clock_ms = (
            clock_ms
            or self._default_clock_ms
        )

    def get_wallet_balance(
        self,
        *,
        account_type: str = "UNIFIED",
        coin: str | None = None,
    ) -> WalletBalance:
        normalized_account_type = (
            account_type.strip().upper()
        )

        if (
            normalized_account_type
            not in SUPPORTED_ACCOUNT_TYPES
        ):
            raise ValueError(
                "unsupported account type"
            )

        params: dict[str, str | int] = {
            "accountType": normalized_account_type,
        }

        if coin is not None:
            normalized_coin = coin.strip().upper()

            if not normalized_coin:
                raise ValueError(
                    "coin must not be empty"
                )

            params["coin"] = normalized_coin

        payload = self._signed_get(
            WALLET_BALANCE_PATH,
            params,
        )

        return self._parse_wallet_balance(payload)

    def get_positions(
        self,
        *,
        category: str,
        symbol: str | None = None,
        settle_coin: str | None = None,
    ) -> tuple[BybitPosition, ...]:
        if category not in SUPPORTED_POSITION_CATEGORIES:
            raise ValueError(
                "unsupported position category"
            )

        params: dict[str, str | int] = {
            "category": category,
        }

        if symbol is not None:
            normalized_symbol = (
                symbol.strip().upper()
            )

            if not normalized_symbol:
                raise ValueError(
                    "symbol must not be empty"
                )

            params["symbol"] = normalized_symbol

        if settle_coin is not None:
            normalized_settle_coin = (
                settle_coin.strip().upper()
            )

            if not normalized_settle_coin:
                raise ValueError(
                    "settle_coin must not be empty"
                )

            params["settleCoin"] = (
                normalized_settle_coin
            )

        if (
            category in {"linear", "inverse"}
            and "symbol" not in params
            and "settleCoin" not in params
        ):
            raise ValueError(
                "symbol or settle_coin is required "
                "for linear and inverse positions"
            )

        payload = self._signed_get(
            POSITION_LIST_PATH,
            params,
        )

        return self._parse_positions(payload)

    def _signed_get(
        self,
        path: str,
        params: dict[str, str | int],
    ) -> JsonObject:
        timestamp = str(self._clock_ms())
        recv_window = str(self.config.recv_window)
        query_string = urlencode(params)

        signature = self._sign_get(
            timestamp=timestamp,
            query_string=query_string,
        )

        headers = {
            "X-BAPI-API-KEY": self.config.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": signature,
            "Content-Type": "application/json",
        }

        assert self.config.base_url is not None

        payload = self._http_get_json(
            self.config.base_url + path,
            params,
            headers,
            self.config.timeout_seconds,
        )

        ret_code = payload.get("retCode")

        if ret_code != 0:
            message = payload.get(
                "retMsg",
                "unknown Bybit error",
            )

            raise RuntimeError(
                f"Bybit API error {ret_code}: {message}"
            )

        return payload

    def _sign_get(
        self,
        *,
        timestamp: str,
        query_string: str,
    ) -> str:
        payload = (
            timestamp
            + self.config.api_key
            + str(self.config.recv_window)
            + query_string
        )

        return hmac.new(
            self.config.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _parse_wallet_balance(
        payload: JsonObject,
    ) -> WalletBalance:
        result = payload.get("result")

        if not isinstance(result, dict):
            raise ValueError(
                "Bybit response has no result object"
            )

        accounts = result.get("list")

        if not isinstance(accounts, list) or not accounts:
            raise ValueError(
                "Bybit response has no wallet balance list"
            )

        account = accounts[0]

        if not isinstance(account, dict):
            raise ValueError(
                "invalid wallet balance account"
            )

        coins_payload = account.get("coin", [])

        if not isinstance(coins_payload, list):
            raise ValueError(
                "invalid wallet balance coin list"
            )

        coins = tuple(
            BybitAccountClient._parse_coin_balance(
                coin_payload
            )
            for coin_payload in coins_payload
        )

        return WalletBalance(
            account_type=str(
                account.get("accountType", "")
            ),
            total_equity=_optional_float(
                account.get("totalEquity")
            ),
            total_wallet_balance=_optional_float(
                account.get("totalWalletBalance")
            ),
            total_available_balance=_optional_float(
                account.get("totalAvailableBalance")
            ),
            coins=coins,
        )

    @staticmethod
    def _parse_coin_balance(
        payload: Any,
    ) -> WalletCoinBalance:
        if not isinstance(payload, dict):
            raise ValueError(
                "invalid wallet coin balance"
            )

        coin = str(payload.get("coin", "")).upper()

        if not coin:
            raise ValueError(
                "wallet coin balance has no coin"
            )

        return WalletCoinBalance(
            coin=coin,
            wallet_balance=_required_float(
                payload.get("walletBalance"),
                "walletBalance",
            ),
            available_to_withdraw=_optional_float(
                payload.get("availableToWithdraw")
            ),
            usd_value=_optional_float(
                payload.get("usdValue")
            ),
        )

    @staticmethod
    def _parse_positions(
        payload: JsonObject,
    ) -> tuple[BybitPosition, ...]:
        result = payload.get("result")

        if not isinstance(result, dict):
            raise ValueError(
                "Bybit response has no result object"
            )

        rows = result.get("list")

        if not isinstance(rows, list):
            raise ValueError(
                "Bybit response has no position list"
            )

        positions: list[BybitPosition] = []

        for row in rows:
            position = (
                BybitAccountClient
                ._parse_position(row)
            )

            if position is not None:
                positions.append(position)

        return tuple(positions)

    @staticmethod
    def _parse_position(
        payload: Any,
    ) -> BybitPosition | None:
        if not isinstance(payload, dict):
            raise ValueError(
                "invalid position row"
            )

        size = _required_float(
            payload.get("size"),
            "size",
        )

        if size == 0:
            return None

        side_value = str(payload.get("side", ""))

        if side_value == "Buy":
            side = PositionSide.LONG
        elif side_value == "Sell":
            side = PositionSide.SHORT
        else:
            raise ValueError(
                "unsupported position side"
            )

        symbol = str(payload.get("symbol", "")).upper()

        if not symbol:
            raise ValueError(
                "position has no symbol"
            )

        return BybitPosition(
            symbol=symbol,
            side=side,
            size=size,
            average_price=_optional_float(
                payload.get("avgPrice")
            ),
            unrealised_pnl=_optional_float(
                payload.get("unrealisedPnl")
            ),
            leverage=_optional_float(
                payload.get("leverage")
            ),
        )

    @staticmethod
    def _default_http_get_json(
        url: str,
        params: dict[str, str | int],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> JsonObject:
        query_string = urlencode(params)
        request_url = (
            url
            if not query_string
            else f"{url}?{query_string}"
        )

        request = Request(
            request_url,
            headers=headers,
            method="GET",
        )

        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            body = response.read().decode("utf-8")

        payload = json.loads(body)

        if not isinstance(payload, dict):
            raise ValueError(
                "Bybit response must be a JSON object"
            )

        return payload

    @staticmethod
    def _default_clock_ms() -> int:
        return int(time.time() * 1000)


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None

    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "invalid numeric Bybit value"
        ) from error


def _required_float(
    value: Any,
    field_name: str,
) -> float:
    parsed = _optional_float(value)

    if parsed is None:
        raise ValueError(
            f"missing numeric Bybit value: {field_name}"
        )

    return parsed
