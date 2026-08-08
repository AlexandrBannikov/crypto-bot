"""Observation-only break-even lifecycle for an existing production LONG.

The observer never emits a trading signal and never mutates controller state.
It records what an unconditional +1% break-even exit would have done using
only fully closed candles.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Literal

from app.candle import Candle
from app.trade_accounting import calculate_long_trade_accounting
from app.trading_controller import TradingControllerState


D = Decimal
BreakEvenShadowStatus = Literal["inactive", "armed", "triggered"]


@dataclass(frozen=True, slots=True)
class BreakEvenShadowState:
    be_shadow_status: BreakEvenShadowStatus = "inactive"
    entry_price: Decimal | None = None
    quantity: Decimal | None = None
    activation_price: Decimal | None = None
    protective_price: Decimal | None = None
    entry_candle: int | None = None
    armed_at_candle: int | None = None
    triggered_at_candle: int | None = None
    hypothetical_exit_price: Decimal | None = None
    hypothetical_pnl: Decimal | None = None


@dataclass(frozen=True, slots=True)
class BreakEvenShadowObservation:
    candle_timestamp: int
    be_shadow_status: BreakEvenShadowStatus
    activation_price: Decimal | None
    protective_price: Decimal | None
    armed_at_candle: int | None
    triggered_at_candle: int | None
    hypothetical_exit_price: Decimal | None
    hypothetical_pnl: Decimal | None
    saved_loss: bool | None = None
    worsened_winner: bool | None = None
    production_exit_pnl: Decimal | None = None


@dataclass(frozen=True, slots=True)
class BreakEvenShadowUpdate:
    state: BreakEvenShadowState
    observation: BreakEvenShadowObservation


def protective_price(entry_price: Decimal, fee_rate: Decimal) -> Decimal:
    """Return the exit price whose net PnL is exactly zero."""
    if entry_price <= 0 or fee_rate < 0 or fee_rate >= 1:
        raise ValueError("invalid break-even price inputs")
    return entry_price * (D("1") + fee_rate) / (D("1") - fee_rate)


def observe_break_even_shadow(
    state: BreakEvenShadowState,
    *,
    candle: Candle,
    production_before: TradingControllerState,
    production_after: TradingControllerState,
    fee_rate: Decimal = D("0.001"),
    production_exit_pnl: Decimal | None = None,
) -> BreakEvenShadowUpdate:
    """Advance shadow state without changing either production snapshot."""
    current = state
    opened = (
        not production_before.has_open_position
        and production_after.has_open_position
    )
    was_open = production_before.has_open_position
    closed = was_open and not production_after.has_open_position

    # Production is authoritative.  This repairs a stale shadow lifecycle on
    # the first successful cycle after a failed exit/reset persistence write.
    if not production_before.has_open_position and not production_after.has_open_position:
        current = BreakEvenShadowState()

    if opened:
        assert production_after.entry_price is not None
        entry = production_after.entry_price
        current = BreakEvenShadowState(
            entry_price=entry,
            quantity=production_after.position_quantity,
            activation_price=entry * D("1.01"),
            protective_price=protective_price(entry, fee_rate),
            entry_candle=candle.timestamp,
        )
    elif was_open and current.entry_price is not None:
        if (
            current.be_shadow_status == "armed"
            and current.armed_at_candle is not None
            and candle.timestamp > current.armed_at_candle
            and D(str(candle.low)) <= current.protective_price
        ):
            assert current.quantity is not None
            assert current.protective_price is not None
            accounting = calculate_long_trade_accounting(
                current.entry_price,
                current.protective_price,
                current.quantity,
                fee_rate,
            )
            hypothetical_pnl = accounting.net_pnl
            if abs(hypothetical_pnl) < D("1e-18"):
                hypothetical_pnl = D("0")
            current = BreakEvenShadowState(
                **{
                    **asdict(current),
                    "be_shadow_status": "triggered",
                    "triggered_at_candle": candle.timestamp,
                    "hypothetical_exit_price": current.protective_price,
                    "hypothetical_pnl": hypothetical_pnl,
                }
            )
        elif (
            current.be_shadow_status == "inactive"
            and current.entry_candle is not None
            and candle.timestamp > current.entry_candle
            and D(str(candle.high)) >= current.activation_price
        ):
            current = BreakEvenShadowState(
                **{
                    **asdict(current),
                    "be_shadow_status": "armed",
                    "armed_at_candle": candle.timestamp,
                }
            )

    saved_loss = worsened_winner = None
    snapshot = current
    if closed:
        if current.hypothetical_pnl is not None and production_exit_pnl is not None:
            saved_loss = production_exit_pnl < 0 <= current.hypothetical_pnl
            worsened_winner = (
                production_exit_pnl > 0
                and production_exit_pnl > current.hypothetical_pnl
            )
        current = BreakEvenShadowState()

    observation = BreakEvenShadowObservation(
        candle_timestamp=candle.timestamp,
        be_shadow_status=snapshot.be_shadow_status,
        activation_price=snapshot.activation_price,
        protective_price=snapshot.protective_price,
        armed_at_candle=snapshot.armed_at_candle,
        triggered_at_candle=snapshot.triggered_at_candle,
        hypothetical_exit_price=snapshot.hypothetical_exit_price,
        hypothetical_pnl=snapshot.hypothetical_pnl,
        saved_loss=saved_loss,
        worsened_winner=worsened_winner,
        production_exit_pnl=production_exit_pnl if closed else None,
    )
    return BreakEvenShadowUpdate(current, observation)


class BreakEvenShadowStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> BreakEvenShadowState:
        if not self.path.exists():
            return BreakEvenShadowState()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for key in (
            "entry_price", "quantity", "activation_price", "protective_price",
            "hypothetical_exit_price", "hypothetical_pnl",
        ):
            if payload.get(key) is not None:
                payload[key] = D(str(payload[key]))
        return BreakEvenShadowState(**payload)

    def save(self, state: BreakEvenShadowState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(state)
        for key, value in tuple(payload.items()):
            if isinstance(value, D):
                payload[key] = str(value)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


class BreakEvenShadowJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, observation: BreakEvenShadowObservation) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._last_candle_timestamp() == observation.candle_timestamp:
            return False
        payload = asdict(observation)
        for key, value in tuple(payload.items()):
            if isinstance(value, D):
                payload[key] = str(value)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True

    def _last_candle_timestamp(self) -> int | None:
        if not self.path.exists():
            return None
        raw_lines = self.path.read_bytes().splitlines(keepends=True)
        valid_size = 0
        last_timestamp = None
        for index, raw_line in enumerate(raw_lines):
            try:
                if raw_line.strip():
                    payload = json.loads(raw_line)
                    last_timestamp = int(payload["candle_timestamp"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                if index != len(raw_lines) - 1:
                    raise ValueError(
                        f"corrupt break-even shadow journal line {index + 1}"
                    ) from exc
                with self.path.open("r+b") as handle:
                    handle.truncate(valid_size)
                break
            valid_size += len(raw_line)
        return last_timestamp
