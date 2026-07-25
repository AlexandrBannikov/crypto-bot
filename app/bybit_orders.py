from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import hmac
import json
import time
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.bybit_account import (
    BYBIT_MAINNET_API_URL,
    BYBIT_TESTNET_API_URL,
    BybitAPIError,
    BybitAccountConfig,
)
from app.order_builder import SpotLimitOrder


CREATE_ORDER_PATH = "/v5/order/create"
CANCEL_ORDER_PATH = "/v5/order/cancel"
REALTIME_ORDER_PATH = "/v5/order/realtime"


@dataclass(frozen=True, slots=True)
class OrderResult:
    order_id: str | None
    order_link_id: str | None
    dry_run: bool
    payload: dict[str, str]


@dataclass(frozen=True, slots=True)
class CancelOrderResult:
    order_id: str | None
    order_link_id: str | None
    dry_run: bool
    payload: dict[str, str]


@dataclass(frozen=True, slots=True)
class OrderStatus:
    order_id: str
    order_link_id: str | None
    symbol: str
    side: str
    order_type: str
    order_status: str
    price: Decimal
    quantity: Decimal
    executed_quantity: Decimal
    remaining_quantity: Decimal


HttpGetJSON = Callable[
    [str, dict[str, str], float],
    dict[str, Any],
]
HttpPostJSON = Callable[
    [str, dict[str, str], bytes, float],
    dict[str, Any],
]
ClockMS = Callable[[], int]


