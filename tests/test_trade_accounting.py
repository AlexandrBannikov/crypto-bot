from decimal import Decimal

import pytest

from app.trade_accounting import (
    calculate_long_trade_accounting,
)


def test_calculates_profitable_long_trade() -> None:
    result = calculate_long_trade_accounting(
        entry_price=Decimal("100"),
        exit_price=Decimal("120"),
        quantity=Decimal("2"),
        fee_rate=Decimal("0.001"),
    )

    assert result.entry_notional == Decimal("200")
    assert result.exit_notional == Decimal("240")
    assert result.gross_pnl == Decimal("40")
    assert result.entry_fee == Decimal("0.200")
    assert result.exit_fee == Decimal("0.240")
    assert result.net_pnl == Decimal("39.560")


def test_calculates_losing_long_trade() -> None:
    result = calculate_long_trade_accounting(
        entry_price=Decimal("100"),
        exit_price=Decimal("90"),
        quantity=Decimal("2"),
        fee_rate=Decimal("0.001"),
    )

    assert result.gross_pnl == Decimal("-20")
    assert result.net_pnl == Decimal("-20.380")


def test_calculates_trade_without_fees() -> None:
    result = calculate_long_trade_accounting(
        entry_price=Decimal("100"),
        exit_price=Decimal("120"),
        quantity=Decimal("2"),
        fee_rate=Decimal("0"),
    )

    assert result.entry_fee == Decimal("0")
    assert result.exit_fee == Decimal("0")
    assert result.net_pnl == result.gross_pnl


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("entry_price", Decimal("0"), "entry_price"),
        ("exit_price", Decimal("-1"), "exit_price"),
        ("quantity", Decimal("0"), "quantity"),
        ("fee_rate", Decimal("-0.001"), "fee_rate"),
    ],
)
def test_rejects_invalid_values(
    field: str,
    value: Decimal,
    message: str,
) -> None:
    values = {
        "entry_price": Decimal("100"),
        "exit_price": Decimal("120"),
        "quantity": Decimal("2"),
        "fee_rate": Decimal("0.001"),
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        calculate_long_trade_accounting(**values)
