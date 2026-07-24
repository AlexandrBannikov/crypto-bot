from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from app.bybit_instruments import InstrumentInfo


class OrderValidationError(ValueError):
    """Ордер не соответствует торговым ограничениям биржи."""


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("step must be greater than zero")

    return (
        value / step
    ).to_integral_value(rounding=ROUND_DOWN) * step


@dataclass(frozen=True)
class SpotLimitOrder:
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        side = self.side.strip().capitalize()

        if not symbol:
            raise ValueError("symbol must not be empty")

        if side not in {"Buy", "Sell"}:
            raise ValueError("side must be Buy or Sell")

        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero")

        if self.price <= 0:
            raise ValueError("price must be greater than zero")

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "side", side)

    @property
    def order_value(self) -> Decimal:
        return self.quantity * self.price

    def to_bybit_payload(self) -> dict[str, str]:
        return {
            "category": "spot",
            "symbol": self.symbol,
            "side": self.side,
            "orderType": "Limit",
            "qty": format(self.quantity, "f"),
            "price": format(self.price, "f"),
        }


class SpotOrderBuilder:
    def __init__(self, instrument: InstrumentInfo) -> None:
        self.instrument = instrument

    def build_limit_order(
        self,
        *,
        side: str,
        quantity: Decimal,
        price: Decimal,
    ) -> SpotLimitOrder:
        if not self.instrument.is_trading:
            raise OrderValidationError(
                f"{self.instrument.symbol} is not available for trading"
            )

        if quantity <= 0:
            raise OrderValidationError(
                "quantity must be greater than zero"
            )

        if price <= 0:
            raise OrderValidationError(
                "price must be greater than zero"
            )

        normalized_quantity = _floor_to_step(
            quantity,
            self.instrument.qty_step,
        )
        normalized_price = _floor_to_step(
            price,
            self.instrument.tick_size,
        )

        if normalized_quantity <= 0:
            raise OrderValidationError(
                "quantity becomes zero after rounding"
            )

        if normalized_price <= 0:
            raise OrderValidationError(
                "price becomes zero after rounding"
            )

        if normalized_quantity < self.instrument.min_order_qty:
            raise OrderValidationError(
                "quantity is below the minimum order quantity"
            )

        if normalized_quantity > self.instrument.max_order_qty:
            raise OrderValidationError(
                "quantity exceeds the maximum order quantity"
            )

        order = SpotLimitOrder(
            symbol=self.instrument.symbol,
            side=side,
            quantity=normalized_quantity,
            price=normalized_price,
        )

        minimum_value = self.instrument.min_order_value

        if (
            minimum_value is not None
            and order.order_value < minimum_value
        ):
            raise OrderValidationError(
                "order value is below the minimum order value"
            )

        return order
