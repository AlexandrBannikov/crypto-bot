from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.request import Request, urlopen

from app.bybit_account import (
    BYBIT_MAINNET_API_URL,
    BYBIT_TESTNET_API_URL,
    BybitAccountConfig,
)
from app.order_executor import (
    DirectOrderExecutor,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
)


ORDER_CREATE_PATH = "/v5/order/create"

SUPPORTED_ORDER_CATEGORIES = {
    "linear",
    "inverse",
    "spot",
    "option",
}


JsonObject = dict[str, Any]
HttpPostJson = Callable[
    [
        str,
        dict[str, Any],
        dict[str, str],
        float,
    ],
    JsonObject,
]
ClockMilliseconds = Callable[[], int]


@dataclass(frozen=True, slots=True)
class BybitOrderExecutorConfig:
    account: BybitAccountConfig
    category: str = "linear"
    position_idx: int = 0
    time_in_force: str = "GTC"
    enable_trading: bool = False
    allow_mainnet: bool = False

    def __post_init__(self) -> None:
        if self.category not in SUPPORTED_ORDER_CATEGORIES:
            raise ValueError(
                "unsupported order category"
            )

        if self.position_idx not in {0, 1, 2}:
            raise ValueError(
                "position_idx must be 0, 1 or 2"
            )

        if not self.time_in_force.strip():
            raise ValueError(
                "time_in_force must not be empty"
            )

        if (
            self.account.base_url == BYBIT_MAINNET_API_URL
            and not self.allow_mainnet
        ):
            raise ValueError(
                "mainnet order execution requires "
                "allow_mainnet=True"
            )


class BybitOrderExecutor(DirectOrderExecutor):
    def __init__(
        self,
        config: BybitOrderExecutorConfig,
        *,
        http_post_json: HttpPostJson | None = None,
        clock_ms: ClockMilliseconds | None = None,
    ) -> None:
        self.config = config
        self._http_post_json = (
            http_post_json
            or self._default_http_post_json
        )
        self._clock_ms = (
            clock_ms
            or self._default_clock_ms
        )

    def submit_order(
        self,
        request: OrderRequest,
    ) -> OrderResult:
        if not self.config.enable_trading:
            return OrderResult(
                request=request,
                status=OrderStatus.REJECTED,
                message=(
                    "Bybit trading is disabled; "
                    "set enable_trading=True to submit"
                ),
            )

        body = self._build_order_body(request)
        headers = self._build_headers(body)

        assert self.config.account.base_url is not None

        payload = self._http_post_json(
            self.config.account.base_url
            + ORDER_CREATE_PATH,
            body,
            headers,
            self.config.account.timeout_seconds,
        )

        ret_code = payload.get("retCode")

        if ret_code != 0:
            return OrderResult(
                request=request,
                status=OrderStatus.REJECTED,
                message=str(
                    payload.get(
                        "retMsg",
                        "unknown Bybit error",
                    )
                ),
            )

        result = payload.get("result")

        if not isinstance(result, dict):
            return OrderResult(
                request=request,
                status=OrderStatus.REJECTED,
                message=(
                    "Bybit response has no result object"
                ),
            )

        order_id = result.get("orderId")

        if not order_id:
            return OrderResult(
                request=request,
                status=OrderStatus.REJECTED,
                message=(
                    "Bybit response has no orderId"
                ),
            )

        return OrderResult(
            request=request,
            status=OrderStatus.ACCEPTED,
            order_id=str(order_id),
            message=str(
                payload.get("retMsg", "OK")
            ),
        )

    def _build_order_body(
        self,
        request: OrderRequest,
    ) -> dict[str, Any]:
        if (
            request.reduce_only
            and request.stop_loss is not None
        ):
            raise ValueError(
                "reduce_only orders cannot include stop_loss"
            )

        body: dict[str, Any] = {
            "category": self.config.category,
            "symbol": request.symbol,
            "side": _bybit_side(request.side),
            "orderType": _bybit_order_type(
                request.order_type
            ),
            "qty": _format_decimal(
                request.quantity
            ),
            "timeInForce": (
                "IOC"
                if request.order_type
                == OrderType.MARKET
                else self.config.time_in_force
            ),
        }

        if self.config.category in {
            "linear",
            "inverse",
        }:
            body["positionIdx"] = (
                self.config.position_idx
            )
            body["reduceOnly"] = (
                request.reduce_only
            )

        if request.price is not None:
            body["price"] = _format_decimal(
                request.price
            )

        if request.stop_loss is not None:
            body["stopLoss"] = _format_decimal(
                request.stop_loss
            )

        return body

    def _build_headers(
        self,
        body: dict[str, Any],
    ) -> dict[str, str]:
        timestamp = str(self._clock_ms())
        recv_window = str(
            self.config.account.recv_window
        )
        body_string = _json_body(body)

        payload = (
            timestamp
            + self.config.account.api_key
            + recv_window
            + body_string
        )

        signature = hmac.new(
            self.config.account.api_secret.encode(
                "utf-8"
            ),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-BAPI-API-KEY": (
                self.config.account.api_key
            ),
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": signature,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _default_http_post_json(
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> JsonObject:
        request = Request(
            url,
            data=_json_body(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            response_body = (
                response.read().decode("utf-8")
            )

        payload = json.loads(response_body)

        if not isinstance(payload, dict):
            raise ValueError(
                "Bybit response must be a JSON object"
            )

        return payload

    @staticmethod
    def _default_clock_ms() -> int:
        return int(time.time() * 1000)


def _bybit_side(side: OrderSide) -> str:
    if side == OrderSide.BUY:
        return "Buy"

    if side == OrderSide.SELL:
        return "Sell"

    raise ValueError("unsupported order side")


def _bybit_order_type(order_type: OrderType) -> str:
    if order_type == OrderType.MARKET:
        return "Market"

    if order_type == OrderType.LIMIT:
        return "Limit"

    raise ValueError("unsupported order type")


def _format_decimal(value: float) -> str:
    return format(value, "f").rstrip("0").rstrip(".")


def _json_body(body: dict[str, Any]) -> str:
    return json.dumps(
        body,
        separators=(",", ":"),
        sort_keys=True,
    )
