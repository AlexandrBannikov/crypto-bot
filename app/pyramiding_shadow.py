"""Research-only pyramiding for production PAPER LONG positions.

Decisions are made once per fully closed hourly candle and execute at that
candle's close, matching production PAPER close-decision semantics.  The
observer never reads a later candle (including its high/low), emits no order,
and never mutates production state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import statistics
from typing import Any, Iterable, Sequence

from app.candle import Candle
from app.trading_controller import TradingControllerState


D = Decimal
THRESHOLDS = (D("65"), D("70"), D("75"))
ADD_QUANTITY = D("0.01")
MAX_ADDS = 3
COOLDOWN_CANDLES = 3
INITIAL_BALANCE = D("1000")


@dataclass(frozen=True, slots=True)
class AddOn:
    candle_timestamp: int
    price: Decimal
    quantity: Decimal
    notional: Decimal
    fee: Decimal
    weighted_average_entry: Decimal
    total_quantity: Decimal
    total_exposure: Decimal
    score: Decimal


@dataclass(frozen=True, slots=True)
class VariantState:
    threshold: Decimal
    quantity: Decimal
    total_cost_basis: Decimal
    weighted_average_entry: Decimal
    total_entry_fees: Decimal
    initial_notional: Decimal
    added_notional: Decimal = D("0")
    maximum_total_notional: Decimal = D("0")
    maximum_total_quantity: Decimal = D("0")
    peak_exposure_pct: Decimal = D("0")
    add_ons: tuple[AddOn, ...] = ()
    last_add_candle: int | None = None
    last_observed_candle: int | None = None
    peak_unrealized_pnl: Decimal = D("0")
    maximum_unrealized_drawdown: Decimal = D("0")
    mae: Decimal = D("0")
    mfe: Decimal = D("0")


@dataclass(frozen=True, slots=True)
class PyramidingShadowState:
    opened_at: str | None = None
    entry_price: Decimal | None = None
    initial_quantity: Decimal | None = None
    entry_candle: int | None = None
    variants: tuple[VariantState, ...] = ()


@dataclass(frozen=True, slots=True)
class PyramidingShadowUpdate:
    state: PyramidingShadowState
    observation: dict[str, Any]


def _new_position(production: TradingControllerState, entry_candle: int,
                  fee_rate: Decimal) -> PyramidingShadowState:
    if production.entry_price is None or production.position_quantity <= 0 or not production.opened_at:
        raise ValueError("open production position has no stable identity")
    notional = production.entry_price * production.position_quantity
    fee = notional * fee_rate
    variants = tuple(VariantState(
        threshold=value, quantity=production.position_quantity,
        total_cost_basis=notional, weighted_average_entry=production.entry_price,
        total_entry_fees=fee, initial_notional=notional,
        maximum_total_notional=notional,
        maximum_total_quantity=production.position_quantity,
        peak_exposure_pct=notional / INITIAL_BALANCE * 100,
    ) for value in THRESHOLDS)
    return PyramidingShadowState(production.opened_at, production.entry_price,
                                  production.position_quantity, entry_candle, variants)


def _matches(state: PyramidingShadowState, production: TradingControllerState) -> bool:
    return (production.has_open_position and state.opened_at == production.opened_at
            and state.entry_price == production.entry_price
            and state.initial_quantity == production.position_quantity
            and tuple(v.threshold for v in state.variants) == THRESHOLDS)


def _component(score: dict[str, Any] | None, name: str) -> Decimal:
    if not score:
        return D("0")
    source = score.get("components") or score.get("score_components") or {}
    value = source.get(name, source.get(f"{name}_score", 0))
    if isinstance(value, dict):
        value = value.get("weighted_score", value.get("score", 0))
    return D(str(value or 0))


def _score_total(score: dict[str, Any] | None) -> Decimal | None:
    if not score:
        return None
    value = score.get("score_total", score.get("signal_score", score.get("score")))
    return D(str(value)) if value is not None else None


def score_for_candle(rows: Iterable[dict[str, Any]], timestamp: int) -> dict[str, Any] | None:
    """Return only the score computed for this candle, never a future row."""
    matches = [row for row in rows if int(row.get("candle_timestamp", -1)) == timestamp]
    return matches[-1] if matches else None


def _cooldown_remaining(item: VariantState, candle_timestamp: int,
                        timeframe_seconds: int) -> int:
    if item.last_add_candle is None:
        return 0
    elapsed = (candle_timestamp - item.last_add_candle) // timeframe_seconds
    return max(0, COOLDOWN_CANDLES - int(elapsed))


def _gate(item: VariantState, *, price: Decimal, score: dict[str, Any] | None,
          candle_timestamp: int, available_equity: Decimal,
          timeframe_seconds: int) -> tuple[bool, str, Decimal | None, int]:
    total = _score_total(score)
    cooldown = _cooldown_remaining(item, candle_timestamp, timeframe_seconds)
    if item.last_observed_candle == candle_timestamp:
        return False, "already_observed", total, cooldown
    if len(item.add_ons) >= MAX_ADDS:
        return False, "maximum_add_ons", total, cooldown
    # Exact no-averaging-down rule: current close must be strictly above the
    # weighted-average entry immediately before the prospective add-on.
    if price <= item.weighted_average_entry:
        return False, "position_not_profitable", total, cooldown
    if total is None:
        return False, "score_unavailable", total, cooldown
    if total < item.threshold:
        return False, "score_below_threshold", total, cooldown
    if _component(score, "trend") <= 0:
        return False, "trend_not_confirmed", total, cooldown
    if _component(score, "ema_alignment") <= 0:
        return False, "ema_alignment_not_confirmed", total, cooldown
    if _component(score, "adx") <= 0:
        return False, "adx_not_confirmed", total, cooldown
    if cooldown:
        return False, "cooldown", total, cooldown
    if item.total_cost_basis + price * ADD_QUANTITY > available_equity:
        return False, "insufficient_capital", total, cooldown
    return True, "eligible", total, cooldown


def _mark_excursion(item: VariantState, *, low: Decimal, high: Decimal,
                    close: Decimal) -> VariantState:
    if not item.add_ons:
        return item
    low_pnl = (low - item.weighted_average_entry) * item.quantity - item.total_entry_fees
    high_pnl = (high - item.weighted_average_entry) * item.quantity - item.total_entry_fees
    current = (close - item.weighted_average_entry) * item.quantity - item.total_entry_fees
    peak = max(item.peak_unrealized_pnl, high_pnl)
    drawdown = max(item.maximum_unrealized_drawdown, peak - current)
    return replace(item, peak_unrealized_pnl=peak,
                   maximum_unrealized_drawdown=drawdown,
                   mae=min(item.mae, low_pnl), mfe=max(item.mfe, high_pnl),
                   peak_exposure_pct=max(
                       item.peak_exposure_pct,
                       high * item.quantity / INITIAL_BALANCE * 100,
                   ))


def observe_pyramiding_shadow(
    state: PyramidingShadowState, *, candle: Candle,
    production_before: TradingControllerState,
    production_after: TradingControllerState,
    score: dict[str, Any] | None,
    production_net_pnl: Decimal | None = None,
    fee_rate: Decimal = D("0.001"), available_equity: Decimal | None = None,
    timeframe_seconds: int = 3600,
) -> PyramidingShadowUpdate:
    """Advance one closed candle using its close as the hypothetical fill."""
    opened = not production_before.has_open_position and production_after.has_open_position
    closed = production_before.has_open_position and not production_after.has_open_position
    current = state
    if not production_before.has_open_position and not production_after.has_open_position:
        current = PyramidingShadowState()
    if opened:
        current = _new_position(production_after, candle.timestamp, fee_rate)

    price, low, high = map(lambda x: D(str(x)), (candle.close, candle.low, candle.high))
    equity = available_equity if available_equity is not None else production_before.virtual_balance
    rows: list[dict[str, Any]] = []
    updated: list[VariantState] = []
    if production_before.has_open_position and current.variants:
        for original in current.variants:
            item = _mark_excursion(original, low=low, high=high, close=price)
            effective_score = None if closed else score
            allowed, reason, total, cooldown = _gate(
                item, price=price, score=effective_score, candle_timestamp=candle.timestamp,
                available_equity=equity, timeframe_seconds=timeframe_seconds,
            )
            if closed:
                reason = "production_exit"
            if allowed:
                notional = price * ADD_QUANTITY
                fee = notional * fee_rate
                quantity = item.quantity + ADD_QUANTITY
                cost = item.total_cost_basis + notional
                average = cost / quantity
                add = AddOn(candle.timestamp, price, ADD_QUANTITY, notional, fee,
                            average, quantity, cost, total or D("0"))
                item = replace(
                    item, quantity=quantity, total_cost_basis=cost,
                    weighted_average_entry=average,
                    total_entry_fees=item.total_entry_fees + fee,
                    added_notional=item.added_notional + notional,
                    maximum_total_notional=max(item.maximum_total_notional, cost),
                    maximum_total_quantity=max(item.maximum_total_quantity, quantity),
                    peak_exposure_pct=max(item.peak_exposure_pct,
                                          price * quantity / INITIAL_BALANCE * 100),
                    add_ons=item.add_ons + (add,), last_add_candle=candle.timestamp,
                    peak_unrealized_pnl=max(
                        item.peak_unrealized_pnl,
                        price * quantity - cost - item.total_entry_fees - fee,
                    ),
                )
                reason, cooldown = "added", COOLDOWN_CANDLES
            item = replace(item, last_observed_candle=candle.timestamp)
            current_value = price * item.quantity
            unrealized = current_value - item.total_cost_basis - item.total_entry_fees
            exit_fee = price * item.quantity * fee_rate if closed else None
            net = (price * item.quantity - item.total_cost_basis
                   - item.total_entry_fees - (exit_fee or D("0"))) if closed else None
            deployed = item.total_cost_basis + item.total_entry_fees
            delta = net - production_net_pnl if net is not None and production_net_pnl is not None else None
            rows.append({
                "threshold": str(item.threshold), "add_count": len(item.add_ons),
                "quantity": item.quantity, "total_cost_basis": item.total_cost_basis,
                "weighted_average_entry": item.weighted_average_entry,
                "total_entry_fees": item.total_entry_fees,
                "current_market_value": current_value, "unrealized_pnl": unrealized,
                "eligible": allowed, "decision_reason": reason, "score": total,
                "cooldown_remaining": cooldown, "initial_notional": item.initial_notional,
                "added_notional": item.added_notional,
                "maximum_total_notional": item.maximum_total_notional,
                "maximum_total_quantity": item.maximum_total_quantity,
                "peak_exposure_pct": item.peak_exposure_pct,
                "average_entries_after_adds": tuple(add.weighted_average_entry for add in item.add_ons),
                "add_ons": tuple(asdict(add) for add in item.add_ons),
                "maximum_unrealized_drawdown": item.maximum_unrealized_drawdown,
                "mae": item.mae, "mfe": item.mfe,
                "exit_fee": exit_fee, "net_pnl": net,
                "return_on_deployed_capital_pct": net / deployed * 100 if net is not None and deployed else None,
                "production_net_pnl": production_net_pnl if closed else None,
                "delta_pnl_vs_production": delta,
            })
            updated.append(item)
        current = replace(current, variants=tuple(updated))

    observation = {
        "research_only": True, "look_ahead": False,
        "execution_semantics": "fully_closed_candle_close",
        "candle_timestamp": candle.timestamp, "opened_at": current.opened_at,
        "entry_price": current.entry_price, "initial_quantity": current.initial_quantity,
        "variants": tuple(rows),
    }
    return PyramidingShadowUpdate(PyramidingShadowState() if closed else current, observation)


def reconcile_pyramiding_shadow(state: PyramidingShadowState, *,
        production: TradingControllerState, candles: Sequence[Candle],
        score_rows: Iterable[dict[str, Any]], fee_rate: Decimal = D("0.001"),
        timeframe_seconds: int = 3600) -> PyramidingShadowState:
    """Causally rebuild an already-open position after restart."""
    if not production.has_open_position or _matches(state, production):
        return state
    ordered = tuple(sorted(candles, key=lambda c: c.timestamp))
    if not ordered:
        raise ValueError("reconciliation requires historical candles")
    opened = int(datetime.fromisoformat(production.opened_at or "").timestamp())
    entry_candle = opened // timeframe_seconds * timeframe_seconds - timeframe_seconds
    if ordered[0].timestamp > entry_candle + timeframe_seconds:
        raise ValueError("historical candles do not cover production entry")
    current = _new_position(production, entry_candle, fee_rate)
    rows = tuple(score_rows)
    for candle in ordered:
        if entry_candle < candle.timestamp:
            current = observe_pyramiding_shadow(
                current, candle=candle, production_before=production,
                production_after=production, score=score_for_candle(rows, candle.timestamp),
                fee_rate=fee_rate, available_equity=production.virtual_balance,
                timeframe_seconds=timeframe_seconds,
            ).state
    return current


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, dict): return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [_jsonable(v) for v in value]
    return value


class PyramidingShadowStateStore:
    def __init__(self, path: str | Path): self.path = Path(path)
    def load(self) -> PyramidingShadowState:
        if not self.path.exists(): return PyramidingShadowState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        variants = []
        for raw in data.pop("variants", ()):
            adds = tuple(AddOn(**{**a, **{k: D(str(a[k])) for k in (
                "price", "quantity", "notional", "fee", "weighted_average_entry",
                "total_quantity", "total_exposure", "score")}}) for a in raw.pop("add_ons", ()))
            decimal_keys = ("threshold", "quantity", "total_cost_basis", "weighted_average_entry",
                "total_entry_fees", "initial_notional", "added_notional", "maximum_total_notional",
                "maximum_total_quantity", "peak_exposure_pct", "peak_unrealized_pnl",
                "maximum_unrealized_drawdown", "mae", "mfe")
            variants.append(VariantState(**{**raw, **{k: D(str(raw[k])) for k in decimal_keys}}, add_ons=adds))
        for key in ("entry_price", "initial_quantity"):
            if data.get(key) is not None: data[key] = D(str(data[key]))
        return PyramidingShadowState(**data, variants=tuple(variants))
    def save(self, state: PyramidingShadowState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(_jsonable(asdict(state)), indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)


class PyramidingShadowJournal:
    def __init__(self, path: str | Path): self.path = Path(path)
    def append(self, observation: dict[str, Any]) -> bool:
        identity = (observation["candle_timestamp"], observation.get("opened_at"))
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if (row.get("candle_timestamp"), row.get("opened_at")) == identity: return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(_jsonable(observation), handle, separators=(",", ":")); handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        return True


def aggregate_pyramiding_statistics(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for threshold in THRESHOLDS:
        key = str(threshold)
        history = [(row, v) for row in rows for v in row.get("variants", ()) if str(v.get("threshold")) == key]
        positions = {row.get("opened_at") for row, _ in history if row.get("opened_at")}
        closed = [v for _, v in history if v.get("net_pnl") is not None]
        deltas = [D(str(v["delta_pnl_vs_production"])) for v in closed if v.get("delta_pnl_vs_production") is not None]
        latest = {}
        for row, v in history:
            latest[row.get("opened_at")] = v
        add_counts = [int(v.get("add_count", 0)) for v in latest.values()]
        result[key] = {
            "positions_observed": len(positions), "positions_with_add_ons": sum(x > 0 for x in add_counts),
            "total_add_ons": sum(add_counts), "average_add_ons_per_position": D(sum(add_counts)) / len(positions) if positions else D("0"),
            "cumulative_pnl": sum((D(str(v["net_pnl"])) for v in closed), D("0")),
            "cumulative_delta_vs_production": sum(deltas, D("0")),
            "average_delta": sum(deltas, D("0")) / len(deltas) if deltas else D("0"),
            "median_delta": D(str(statistics.median(deltas))) if deltas else D("0"),
            "improved_trades": sum(x > 0 for x in deltas), "worsened_trades": sum(x < 0 for x in deltas),
            "maximum_observed_exposure": max((D(str(v.get("maximum_total_notional", 0))) for _, v in history), default=D("0")),
            "maximum_drawdown": max((D(str(v.get("maximum_unrealized_drawdown", 0))) for _, v in history), default=D("0")),
        }
    return result
