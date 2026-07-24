from decimal import Decimal

import pytest

from app.bybit_instruments import InstrumentInfo
from app.order_builder import (
    OrderValidationError,
    SpotLimitOrder,
    SpotOrderBuilder,
)


@pytest.fixture
def instrument() -> InstrumentInfo:
    return InstrumentInfo(
        symbol="ETHUSDT",
        status="Trading",
        tick_size=Decimal("0.01"),
        qty_step=Decimal("0.00001"),
        min_order_qty=Decimal("0.00001"),
        max_order_qty=Decimal("8118"),
        min_order_value=Decimal("5"),
    )


def test_limit_order_normalizes_symbol_and_side() -> None:
    order = SpotLimitOrder(
        symbol=" ethusdt ",
        side=" buy ",
        quantity=Decimal("0.01"),
        price=Decimal("3000"),
    )

    assert order.symbol == "ETHUSDT"
    assert order.side == "Buy"


def test_builder_rounds_price_and_quantity_down(
    instrument: InstrumentInfo,
) -> None:
    builder = SpotOrderBuilder(instrument)

    order = builder.build_limit_order(
        side="Buy",
        quantity=Decimal("0.003728915"),
        price=Decimal("3817.12867"),
    )

    assert order.quantity == Decimal("0.00372")
    assert order.price == Decimal("3817.12")


def test_order_value_is_calculated(
    instrument: InstrumentInfo,
) -> None:
    builder = SpotOrderBuilder(instrument)

    order = builder.build_limit_order(
        side="Buy",
        quantity=Decimal("0.01"),
        price=Decimal("3000"),
    )

    assert order.order_value == Decimal("30.00")


def test_order_builds_bybit_payload(
    instrument: InstrumentInfo,
) -> None:
    builder = SpotOrderBuilder(instrument)

    order = builder.build_limit_order(
        side="Sell",
        quantity=Decimal("0.010009"),
        price=Decimal("3000.999"),
    )

    assert order.to_bybit_payload() == {
        "category": "spot",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "orderType": "Limit",
        "qty": "0.01000",
        "price": "3000.99",
    }


def test_builder_rejects_order_below_minimum_value(
    instrument: InstrumentInfo,
) -> None:
    builder = SpotOrderBuilder(instrument)

    with pytest.raises(
        OrderValidationError,
        match="below the minimum order value",
    ):
        builder.build_limit_order(
            side="Buy",
            quantity=Decimal("0.00001"),
            price=Decimal("3000"),
        )


def test_builder_rejects_quantity_above_maximum(
    instrument: InstrumentInfo,
) -> None:
    builder = SpotOrderBuilder(instrument)

    with pytest.raises(
        OrderValidationError,
        match="exceeds the maximum",
    ):
        builder.build_limit_order(
            side="Buy",
            quantity=Decimal("9000"),
            price=Decimal("3000"),
        )


def test_builder_rejects_non_trading_instrument() -> None:
    instrument = InstrumentInfo(
        symbol="ETHUSDT",
        status="PreLaunch",
        tick_size=Decimal("0.01"),
        qty_step=Decimal("0.00001"),
        min_order_qty=Decimal("0.00001"),
        max_order_qty=Decimal("8118"),
        min_order_value=Decimal("5"),
    )
    builder = SpotOrderBuilder(instrument)

    with pytest.raises(
        OrderValidationError,
        match="not available for trading",
    ):
        builder.build_limit_order(
            side="Buy",
            quantity=Decimal("0.01"),
            price=Decimal("3000"),
        )


@pytest.mark.parametrize("side", ["", "Long", "Short"])
def test_order_rejects_invalid_side(side: str) -> None:
    with pytest.raises(ValueError, match="side must be Buy or Sell"):
        SpotLimitOrder(
            symbol="ETHUSDT",
            side=side,
            quantity=Decimal("0.01"),
            price=Decimal("3000"),
        )
