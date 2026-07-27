from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ClosedTradeAccounting:
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_notional: Decimal
    exit_notional: Decimal
    gross_pnl: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    net_pnl: Decimal


def calculate_long_trade_accounting(
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    fee_rate: Decimal,
) -> ClosedTradeAccounting:
    if entry_price <= 0:
        raise ValueError(
            "entry_price must be greater than zero"
        )

    if exit_price <= 0:
        raise ValueError(
            "exit_price must be greater than zero"
        )

    if quantity <= 0:
        raise ValueError(
            "quantity must be greater than zero"
        )

    if fee_rate < 0:
        raise ValueError(
            "fee_rate must not be negative"
        )

    entry_notional = entry_price * quantity
    exit_notional = exit_price * quantity
    gross_pnl = exit_notional - entry_notional
    entry_fee = entry_notional * fee_rate
    exit_fee = exit_notional * fee_rate
    net_pnl = gross_pnl - entry_fee - exit_fee

    return ClosedTradeAccounting(
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        entry_notional=entry_notional,
        exit_notional=exit_notional,
        gross_pnl=gross_pnl,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        net_pnl=net_pnl,
    )
