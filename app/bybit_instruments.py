from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


INSTRUMENTS_INFO_PATH = "/v5/market/instruments-info"
MAINNET_BASE_URL = "https://api.bybit.com"


def _default_http_get_json(
    url: str,
    timeout_seconds: float,
) -> dict:
    request = Request(
        url=url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "crypto-bot/1.0",
        },
    )

    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read().decode("utf-8")

    data = json.loads(payload)

    if not isinstance(data, dict):
        raise RuntimeError("Bybit returned an invalid JSON response")

    return data


def _parse_decimal(
    value: object,
    *,
    default: str = "0",
) -> Decimal:
    if value is None:
        return Decimal(default)

    text = str(value).strip()

    if not text:
        return Decimal(default)

    return Decimal(text)


@dataclass(frozen=True)
class InstrumentInfo:
    symbol: str
    status: str
    tick_size: Decimal
    qty_step: Decimal
    min_order_qty: Decimal
    max_order_qty: Decimal
    min_order_value: Decimal | None = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        status = self.status.strip()

        if not symbol:
            raise ValueError("symbol must not be empty")

        if not status:
            raise ValueError("status must not be empty")

        numeric_values = (
            self.tick_size,
            self.qty_step,
            self.min_order_qty,
            self.max_order_qty,
        )

        if any(value <= 0 for value in numeric_values):
            raise ValueError(
                "instrument size and price values must be greater than zero"
            )

        if (
            self.min_order_value is not None
            and self.min_order_value < 0
        ):
            raise ValueError(
                "min_order_value must not be negative"
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "status", status)

    @property
    def is_trading(self) -> bool:
        return self.status.upper() == "TRADING"


class BybitInstrumentClient:
    def __init__(
        self,
        *,
        base_url: str = MAINNET_BASE_URL,
        timeout_seconds: float = 10.0,
        http_get_json: Callable[[str, float], dict] = (
            _default_http_get_json
        ),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
            )

        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_get_json = http_get_json

    def get_spot_instrument(
        self,
        symbol: str,
    ) -> InstrumentInfo:
        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        query = urlencode(
            {
                "category": "spot",
                "symbol": normalized_symbol,
            }
        )
        url = (
            f"{self.base_url}{INSTRUMENTS_INFO_PATH}?{query}"
        )

        payload = self.http_get_json(
            url,
            self.timeout_seconds,
        )

        ret_code = payload.get("retCode", -1)

        if ret_code != 0:
            ret_msg = payload.get(
                "retMsg",
                "Unknown Bybit API error",
            )
            raise RuntimeError(
                f"Bybit API error {ret_code}: {ret_msg}"
            )

        instruments = (
            payload.get("result", {}).get("list", [])
        )

        for item in instruments:
            if item.get("symbol", "").upper() != normalized_symbol:
                continue

            price_filter = item.get("priceFilter", {})
            lot_filter = item.get("lotSizeFilter", {})

            qty_step_value = lot_filter.get(
                "qtyStep",
                lot_filter.get("basePrecision"),
            )

            max_order_qty_value = lot_filter.get(
                "maxLimitOrderQty",
                lot_filter.get("maxOrderQty"),
            )

            return InstrumentInfo(
                symbol=item.get("symbol", normalized_symbol),
                status=item.get("status", ""),
                tick_size=_parse_decimal(
                    price_filter.get("tickSize")
                ),
                qty_step=_parse_decimal(qty_step_value),
                min_order_qty=_parse_decimal(
                    lot_filter.get("minOrderQty"),
                    default=str(qty_step_value or "0"),
                ),
                max_order_qty=_parse_decimal(
                    max_order_qty_value
                ),
                min_order_value=_parse_decimal(
                    lot_filter.get("minOrderAmt")
                ),
            )

        raise LookupError(
            f"Spot instrument {normalized_symbol} was not found"
        )