class BybitOrderClient:
    def __init__(
        self,
        config: BybitAccountConfig,
        *,
        http_get_json: HttpGetJSON | None = None,
        http_post_json: HttpPostJSON | None = None,
        clock_ms: ClockMS | None = None,
    ) -> None:
        self.config = config
        self._http_get_json = (
            http_get_json or self._default_http_get_json
        )
        self._http_post_json = (
            http_post_json or self._default_http_post_json
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

    def create_limit_order(
        self,
        order: SpotLimitOrder,
        *,
        order_link_id: str | None = None,
        dry_run: bool = True,
    ) -> OrderResult:
        payload = order.to_bybit_payload()

        if order_link_id is not None:
            payload["orderLinkId"] = self._normalize_identifier(
                order_link_id,
                "order_link_id",
            )

        if dry_run:
            return OrderResult(
                order_id=None,
                order_link_id=payload.get("orderLinkId"),
                dry_run=True,
                payload=dict(payload),
            )

        response = self._signed_post(
            CREATE_ORDER_PATH,
            payload,
        )
        result = self._require_result_dict(
            response,
            "unexpected create order response",
        )

        order_id = self._optional_string(result.get("orderId"))
        response_order_link_id = self._optional_string(
            result.get("orderLinkId")
        )

        if order_id is None:
            raise ValueError("unexpected create order response")

        return OrderResult(
            order_id=order_id,
            order_link_id=response_order_link_id,
            dry_run=False,
            payload=dict(payload),
        )

    def get_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> OrderStatus:
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_order_id, normalized_order_link_id = (
            self._normalize_order_identifiers(
                order_id=order_id,
                order_link_id=order_link_id,
            )
        )

        query = {
            "category": "spot",
            "symbol": normalized_symbol,
        }

        if normalized_order_id is not None:
            query["orderId"] = normalized_order_id
        elif normalized_order_link_id is not None:
            query["orderLinkId"] = normalized_order_link_id

        response = self._signed_get(
            REALTIME_ORDER_PATH,
            query,
        )
        result = self._require_result_dict(
            response,
            "unexpected realtime order response",
        )
        orders = result.get("list")

        if not isinstance(orders, list):
            raise ValueError("unexpected realtime order response")

        if not orders:
            raise LookupError("order not found")

        raw_order = orders[0]

        if not isinstance(raw_order, dict):
            raise ValueError("unexpected realtime order response")

        raw_order_id = self._optional_string(
            raw_order.get("orderId")
        )

        if raw_order_id is None:
            raise ValueError("unexpected realtime order response")

        return OrderStatus(
            order_id=raw_order_id,
            order_link_id=self._optional_string(
                raw_order.get("orderLinkId")
            ),
            symbol=str(raw_order.get("symbol", "")).strip(),
            side=str(raw_order.get("side", "")).strip(),
            order_type=str(
                raw_order.get("orderType", "")
            ).strip(),
            order_status=str(
                raw_order.get("orderStatus", "")
            ).strip(),
            price=self._decimal_or_zero(raw_order.get("price")),
            quantity=self._decimal_or_zero(raw_order.get("qty")),
            executed_quantity=self._decimal_or_zero(
                raw_order.get("cumExecQty")
            ),
            remaining_quantity=self._decimal_or_zero(
                raw_order.get("leavesQty")
            ),
        )

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
        dry_run: bool = True,
    ) -> CancelOrderResult:
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_order_id, normalized_order_link_id = (
            self._normalize_order_identifiers(
                order_id=order_id,
                order_link_id=order_link_id,
            )
        )

        payload = {
            "category": "spot",
            "symbol": normalized_symbol,
        }

        if normalized_order_id is not None:
            payload["orderId"] = normalized_order_id
        elif normalized_order_link_id is not None:
            payload["orderLinkId"] = normalized_order_link_id

        if dry_run:
            return CancelOrderResult(
                order_id=normalized_order_id,
                order_link_id=normalized_order_link_id,
                dry_run=True,
                payload=dict(payload),
            )

        response = self._signed_post(
            CANCEL_ORDER_PATH,
            payload,
        )
        result = self._require_result_dict(
            response,
            "unexpected cancel order response",
        )

        response_order_id = self._optional_string(
            result.get("orderId")
        )
        response_order_link_id = self._optional_string(
            result.get("orderLinkId")
        )

        if (
            response_order_id is None
            and response_order_link_id is None
        ):
            raise ValueError("unexpected cancel order response")

        return CancelOrderResult(
            order_id=response_order_id,
            order_link_id=response_order_link_id,
            dry_run=False,
            payload=dict(payload),
        )

    def _signed_get(
        self,
        path: str,
        query: dict[str, str],
    ) -> dict[str, Any]:
        timestamp = str(self._clock_ms())
        recv_window = str(self.config.recv_window)
        query_text = urlencode(sorted(query.items()))
        signature = self._sign_get(
            timestamp,
            recv_window,
            query_text,
        )
        headers = self._signed_headers(
            timestamp,
            recv_window,
            signature,
        )

        response = self._http_get_json(
            f"{self.base_url}{path}?{query_text}",
            headers,
            self.config.timeout_seconds,
        )
        self._raise_for_api_error(response)
        return response

    def _signed_post(
        self,
        path: str,
        payload: dict[str, str],
    ) -> dict[str, Any]:
        timestamp = str(self._clock_ms())
        recv_window = str(self.config.recv_window)
        body_text = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )
        signature = self._sign_post(
            timestamp,
            recv_window,
            body_text,
        )
        headers = self._signed_headers(
            timestamp,
            recv_window,
            signature,
        )
        headers["Content-Type"] = "application/json"

        response = self._http_post_json(
            f"{self.base_url}{path}",
            headers,
            body_text.encode("utf-8"),
            self.config.timeout_seconds,
        )
        self._raise_for_api_error(response)
        return response

    def _signed_headers(
        self,
        timestamp: str,
        recv_window: str,
        signature: str,
    ) -> dict[str, str]:
        return {
            "X-BAPI-API-KEY": self.config.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        }

    def _sign_get(
        self,
        timestamp: str,
        recv_window: str,
        query_text: str,
    ) -> str:
        return self._create_signature(
            timestamp,
            recv_window,
            query_text,
        )

    def _sign_post(
        self,
        timestamp: str,
        recv_window: str,
        body_text: str,
    ) -> str:
        return self._create_signature(
            timestamp,
            recv_window,
            body_text,
        )

    def _create_signature(
        self,
        timestamp: str,
        recv_window: str,
        request_data: str,
    ) -> str:
        payload = (
            f"{timestamp}"
            f"{self.config.api_key}"
            f"{recv_window}"
            f"{request_data}"
        )

        return hmac.new(
            self.config.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            sha256,
        ).hexdigest()

    @staticmethod
    def _raise_for_api_error(
        response: dict[str, Any],
    ) -> None:
        ret_code = response.get("retCode")

        if ret_code == 0:
            return

        normalized_code = (
            int(ret_code)
            if isinstance(ret_code, (int, str))
            and str(ret_code).lstrip("-").isdigit()
            else None
        )

        raise BybitAPIError(
            ret_code=normalized_code,
            ret_msg=str(
                response.get(
                    "retMsg",
                    "Bybit API error",
                )
            ),
        )

    @staticmethod
    def _require_result_dict(
        response: dict[str, Any],
        error_message: str,
    ) -> dict[str, Any]:
        result = response.get("result")

        if not isinstance(result, dict):
            raise ValueError(error_message)

        return result

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()

        if not normalized:
            raise ValueError("symbol must not be empty")

        return normalized

    @classmethod
    def _normalize_order_identifiers(
        cls,
        *,
        order_id: str | None,
        order_link_id: str | None,
    ) -> tuple[str | None, str | None]:
        normalized_order_id = (
            cls._normalize_identifier(order_id, "order_id")
            if order_id is not None
            else None
        )
        normalized_order_link_id = (
            cls._normalize_identifier(
                order_link_id,
                "order_link_id",
            )
            if order_link_id is not None
            else None
        )

        if (
            normalized_order_id is None
            and normalized_order_link_id is None
        ):
            raise ValueError(
                "order_id or order_link_id is required"
            )

        return normalized_order_id, normalized_order_link_id

    @staticmethod
    def _normalize_identifier(
        value: str,
        field_name: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{field_name} must not be empty"
            )

        return normalized

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _decimal_or_zero(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")

        normalized = str(value).strip()

        if not normalized:
            return Decimal("0")

        return Decimal(normalized)

    @staticmethod
    def _default_http_get_json(
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        request = Request(
            url=url,
            method="GET",
            headers=headers,
        )

        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            response_body = response.read().decode("utf-8")

        payload = json.loads(response_body)

        if not isinstance(payload, dict):
            raise ValueError("Bybit returned invalid JSON")

        return payload

    @staticmethod
    def _default_http_post_json(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        request = Request(
            url=url,
            data=body,
            method="POST",
            headers=headers,
        )

        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            response_body = response.read().decode("utf-8")

        payload = json.loads(response_body)

        if not isinstance(payload, dict):
            raise ValueError("Bybit returned invalid JSON")

        return payload
