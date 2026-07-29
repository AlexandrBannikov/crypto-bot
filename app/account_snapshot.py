from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


ZERO = Decimal("0")


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def _opened_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    initial_balance: Decimal
    cash_balance: Decimal
    position_side: str
    position_quantity: Decimal
    entry_price: Decimal | None
    current_price: Decimal | None
    position_market_value: Decimal | None
    equity: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None
    total_pnl: Decimal | None
    realized_return_pct: Decimal
    total_return_pct: Decimal | None
    unrealized_return_pct: Decimal | None
    opened_at: str | None
    position_age_seconds: int | None
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    break_even_active: bool
    trailing_stop_active: bool
    distance_to_stop_value: Decimal | None
    distance_to_stop_pct: Decimal | None
    distance_to_take_profit_value: Decimal | None
    distance_to_take_profit_pct: Decimal | None

    @property
    def is_open(self) -> bool:
        return self.position_side != "FLAT" and self.position_quantity > ZERO

    def to_dict(self) -> dict[str, Any]:
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(self).items()
        }


def calculate_account_snapshot(
    *,
    initial_balance: Any,
    cash_balance: Any,
    position_side: str = "FLAT",
    position_quantity: Any = 0,
    entry_price: Any = None,
    current_price: Any = None,
    realized_pnl: Any = 0,
    opened_at: str | None = None,
    now: datetime | None = None,
    stop_loss_price: Any = None,
    take_profit_price: Any = None,
    break_even_active: bool = False,
    trailing_stop_active: bool = False,
) -> AccountSnapshot:
    """Build an account snapshot without I/O.

    LONG is the controller's spot model. SHORT is supported for reporting
    abstractions: its equity is initial balance + realised + unrealised PnL,
    rather than applying the LONG spot cash-plus-asset formula.
    """
    initial = _decimal(initial_balance) or ZERO
    cash = _decimal(cash_balance) or ZERO
    quantity = abs(_decimal(position_quantity) or ZERO)
    side = str(position_side or "FLAT").upper()
    if quantity == ZERO or side not in {"LONG", "SHORT"}:
        side = "FLAT"
        quantity = ZERO
    entry = _decimal(entry_price)
    price = _decimal(current_price)
    realized = _decimal(realized_pnl) or ZERO
    stop = _decimal(stop_loss_price)
    take_profit = _decimal(take_profit_price)

    market_value = quantity * price if side != "FLAT" and price is not None else (
        ZERO if side == "FLAT" else None
    )
    unrealized = ZERO if side == "FLAT" else None
    unrealized_return = ZERO if side == "FLAT" else None
    if side != "FLAT" and entry is not None and price is not None:
        direction = Decimal("1") if side == "LONG" else Decimal("-1")
        unrealized = quantity * (price - entry) * direction
        unrealized_return = (
            (price - entry) * direction / entry * Decimal("100")
            if entry
            else None
        )

    if side == "SHORT":
        equity = initial + realized + unrealized if unrealized is not None else None
    else:
        equity = cash + market_value if market_value is not None else None
    total = realized + unrealized if unrealized is not None else None
    realized_return = realized / initial * Decimal("100") if initial else ZERO
    total_return = total / initial * Decimal("100") if initial and total is not None else None

    age = None
    opened = _opened_at(opened_at)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if opened is not None:
        age = max(0, int((current.astimezone(timezone.utc) - opened.astimezone(timezone.utc)).total_seconds()))

    stop_value = stop_pct = take_value = take_pct = None
    if side != "FLAT" and price is not None and price != ZERO:
        if stop is not None:
            stop_value = price - stop if side == "LONG" else stop - price
            stop_pct = stop_value / price * Decimal("100")
        if take_profit is not None:
            take_value = take_profit - price if side == "LONG" else price - take_profit
            take_pct = take_value / price * Decimal("100")

    return AccountSnapshot(
        initial, cash, side, quantity, entry, price, market_value, equity,
        realized, unrealized, total, realized_return, total_return,
        unrealized_return, opened_at, age, stop, take_profit,
        bool(break_even_active), bool(trailing_stop_active),
        stop_value, stop_pct, take_value, take_pct,
    )


def format_position_age(seconds: int | None) -> str:
    if seconds is None:
        return "N/A"
    minutes = max(0, seconds) // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, remaining_minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {remaining_minutes}m"
    days, remaining_hours = divmod(hours, 24)
    return f"{days}d {remaining_hours}h"


def market_from_decisions(
    rows: list[dict[str, Any]],
    *,
    symbol: str = "ETHUSDT",
    source: str = "Bybit",
) -> dict[str, Any]:
    """Read the newest already-recorded candle price; never performs I/O."""
    candidates: list[tuple[int, Decimal]] = []
    for row in rows:
        try:
            timestamp = int(row["candle_timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        price = _decimal(row.get("close", row.get("price")))
        if price is not None and price > ZERO:
            candidates.append((timestamp, price))
    if not candidates:
        return {"symbol": symbol, "price": None, "price_timestamp": None, "source": None}
    timestamp, price = max(candidates, key=lambda item: item[0])
    return {
        "symbol": symbol,
        "price": str(price),
        "price_timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        "source": source,
    }
