"""Independent research-only Strategy V2 virtual trading account.

One call consumes one fully closed hourly candle.  Stops stored before that
candle may fill intrabar; levels derived from its high or close become active
only on the next call.  The module has no production execution dependency.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from app.candle import Candle

D = Decimal
INITIAL_BALANCE = D("1000")
FEE_RATE = D("0.001")
ENTRY_QUANTITY = D("0.01")
MAX_ADDS = 3
MAX_QUANTITY = D("0.04")
COOLDOWN_CANDLES = 3
ENTRY_THRESHOLD = D("65")
ADD_THRESHOLD = D("70")
HARD_STOP_PCT = D("0.02")
PROFIT_ACTIVATION_PCT = D("0.005")
PROFIT_BUFFER = D("0.001")
TRAILING_ACTIVATION_PCT = D("0.05")
TRAILING_DISTANCE = D("0.05")


def _now(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _component(score: dict[str, Any] | None, name: str) -> D:
    source = (score or {}).get("components") or (score or {}).get("score_components") or {}
    value = source.get(name, source.get(f"{name}_score", 0))
    if isinstance(value, dict):
        value = value.get("weighted_score", value.get("score", 0))
    return D(str(value or 0))


def _total(score: dict[str, Any] | None) -> D | None:
    value = (score or {}).get("score_total", (score or {}).get("signal_score", (score or {}).get("score")))
    return None if value is None else D(str(value))


def _decision(score: dict[str, Any] | None) -> str:
    return str((score or {}).get("decision", (score or {}).get("action", "HOLD"))).upper()


def score_for_candle(rows: Iterable[dict[str, Any]], timestamp: int) -> dict[str, Any] | None:
    matches = [row for row in rows if int(row.get("candle_timestamp", -1)) == timestamp]
    return matches[-1] if matches else None


@dataclass(slots=True)
class StrategyV2State:
    cash: D = INITIAL_BALANCE
    equity: D = INITIAL_BALANCE
    quantity: D = D("0")
    cost_basis: D = D("0")
    weighted_average_entry: D | None = None
    add_count: int = 0
    peak: D | None = None
    hard_stop: D | None = None
    profit_active: bool = False
    trailing_active: bool = False
    profit_floor: D | None = None
    trailing_floor: D | None = None
    effective_floor: D | None = None
    last_entry_timestamp: int | None = None
    last_add_timestamp: int | None = None
    last_processed_timestamp: int | None = None
    last_score: D | None = None
    realised_pnl: D = D("0")
    unrealised_pnl: D = D("0")
    fees: D = D("0")
    entry_fees: D = D("0")
    closed_trades: int = 0
    winning_trades: int = 0
    gross_profit: D = D("0")
    gross_loss: D = D("0")
    max_equity: D = INITIAL_BALANCE
    max_drawdown: D = D("0")
    exposure_sum: D = D("0")
    exposure_samples: int = 0
    current_trade: dict[str, Any] | None = None

    @property
    def is_long(self) -> bool:
        return self.quantity > 0


_DECIMAL_FIELDS = {
    "cash", "equity", "quantity", "cost_basis", "weighted_average_entry",
    "peak", "hard_stop", "profit_floor", "trailing_floor", "effective_floor",
    "realised_pnl", "unrealised_pnl", "fees", "entry_fees", "gross_profit",
    "gross_loss", "max_equity", "max_drawdown", "exposure_sum", "last_score",
}


class StrategyV2StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> StrategyV2State:
        if not self.path.exists():
            return StrategyV2State()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for key in _DECIMAL_FIELDS:
            if payload.get(key) is not None:
                payload[key] = D(str(payload[key]))
        return StrategyV2State(**payload)

    def save(self, state: StrategyV2State) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(state)
        for key in _DECIMAL_FIELDS:
            if payload.get(key) is not None:
                payload[key] = str(payload[key])
        descriptor, name = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


class StrategyV2Journal:
    def __init__(self, path: Path):
        self.path = path

    def append(self, record: dict[str, Any]) -> bool:
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip() and json.loads(line).get("candle_timestamp") == record["candle_timestamp"]:
                    return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, separators=(",", ":"), default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True


def _mark(state: StrategyV2State, price: D) -> None:
    state.unrealised_pnl = price * state.quantity - state.cost_basis - state.entry_fees if state.is_long else D("0")
    state.equity = state.cash + price * state.quantity
    state.max_equity = max(state.max_equity, state.equity)
    if state.max_equity:
        state.max_drawdown = max(state.max_drawdown, (state.max_equity - state.equity) / state.max_equity * 100)
    exposure = price * state.quantity
    state.exposure_sum += exposure
    state.exposure_samples += 1


def _buy(state: StrategyV2State, price: D, timestamp: int, score: D, *, add: bool) -> None:
    notional = price * ENTRY_QUANTITY
    fee = notional * FEE_RATE
    if state.cash < notional + fee:
        raise ValueError("insufficient Strategy V2 cash")
    old_average = state.weighted_average_entry
    state.cash -= notional + fee
    state.quantity += ENTRY_QUANTITY
    state.cost_basis += notional
    state.entry_fees += fee
    state.fees += fee
    state.weighted_average_entry = state.cost_basis / state.quantity
    state.hard_stop = state.weighted_average_entry * (D("1") - HARD_STOP_PCT)
    fill = {"timestamp": timestamp, "price": str(price), "quantity": str(ENTRY_QUANTITY), "fee": str(fee), "score": str(score), "weighted_average_entry": str(state.weighted_average_entry)}
    if not add:
        state.last_entry_timestamp = timestamp
        state.last_add_timestamp = timestamp
        state.peak = price
        state.current_trade = {"opened_at": _now(timestamp), "initial_entry": fill, "add_ons": [], "weighted_average_progression": [str(state.weighted_average_entry)], "mfe": "0", "mae": "0", "max_exposure": str(notional)}
    else:
        state.add_count += 1
        state.last_add_timestamp = timestamp
        assert state.current_trade is not None
        state.current_trade["add_ons"].append(fill)
        state.current_trade["weighted_average_progression"].append(str(state.weighted_average_entry))
        state.current_trade["max_exposure"] = str(max(D(state.current_trade["max_exposure"]), state.cost_basis))
        # Existing protection remains monotonic, but any newly calculated level
        # is based on the new average and cannot be tested until the next call.
        if state.profit_active:
            be = state.weighted_average_entry * (D("1") + FEE_RATE) / (D("1") - FEE_RATE)
            state.profit_floor = max(state.profit_floor or D("0"), be * (D("1") + PROFIT_BUFFER))
            state.effective_floor = max(state.effective_floor or D("0"), state.profit_floor)


def _close(state: StrategyV2State, price: D, timestamp: int, reason: str) -> dict[str, Any]:
    quantity, basis, entry_fees = state.quantity, state.cost_basis, state.entry_fees
    exit_fee = price * quantity * FEE_RATE
    net = price * quantity - basis - entry_fees - exit_fee
    state.cash += price * quantity - exit_fee
    state.fees += exit_fee
    state.realised_pnl += net
    state.closed_trades += 1
    if net > 0:
        state.winning_trades += 1
        state.gross_profit += net
    elif net < 0:
        state.gross_loss += net
    trade = dict(state.current_trade or {})
    opened = datetime.fromisoformat(trade["opened_at"])
    trade.update({"closed_at": _now(timestamp), "final_quantity": str(quantity), "exit_price": str(price), "exit_reason": reason, "entry_fees": str(entry_fees), "exit_fee": str(exit_fee), "fees": str(entry_fees + exit_fee), "net_pnl": str(net), "return_pct": str(net / (basis + entry_fees) * 100), "hold_seconds": int(datetime.fromtimestamp(timestamp, timezone.utc).timestamp() - opened.timestamp())})
    state.quantity = state.cost_basis = state.entry_fees = D("0")
    state.weighted_average_entry = state.peak = state.hard_stop = None
    state.profit_floor = state.trailing_floor = state.effective_floor = None
    state.profit_active = state.trailing_active = False
    state.add_count = 0
    state.current_trade = None
    return trade


def process_candle(state: StrategyV2State, *, candle: Candle, score: dict[str, Any] | None, bearish_ema_cross: bool = False, timeframe_seconds: int = 3600) -> tuple[StrategyV2State, dict[str, Any]]:
    """Advance independent V2 by one closed candle; mutates and returns state."""
    ts = int(candle.timestamp)
    if state.last_processed_timestamp is not None and ts <= state.last_processed_timestamp:
        return state, {"candle_timestamp": ts, "event": "already_processed", "appended": False}
    close, low, high = D(str(candle.close)), D(str(candle.low)), D(str(candle.high))
    total = _total(score)
    state.last_score = total
    event, reason, closed_trade = "hold", None, None

    # Only pre-candle levels participate in intrabar fills.
    if state.is_long:
        protective = state.effective_floor
        if protective is not None and low <= protective:
            event, reason = "exit", "protective_floor"
            closed_trade = _close(state, protective, ts, reason)
        elif state.hard_stop is not None and low <= state.hard_stop:
            event, reason = "exit", "hard_stop"
            closed_trade = _close(state, state.hard_stop, ts, reason)
        elif bearish_ema_cross:
            event, reason = "exit", "ema_reversal"
            closed_trade = _close(state, close, ts, reason)

    if state.is_long:
        avg = state.weighted_average_entry
        assert avg is not None and state.current_trade is not None
        state.peak = max(state.peak or high, high)
        mfe = (high - avg) * state.quantity - state.entry_fees
        mae = (low - avg) * state.quantity - state.entry_fees
        state.current_trade["mfe"] = str(max(D(state.current_trade["mfe"]), mfe))
        state.current_trade["mae"] = str(min(D(state.current_trade["mae"]), mae))
        if state.peak >= avg * (D("1") + PROFIT_ACTIVATION_PCT):
            state.profit_active = True
            be = avg * (D("1") + FEE_RATE) / (D("1") - FEE_RATE)
            state.profit_floor = max(state.profit_floor or D("0"), be * (D("1") + PROFIT_BUFFER))
        if state.peak >= avg * (D("1") + TRAILING_ACTIVATION_PCT):
            state.trailing_active = True
            state.trailing_floor = max(state.trailing_floor or D("0"), state.peak * (D("1") - TRAILING_DISTANCE))
        candidates = [value for value in (state.profit_floor, state.trailing_floor) if value is not None]
        if candidates:
            state.effective_floor = max([state.effective_floor or D("0"), *candidates])

        cooldown_ok = state.last_add_timestamp is None or ts - state.last_add_timestamp >= COOLDOWN_CANDLES * timeframe_seconds
        add_ok = (total is not None and total >= ADD_THRESHOLD and _component(score, "trend") > 0 and _component(score, "ema_alignment") > 0 and _component(score, "adx") > 0 and close > avg and cooldown_ok and state.add_count < MAX_ADDS and state.quantity + ENTRY_QUANTITY <= MAX_QUANTITY and state.cash >= close * ENTRY_QUANTITY * (D("1") + FEE_RATE))
        if add_ok:
            _buy(state, close, ts, total, add=True)
            event, reason = "add", "scored70"
    elif event != "exit":
        entry_ok = (_decision(score) == "ENTER_LONG" and total is not None and total >= ENTRY_THRESHOLD and _component(score, "trend") > 0 and _component(score, "ema_alignment") > 0 and _component(score, "adx") > 0 and state.cash >= close * ENTRY_QUANTITY * (D("1") + FEE_RATE))
        if entry_ok:
            _buy(state, close, ts, total, add=False)
            event, reason = "entry", "scored65"

    _mark(state, close)
    state.last_processed_timestamp = ts
    record = {"strategy": "strategy_v2_shadow", "research_only": True, "candle_timestamp": ts, "event": event, "reason": reason, "close": str(close), "score": None if total is None else str(total), "cash": str(state.cash), "equity": str(state.equity), "quantity": str(state.quantity), "weighted_average_entry": None if state.weighted_average_entry is None else str(state.weighted_average_entry), "add_count": state.add_count, "peak": None if state.peak is None else str(state.peak), "hard_stop": None if state.hard_stop is None else str(state.hard_stop), "profit_floor": None if state.profit_floor is None else str(state.profit_floor), "trailing_floor": None if state.trailing_floor is None else str(state.trailing_floor), "effective_floor": None if state.effective_floor is None else str(state.effective_floor), "realised_pnl": str(state.realised_pnl), "unrealised_pnl": str(state.unrealised_pnl), "fees": str(state.fees), "closed_trades": state.closed_trades, "max_drawdown_pct": str(state.max_drawdown), "closed_trade": closed_trade, "causal_semantics": "pre_candle_floor_then_ema_then_high_for_next_candle_then_close_fill"}
    return state, record


def metrics(state: StrategyV2State) -> dict[str, Any]:
    losses = abs(state.gross_loss)
    return {"equity": state.equity, "realised_pnl": state.realised_pnl, "max_drawdown_pct": state.max_drawdown, "closed_trades": state.closed_trades, "win_rate_pct": D(state.winning_trades) / state.closed_trades * 100 if state.closed_trades else D("0"), "profit_factor": state.gross_profit / losses if losses else None, "average_trade": state.realised_pnl / state.closed_trades if state.closed_trades else D("0"), "average_exposure": state.exposure_sum / state.exposure_samples if state.exposure_samples else D("0")}


def comparison(state: StrategyV2State, *, production_equity: D, production_realised_pnl: D, production_max_drawdown_pct: D = D("0"), production_closed_trades: int = 0) -> dict[str, Any]:
    return {"production": {"equity": production_equity, "realised_pnl": production_realised_pnl, "max_drawdown_pct": production_max_drawdown_pct, "closed_trades": production_closed_trades}, "strategy_v2": metrics(state), "delta": {"equity": state.equity - production_equity, "pnl": state.realised_pnl - production_realised_pnl, "max_drawdown_pct": state.max_drawdown - production_max_drawdown_pct}}
