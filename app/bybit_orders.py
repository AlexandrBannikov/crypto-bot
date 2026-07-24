from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import time
from typing import Any, Callable
from urllib.request import Request, urlopen

from app.bybit_account import (
    BYBIT_MAINNET_API_URL,
    BYBIT_TESTNET_API_URL,
    BybitAPIError,
    BybitAccountConfig,
)
from app.order_builder import SpotLimitOrder


CREATE_ORDER_PATH = "/v5/order/create"


@dataclass(frozen=True, slots=True)
class OrderResult:
    order_id: str | None
    order_link_id: str | None
    dry_run: bool
    payload: dict[str, str]


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
        http_post_json: HttpPostJSON | None = None,
        clock_ms: ClockMS | None = None,
    ) -> None:
        self.config = config
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
            normalized_link_id = order_link_id.strip()

            if not normalized_link_id:
                raise ValueError(
                    "order_link_id must not be empty"
                )

            payload["orderLinkId"] = normalized_link_id

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
        result = response.get("result")

        if not isinstance(result, dict):
            raise ValueError("unexpected create order response")

        raw_order_id = result.get("orderId")
        raw_order_link_id = result.get("orderLinkId")

        order_id = (
            str(raw_order_id).strip()
            if raw_order_id is not None
            else None
        )
        response_order_link_id = (
            str(raw_order_link_id).strip()
            if raw_order_link_id is not None
            else None
        )

        if not order_id:
            raise ValueError("unexpected create order response")

        return OrderResult(
            order_id=order_id,
            order_link_id=response_order_link_id or None,
            dry_run=False,
            payload=dict(payload),
        )

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

        headers = {
            "Content-Type": "application/json",
            "X-BAPI-API-KEY": self.config.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        }

        response = self._http_post_json(
            f"{self.base_url}{path}",
            headers,
            body_text.encode("utf-8"),
            self.config.timeout_seconds,
        )
        ret_code = response.get("retCode")

        if ret_code != 0:
            raise BybitAPIError(
                ret_code=(
                    int(ret_code)
                    if isinstance(ret_code, int | str)
                    and str(ret_code).lstrip("-").isdigit()
                    else None
                ),
                ret_msg=str(
                    response.get(
                        "retMsg",
                        "Bybit API error",
                    )
                ),
            )

        return response

    def _sign_post(
        self,
        timestamp: str,
        recv_window: str,
        body_text: str,
    ) -> str:
        payload = (
            f"{timestamp}"
            f"{self.config.api_key}"
            f"{recv_window}"
            f"{body_text}"
        )

        return hmac.new(
            self.config.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            sha256,
        ).hexdigest()

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
