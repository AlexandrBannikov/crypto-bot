"""Research-only fee-aware profit locks layered over trailing floors.

The observer consumes fully closed candles, never emits orders, and never
mutates production state.  A floor derived from a candle high becomes eligible
to trigger only on the following candle.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import statistics
from typing import Any, Literal, Sequence

from app.break_even_shadow import protective_price
from app.candle import Candle
from app.trade_accounting import calculate_long_trade_accounting
from app.trading_controller import TradingControllerState


D = Decimal
TRAILING_PCTS = (D("0.005"), D("0.010"), D("0.015"), D("0.020"))
BUFFERS = (D("0"), D("0.001"))
ProfitLockStatus = Literal["inactive", "locked", "triggered"]
Effect = Literal["saved_loss", "protected_profit", "worsened_winner", "no_effect"]


def variant_key(trailing_pct: Decimal, buffer: Decimal) -> str:
    suffix = "BE" if buffer == 0 else "BE+0.1%"
    return f"{trailing_pct * 100:.1f}% + {suffix}"


@dataclass(frozen=True, slots=True)
class ProfitLockVariantState:
    trailing_pct: Decimal
    buffer: Decimal
    status: ProfitLockStatus = "inactive"
    trailing_floor: Decimal | None = None
    profit_lock_floor: Decimal | None = None
    effective_floor: Decimal | None = None
    activated_at_candle: int | None = None
    triggered_at_candle: int | None = None
    hypothetical_exit_price: Decimal | None = None
    hypothetical_net_pnl: Decimal | None = None


def _variants() -> tuple[ProfitLockVariantState, ...]:
    return tuple(
        ProfitLockVariantState(trailing_pct=trail, buffer=buffer)
        for buffer in BUFFERS for trail in TRAILING_PCTS
    )


@dataclass(frozen=True, slots=True)
class ProfitLockShadowState:
    entry_price: Decimal | None = None
    quantity: Decimal | None = None
    opened_at: str | None = None
    activation_price: Decimal | None = None
    fee_aware_be: Decimal | None = None
    peak_price: Decimal | None = None
    entry_candle: int | None = None
    variants: tuple[ProfitLockVariantState, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfitLockShadowObservation:
    candle_timestamp: int
    entry_price: Decimal | None
    quantity: Decimal | None
    opened_at: str | None
    activation_price: Decimal | None
    fee_aware_be: Decimal | None
    peak_price: Decimal | None
    variants: tuple[dict[str, object], ...]
    production_net_pnl: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ProfitLockShadowUpdate:
    state: ProfitLockShadowState
    observation: ProfitLockShadowObservation


def _new_position(
    production: TradingControllerState, entry_candle: int, fee_rate: Decimal,
) -> ProfitLockShadowState:
    if production.entry_price is None or production.position_quantity <= 0 or production.opened_at is None:
        raise ValueError("open production position has no stable identity")
    entry = production.entry_price
    return ProfitLockShadowState(
        entry_price=entry,
        quantity=production.position_quantity,
        opened_at=production.opened_at,
        activation_price=entry * D("1.005"),
        fee_aware_be=protective_price(entry, fee_rate),
        peak_price=entry,
        entry_candle=entry_candle,
        variants=_variants(),
    )


def _matches(state: ProfitLockShadowState, production: TradingControllerState) -> bool:
    return (
        production.has_open_position
        and state.entry_price == production.entry_price
        and state.quantity == production.position_quantity
        and state.opened_at == production.opened_at
        and tuple((v.trailing_pct, v.buffer) for v in state.variants)
        == tuple((t, b) for b in BUFFERS for t in TRAILING_PCTS)
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


def observe_profit_lock_shadow(
    state: ProfitLockShadowState,
    *,
    candle: Candle,
    production_before: TradingControllerState,
    production_after: TradingControllerState,
    fee_rate: Decimal = D("0.001"),
    production_net_pnl: Decimal | None = None,
) -> ProfitLockShadowUpdate:
    """Advance all eight counterfactuals with strict candle causality."""
    opened = not production_before.has_open_position and production_after.has_open_position
    was_open = production_before.has_open_position
    closed = was_open and not production_after.has_open_position
    current = state
    if not production_before.has_open_position and not production_after.has_open_position:
        current = ProfitLockShadowState()
    if opened:
        current = _new_position(production_after, candle.timestamp, fee_rate)
    elif was_open and current.entry_price is not None:
        assert current.quantity is not None and current.activation_price is not None
        updated: list[ProfitLockVariantState] = []
        # Trigger strictly against the effective floor known before this candle.
        for item in current.variants:
            if item.status == "locked" and item.effective_floor is not None and D(str(candle.low)) <= item.effective_floor:
                accounting = calculate_long_trade_accounting(
                    current.entry_price, item.effective_floor, current.quantity, fee_rate,
                )
                net = accounting.net_pnl
                if abs(net) < D("1e-18"):
                    net = D("0")
                updated.append(ProfitLockVariantState(
                    trailing_pct=item.trailing_pct, buffer=item.buffer,
                    status="triggered", trailing_floor=item.trailing_floor,
                    profit_lock_floor=item.profit_lock_floor,
                    effective_floor=item.effective_floor,
                    activated_at_candle=item.activated_at_candle,
                    triggered_at_candle=candle.timestamp,
                    hypothetical_exit_price=item.effective_floor,
                    hypothetical_net_pnl=net,
                ))
            else:
                updated.append(item)

        new_peak = max(current.peak_price or current.entry_price, D(str(candle.high)))
        activation_reached = new_peak >= current.activation_price
        effective: list[ProfitLockVariantState] = []
        for item in updated:
            if item.status == "triggered" or not activation_reached:
                effective.append(item)
                continue
            trailing_floor = new_peak * (D("1") - item.trailing_pct)
            if item.trailing_floor is not None:
                trailing_floor = max(trailing_floor, item.trailing_floor)
            assert current.fee_aware_be is not None
            lock_floor = current.fee_aware_be * (D("1") + item.buffer)
            if item.profit_lock_floor is not None:
                lock_floor = item.profit_lock_floor
            effective_floor = max(trailing_floor, lock_floor)
            if item.effective_floor is not None:
                effective_floor = max(effective_floor, item.effective_floor)
            effective.append(ProfitLockVariantState(
                trailing_pct=item.trailing_pct, buffer=item.buffer,
                status="locked", trailing_floor=trailing_floor,
                profit_lock_floor=lock_floor, effective_floor=effective_floor,
                activated_at_candle=item.activated_at_candle or candle.timestamp,
            ))
        current = ProfitLockShadowState(
            entry_price=current.entry_price, quantity=current.quantity,
            opened_at=current.opened_at, activation_price=current.activation_price,
            fee_aware_be=current.fee_aware_be, peak_price=new_peak,
            entry_candle=current.entry_candle, variants=tuple(effective),
        )

    snapshot = current
    rows: list[dict[str, object]] = []
    for item in snapshot.variants:
        accounting = None
        if item.hypothetical_exit_price is not None and snapshot.entry_price is not None and snapshot.quantity is not None:
            accounting = calculate_long_trade_accounting(
                snapshot.entry_price, item.hypothetical_exit_price,
                snapshot.quantity, fee_rate,
            )
        hypothetical = item.hypothetical_net_pnl
        if closed and production_net_pnl is not None:
            compared = hypothetical if hypothetical is not None else production_net_pnl
            delta = compared - production_net_pnl
            notional = (snapshot.entry_price or D("0")) * (snapshot.quantity or D("0"))
            delta_pct = delta / notional * 100 if notional else D("0")
            effect = _effect(production_net_pnl, compared, item.status == "triggered")
        else:
            compared = delta = delta_pct = effect = None
        rows.append({
            **asdict(item), "variant": variant_key(item.trailing_pct, item.buffer),
            "hypothetical_gross_pnl": accounting.gross_pnl if accounting else None,
            "hypothetical_entry_fee": accounting.entry_fee if accounting else None,
            "hypothetical_exit_fee": accounting.exit_fee if accounting else None,
            "hypothetical_return_pct": (
                accounting.net_pnl / accounting.entry_notional * 100 if accounting else None
            ),
            "comparison_hypothetical_net_pnl": compared,
            "production_net_pnl": production_net_pnl if closed else None,
            "delta_usdt": delta, "delta_pct": delta_pct, "effect": effect,
        })
    observation = ProfitLockShadowObservation(
        candle_timestamp=candle.timestamp, entry_price=snapshot.entry_price,
        quantity=snapshot.quantity, opened_at=snapshot.opened_at,
        activation_price=snapshot.activation_price,
        fee_aware_be=snapshot.fee_aware_be, peak_price=snapshot.peak_price,
        variants=tuple(rows), production_net_pnl=production_net_pnl if closed else None,
    )
    return ProfitLockShadowUpdate(ProfitLockShadowState() if closed else current, observation)


def reconcile_profit_lock_shadow(
    state: ProfitLockShadowState, *, production: TradingControllerState,
    candles: Sequence[Candle], fee_rate: Decimal = D("0.001"),
) -> ProfitLockShadowState:
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
    current = _new_position(production, entry_candle, fee_rate)
    for candle in ordered:
        if candle.timestamp > entry_candle:
            current = observe_profit_lock_shadow(
                current, candle=candle, production_before=production,
                production_after=production, fee_rate=fee_rate,
            ).state
    return current


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


class ProfitLockShadowStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> ProfitLockShadowState:
        if not self.path.exists():
            return ProfitLockShadowState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        variants = tuple(ProfitLockVariantState(**{
            **item,
            **{key: D(str(item[key])) for key in (
                "trailing_pct", "buffer", "trailing_floor", "profit_lock_floor",
                "effective_floor", "hypothetical_exit_price", "hypothetical_net_pnl",
            ) if item.get(key) is not None},
        }) for item in data.pop("variants", ()))
        for key in ("entry_price", "quantity", "activation_price", "fee_aware_be", "peak_price"):
            if data.get(key) is not None:
                data[key] = D(str(data[key]))
        return ProfitLockShadowState(**data, variants=variants)

    def save(self, state: ProfitLockShadowState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(_jsonable(asdict(state)), indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


class ProfitLockShadowJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, observation: ProfitLockShadowObservation) -> bool:
        identity = (observation.candle_timestamp, observation.opened_at)
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if (int(row["candle_timestamp"]), row.get("opened_at")) == identity:
                        return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(_jsonable(asdict(observation)), handle, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True


def aggregate_profit_lock_statistics(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate completed production comparisons once per position/variant."""
    result: dict[str, dict[str, Any]] = {}
    positions = {row.get("opened_at") for row in rows if row.get("opened_at")}
    for buffer in BUFFERS:
        for trail in TRAILING_PCTS:
            name = variant_key(trail, buffer)
            history = [
                (row, item) for row in rows for item in row.get("variants", ())
                if item.get("variant") == name
            ]
            closed = [item for _, item in history if item.get("production_net_pnl") is not None]
            deltas = [D(str(item.get("delta_usdt") or 0)) for item in closed]
            activated = {row.get("opened_at") for row, item in history if item.get("activated_at_candle") is not None}
            triggered = {row.get("opened_at") for row, item in history if item.get("triggered_at_candle") is not None}
            hypothetical = [D(str(item["comparison_hypothetical_net_pnl"])) for item in closed]
            total = sum(deltas, D("0"))
            result[name] = {
                "positions_observed": len(positions), "activated": len(activated),
                "triggered": len(triggered),
                **{effect.replace("protected_profit", "protected_profits").replace("saved_loss", "saved_losses").replace("worsened_winner", "worsened_winners").replace("no_effect", "no_effect"): sum(item.get("effect") == effect for item in closed)
                   for effect in ("saved_loss", "protected_profit", "worsened_winner", "no_effect")},
                "cumulative_delta_usdt": total,
                "average_delta_usdt": total / len(deltas) if deltas else D("0"),
                "median_delta_usdt": D(str(statistics.median(deltas))) if deltas else D("0"),
                "hypothetical_winners": sum(value > 0 for value in hypothetical),
                "hypothetical_losers": sum(value < 0 for value in hypothetical),
            }
    return result
