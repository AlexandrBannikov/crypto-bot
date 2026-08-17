"""Research-only multi-variant trailing stops for production PAPER LONGs.

The observer consumes fully closed candles and cannot emit orders or mutate the
production controller.  Floors calculated from a candle's high become usable
only by the following candle, avoiding assumptions about intrabar high/low
ordering.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Literal, Sequence

from app.candle import Candle
from app.trade_accounting import calculate_long_trade_accounting
from app.trading_controller import TradingControllerState


D = Decimal
TRAILING_PCTS = (D("0.005"), D("0.010"), D("0.015"), D("0.020"))
TrailingStatus = Literal["inactive", "trailing", "triggered"]
Effect = Literal["saved_loss", "protected_profit", "worsened_winner", "no_effect"]


def variant_key(value: Decimal) -> str:
    return f"{value * 100:.1f}%"


@dataclass(frozen=True, slots=True)
class TrailingVariantState:
    trailing_pct: Decimal
    status: TrailingStatus = "inactive"
    current_floor: Decimal | None = None
    activated_at_candle: int | None = None
    triggered_at_candle: int | None = None
    hypothetical_exit_price: Decimal | None = None
    hypothetical_net_pnl: Decimal | None = None


def _initial_variants() -> tuple[TrailingVariantState, ...]:
    return tuple(TrailingVariantState(value) for value in TRAILING_PCTS)


@dataclass(frozen=True, slots=True)
class TrailingShadowState:
    entry_price: Decimal | None = None
    quantity: Decimal | None = None
    opened_at: str | None = None
    activation_price: Decimal | None = None
    peak_price: Decimal | None = None
    entry_candle: int | None = None
    variants: tuple[TrailingVariantState, ...] = ()


@dataclass(frozen=True, slots=True)
class TrailingShadowObservation:
    candle_timestamp: int
    entry_price: Decimal | None
    quantity: Decimal | None
    opened_at: str | None
    activation_price: Decimal | None
    peak_price: Decimal | None
    variants: tuple[dict[str, object], ...]
    production_net_pnl: Decimal | None = None


@dataclass(frozen=True, slots=True)
class TrailingShadowUpdate:
    state: TrailingShadowState
    observation: TrailingShadowObservation


def _matches(state: TrailingShadowState, production: TradingControllerState) -> bool:
    return (
        production.has_open_position
        and state.entry_price == production.entry_price
        and state.quantity == production.position_quantity
        and state.opened_at == production.opened_at
        and tuple(item.trailing_pct for item in state.variants) == TRAILING_PCTS
    )


def _new_position(production: TradingControllerState, entry_candle: int) -> TrailingShadowState:
    if production.entry_price is None or production.position_quantity <= 0 or production.opened_at is None:
        raise ValueError("open production position has no stable identity")
    return TrailingShadowState(
        entry_price=production.entry_price,
        quantity=production.position_quantity,
        opened_at=production.opened_at,
        activation_price=production.entry_price * D("1.005"),
        peak_price=production.entry_price,
        entry_candle=entry_candle,
        variants=_initial_variants(),
    )


def _effect(production: Decimal, hypothetical: Decimal, triggered: bool) -> Effect:
    if not triggered or hypothetical == production:
        return "no_effect"
    if production <= 0 and hypothetical > production:
        return "saved_loss"
    if production > 0 and hypothetical > production:
        return "protected_profit"
    if production > 0 and hypothetical < production:
        return "worsened_winner"
    return "no_effect"


def observe_trailing_shadow(
    state: TrailingShadowState,
    *,
    candle: Candle,
    production_before: TradingControllerState,
    production_after: TradingControllerState,
    fee_rate: Decimal = D("0.001"),
    production_net_pnl: Decimal | None = None,
) -> TrailingShadowUpdate:
    """Advance shadow state; both production snapshots remain authoritative."""
    opened = not production_before.has_open_position and production_after.has_open_position
    was_open = production_before.has_open_position
    closed = was_open and not production_after.has_open_position
    current = state
    if not production_before.has_open_position and not production_after.has_open_position:
        current = TrailingShadowState()
    if opened:
        current = _new_position(production_after, candle.timestamp)
    elif was_open and current.entry_price is not None:
        assert current.quantity is not None
        updated: list[TrailingVariantState] = []
        # Only floors known before this candle may trigger on this candle.
        for item in current.variants:
            if item.status == "trailing" and item.current_floor is not None and D(str(candle.low)) <= item.current_floor:
                pnl = calculate_long_trade_accounting(
                    current.entry_price, item.current_floor, current.quantity, fee_rate
                ).net_pnl
                updated.append(TrailingVariantState(
                    trailing_pct=item.trailing_pct, status="triggered",
                    current_floor=item.current_floor,
                    activated_at_candle=item.activated_at_candle,
                    triggered_at_candle=candle.timestamp,
                    hypothetical_exit_price=item.current_floor,
                    hypothetical_net_pnl=pnl,
                ))
            else:
                updated.append(item)
        new_peak = max(current.peak_price or current.entry_price, D(str(candle.high)))
        activation_reached = new_peak >= current.activation_price
        effective: list[TrailingVariantState] = []
        for item in updated:
            if item.status == "triggered" or not activation_reached:
                effective.append(item)
                continue
            floor = new_peak * (D("1") - item.trailing_pct)
            if item.current_floor is not None:
                floor = max(floor, item.current_floor)
            effective.append(TrailingVariantState(
                trailing_pct=item.trailing_pct, status="trailing",
                current_floor=floor,
                activated_at_candle=item.activated_at_candle or candle.timestamp,
            ))
        current = TrailingShadowState(
            entry_price=current.entry_price, quantity=current.quantity,
            opened_at=current.opened_at, activation_price=current.activation_price,
            peak_price=new_peak, entry_candle=current.entry_candle,
            variants=tuple(effective),
        )

    snapshot = current
    rows: list[dict[str, object]] = []
    for item in snapshot.variants:
        hypothetical = item.hypothetical_net_pnl
        if closed and production_net_pnl is not None:
            compared = hypothetical if hypothetical is not None else production_net_pnl
            delta = compared - production_net_pnl
            notional = snapshot.entry_price * snapshot.quantity if snapshot.entry_price and snapshot.quantity else D("0")
            effect = _effect(production_net_pnl, compared, item.status == "triggered")
            delta_pct = delta / notional * 100 if notional else D("0")
        else:
            compared = delta = delta_pct = effect = None
        rows.append({
            **asdict(item), "variant": variant_key(item.trailing_pct),
            "comparison_hypothetical_net_pnl": compared,
            "production_net_pnl": production_net_pnl if closed else None,
            "delta_usdt": delta, "delta_pct": delta_pct, "effect": effect,
        })
    observation = TrailingShadowObservation(
        candle_timestamp=candle.timestamp, entry_price=snapshot.entry_price,
        quantity=snapshot.quantity, opened_at=snapshot.opened_at,
        activation_price=snapshot.activation_price, peak_price=snapshot.peak_price,
        variants=tuple(rows), production_net_pnl=production_net_pnl if closed else None,
    )
    return TrailingShadowUpdate(TrailingShadowState() if closed else current, observation)


def reconcile_trailing_shadow(
    state: TrailingShadowState, *, production: TradingControllerState,
    candles: Sequence[Candle], fee_rate: Decimal = D("0.001"),
) -> TrailingShadowState:
    if not production.has_open_position or _matches(state, production):
        return state
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    if not ordered:
        raise ValueError("reconciliation requires historical candles")
    opened = int(datetime.fromisoformat(production.opened_at or "").timestamp())
    deltas = [b.timestamp - a.timestamp for a, b in zip(ordered, ordered[1:]) if b.timestamp > a.timestamp]
    interval = min(deltas) if deltas else 3600
    entry_candle = opened // interval * interval - interval
    if ordered[0].timestamp > entry_candle + interval:
        raise ValueError("historical candles do not cover production entry")
    current = _new_position(production, entry_candle)
    for item in ordered:
        if item.timestamp > entry_candle:
            current = observe_trailing_shadow(
                current, candle=item, production_before=production,
                production_after=production, fee_rate=fee_rate,
            ).state
    return current


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


class TrailingShadowStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> TrailingShadowState:
        if not self.path.exists():
            return TrailingShadowState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        variants = tuple(TrailingVariantState(
            trailing_pct=D(str(item["trailing_pct"])), status=item["status"],
            current_floor=D(str(item["current_floor"])) if item.get("current_floor") is not None else None,
            activated_at_candle=item.get("activated_at_candle"),
            triggered_at_candle=item.get("triggered_at_candle"),
            hypothetical_exit_price=D(str(item["hypothetical_exit_price"])) if item.get("hypothetical_exit_price") is not None else None,
            hypothetical_net_pnl=D(str(item["hypothetical_net_pnl"])) if item.get("hypothetical_net_pnl") is not None else None,
        ) for item in data.pop("variants", ()))
        for key in ("entry_price", "quantity", "activation_price", "peak_price"):
            if data.get(key) is not None:
                data[key] = D(str(data[key]))
        return TrailingShadowState(**data, variants=variants)

    def save(self, state: TrailingShadowState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(_jsonable(asdict(state)), indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


class TrailingShadowJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, observation: TrailingShadowObservation) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        identity = (observation.candle_timestamp, observation.opened_at)
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if (int(row["candle_timestamp"]), row.get("opened_at")) == identity:
                        return False
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(_jsonable(asdict(observation)), handle, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True
