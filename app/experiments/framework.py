from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Iterable, Sequence
from uuid import uuid4

import pandas as pd

from app.candle import Candle
from app.experiments.registry import ExperimentDefinition, ExperimentRegistry

D = Decimal


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str; timeframe: int; candle_open_timestamp: int; candle_close_timestamp: int
    open: float; high: float; low: float; close: float; volume: float
    source: str; fetched_at: str; checksum: str

    @classmethod
    def from_candle(cls, candle: Candle, symbol: str, timeframe: int, source: str = "bybit_public"):
        raw = f"{symbol}|{timeframe}|{candle.timestamp}|{candle.open}|{candle.high}|{candle.low}|{candle.close}|{candle.volume}"
        return cls(symbol, timeframe, candle.timestamp, candle.timestamp + timeframe * 60,
                   candle.open, candle.high, candle.low, candle.close, candle.volume, source,
                   datetime.now(timezone.utc).isoformat(), hashlib.sha256(raw.encode()).hexdigest())


@dataclass(slots=True)
class ExperimentState:
    experiment_id: str; strategy_version: str; initial_balance: str = "1000"
    cash: str = "1000"; quantity: str = "0"; entry_price: str | None = None
    stop_price: str | None = None; entry_fee: str = "0"; opened_at: int | None = None
    last_candle_close: int | None = None; realised_pnl: str = "0"; total_fees: str = "0"
    peak_equity: str = "1000"; status: str = "initialized"; open_trade: dict | None = None
    skipped_minimum_order_count: int = 0


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
    finally: Path(name).unlink(missing_ok=True)


def load_state(spec: ExperimentDefinition) -> ExperimentState:
    if not spec.state_path.exists():
        initial = str(spec.initial_balance)
        return ExperimentState(spec.experiment_id, spec.strategy_version, initial, initial, peak_equity=initial)
    state = ExperimentState(**json.loads(spec.state_path.read_text(encoding="utf-8")))
    if (state.experiment_id, state.strategy_version) != (spec.experiment_id, spec.strategy_version):
        raise ValueError("state experiment/version mismatch")
    return state


class ConflictError(ValueError): pass


class CanonicalJsonl:
    _cache: dict[Path, tuple[int, int, list[dict]]] = {}
    def __init__(self, path: Path, key_fields: tuple[str, ...]): self.path, self.key_fields = path, key_fields
    def rows(self) -> list[dict]:
        if not self.path.exists(): return []
        stat = self.path.stat()
        cached = self._cache.get(self.path)
        if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return list(cached[2])
        rows = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]
        self._cache[self.path] = (stat.st_mtime_ns, stat.st_size, rows)
        return list(rows)
    def append(self, row: dict) -> bool:
        key = tuple(row.get(k) for k in self.key_fields)
        existing = self.rows()
        for old in existing:
            if tuple(old.get(k) for k in self.key_fields) == key:
                if old == row: return False
                raise ConflictError(f"canonical key conflict: {key}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        stat = self.path.stat()
        self._cache[self.path] = (stat.st_mtime_ns, stat.st_size, [*existing, row])
        return True


@dataclass(frozen=True, slots=True)
class Decision:
    action: str; signal: str; score: float | None; score_version: str | None
    reason_codes: tuple[str, ...]; hard_blocks: tuple[str, ...]; indicators: dict
    risk_fraction: float; stop_price: float | None


def decide(spec: ExperimentDefinition, history: Sequence[Candle]) -> Decision:
    if len(history) < 51:
        return Decision("HOLD", "insufficient_data", None, None, ("insufficient_data",), ("insufficient_data",), {}, 0, None)
    close = pd.Series([c.close for c in history], dtype=float)
    fast = close.ewm(span=20, adjust=False).mean(); slow = close.ewm(span=50, adjust=False).mean()
    f, s, pf, ps = map(float, (fast.iloc[-1], slow.iloc[-1], fast.iloc[-2], slow.iloc[-2]))
    price = history[-1].close; stop = price * 0.98
    cross_up, cross_down = pf <= ps and f > s, pf >= ps and f < s
    indicators = {"ema20": f, "ema50": s}
    if spec.strategy_version == "control_ema_cross_v1": enter = cross_up
    elif spec.strategy_version == "relaxed_ema_gate_v1": enter = f > s
    else:
        from app.signal_scoring import evaluate_signal
        from app.risk_allocation import risk_fraction
        scored = evaluate_signal(history); fraction = risk_fraction(scored.total_score)
        action = "ENTER" if scored.total_score >= 65 and not scored.hard_blocks else ("EXIT" if cross_down else "HOLD")
        return Decision(action, action.lower(), scored.total_score, scored.version, (action.lower(),), scored.hard_blocks, scored.indicators, fraction, stop if action == "ENTER" else None)
    action = "EXIT" if cross_down else ("ENTER" if enter else "HOLD")
    return Decision(action, action.lower(), None, None, ("ema_cross_down" if cross_down else "ema_entry_gate" if enter else "no_signal",), (), indicators, 1.0, stop if action == "ENTER" else None)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    state: ExperimentState; trade_event: dict | None; fee: Decimal; realised_pnl: Decimal
    unrealised_pnl: Decimal; equity: Decimal; execution_reason: str


class ExperimentPaperExecutor:
    def __init__(self, *, execution_mode: str = "paper_research", fee_rate: Decimal = D("0.001"), risk_per_trade: Decimal = D("0.01"), capital_cap: Decimal = D("1"), minimum_notional: Decimal = D("5")):
        if execution_mode != "paper_research": raise ValueError("real mode is forbidden")
        self.fee_rate, self.risk_per_trade, self.capital_cap, self.minimum_notional = fee_rate, risk_per_trade, capital_cap, minimum_notional

    def execute(self, spec: ExperimentDefinition, state: ExperimentState, decision: Decision, snapshot: MarketSnapshot) -> ExecutionResult:
        price, high, low = map(D, map(str, (snapshot.close, snapshot.high, snapshot.low)))
        cash, qty = D(state.cash), D(state.quantity); fee = pnl = D("0"); event = None; reason = "hold"
        # Stops are evaluated causally on each closed candle, before a signal exit.
        exit_price = None; exit_reason = None
        if qty > 0 and state.stop_price is not None and low <= D(state.stop_price): exit_price, exit_reason = D(state.stop_price), "stop_loss"
        elif qty > 0 and decision.action == "EXIT": exit_price, exit_reason = price, "signal"
        if exit_price is not None:
            proceeds = qty * exit_price; fee = proceeds * self.fee_rate; entry = D(state.entry_price or "0")
            gross = (exit_price-entry)*qty; pnl = gross-D(state.entry_fee)-fee; cash += proceeds-fee
            opened = state.open_trade or {}; event = {**opened, "experiment_id": spec.experiment_id, "strategy_version": spec.strategy_version,
                "exit_timestamp": snapshot.candle_close_timestamp, "exit_price": str(exit_price), "exit_fee": str(fee), "total_fees": str(D(state.entry_fee)+fee),
                "exit_reason": exit_reason, "realised_pnl": str(pnl), "return_percentage": str(pnl/(entry*qty)*100 if entry*qty else 0),
                "holding_time": snapshot.candle_close_timestamp-int(state.opened_at or snapshot.candle_close_timestamp), "bars_held": opened.get("bars_held", 0)}
            qty=D("0"); state.entry_price=state.stop_price=None; state.entry_fee="0"; state.opened_at=None; state.open_trade=None; reason=exit_reason
        if qty == 0 and decision.action == "ENTER":
            if decision.stop_price is None: raise ValueError("stop-loss required")
            stop=D(str(decision.stop_price)); risk_cash=D(state.cash)*self.risk_per_trade*D(str(decision.risk_fraction)); raw=risk_cash/(price-stop)
            quantity=min(raw, D(state.cash)*self.capital_cap/(price*(D("1")+self.fee_rate)))
            notional=quantity*price; entry_fee=notional*self.fee_rate
            if quantity <= 0 or notional < self.minimum_notional: state.skipped_minimum_order_count += 1; reason="minimum_order"
            elif notional+entry_fee > D(state.cash): reason="insufficient_balance"
            else:
                cash=D(state.cash)-notional-entry_fee; qty=quantity; fee=entry_fee; state.entry_price=str(price); state.stop_price=str(stop); state.entry_fee=str(entry_fee); state.opened_at=snapshot.candle_close_timestamp
                state.open_trade={"trade_id":str(uuid4()),"symbol":spec.symbol,"side":"LONG","entry_timestamp":snapshot.candle_close_timestamp,"entry_price":str(price),"quantity":str(qty),"notional":str(notional),"entry_fee":str(entry_fee),"stop_price":str(stop),"entry_score":decision.score,"entry_reason":";".join(decision.reason_codes),"market_regime":None,"setup_type":None,"lifecycle_stage":None,"MFE":"0","MAE":"0","maximum_unrealised_profit":"0","maximum_unrealised_loss":"0","bars_held":0}
                reason="entered"
        if qty > 0 and state.open_trade:
            entry=D(state.entry_price or "0"); mfe=max(D(state.open_trade.get("MFE","0")),(high-entry)*qty); mae=min(D(state.open_trade.get("MAE","0")),(low-entry)*qty)
            state.open_trade.update(MFE=str(mfe), MAE=str(mae), maximum_unrealised_profit=str(mfe), maximum_unrealised_loss=str(mae), bars_held=int(state.open_trade.get("bars_held",0))+1)
        unreal=(price-D(state.entry_price or price))*qty if qty else D("0"); equity=cash+qty*price
        state.cash=str(cash); state.quantity=str(qty); state.realised_pnl=str(D(state.realised_pnl)+pnl); state.total_fees=str(D(state.total_fees)+fee); state.peak_equity=str(max(D(state.peak_equity),equity))
        return ExecutionResult(state,event,fee,pnl,unreal,equity,reason)


def process_experiment(spec: ExperimentDefinition, snapshot: MarketSnapshot, history: Sequence[Candle]) -> dict:
    state=load_state(spec)
    if state.last_candle_close is not None and snapshot.candle_close_timestamp <= state.last_candle_close:
        if snapshot.candle_close_timestamp < state.last_candle_close: raise ValueError("out-of-order candle")
        return {"experiment_id":spec.experiment_id,"status":"waiting","processed":False,"candle_close_timestamp":snapshot.candle_close_timestamp}
    decision=decide(spec,history); result=ExperimentPaperExecutor().execute(spec,state,decision,snapshot); now=datetime.now(timezone.utc).isoformat()
    decision_row={"experiment_id":spec.experiment_id,"strategy_version":spec.strategy_version,"candle_close_timestamp":snapshot.candle_close_timestamp,"market_checksum":snapshot.checksum,"decision":decision.action,"signal":decision.signal,"score":decision.score,"score_version":decision.score_version,"reason_codes":decision.reason_codes,"hard_blocks":decision.hard_blocks,"market_regime":None,"setup_type":None,"lifecycle_stage":None,"indicators":decision.indicators,"risk_fraction":decision.risk_fraction,"allowed_monetary_risk":str(D(result.state.cash)*D("0.01")*D(str(decision.risk_fraction))),"final_position_size":result.state.quantity,"stop_distance":str(D(str(snapshot.close))-D(str(decision.stop_price))) if decision.stop_price else None,"current_balance":result.state.cash,"current_position":"LONG" if D(result.state.quantity)>0 else "FLAT","created_at":now}
    CanonicalJsonl(spec.decision_path,("experiment_id","strategy_version","candle_close_timestamp")).append(decision_row)
    if result.trade_event: CanonicalJsonl(spec.journal_path,("experiment_id","trade_id")).append(result.trade_event)
    peak=D(result.state.peak_equity); drawdown=(peak-result.equity)/peak*100 if peak else D("0")
    equity_row={"experiment_id":spec.experiment_id,"strategy_version":spec.strategy_version,"candle_close_timestamp":snapshot.candle_close_timestamp,"cash":result.state.cash,"position_market_value":str(D(result.state.quantity)*D(str(snapshot.close))),"equity":str(result.equity),"realised_pnl":result.state.realised_pnl,"unrealised_pnl":str(result.unrealised_pnl),"total_pnl":str(result.equity-D(result.state.initial_balance)),"drawdown":str(drawdown),"snapshot_reason":"cycle","created_at":now}
    CanonicalJsonl(spec.equity_path,("experiment_id","strategy_version","candle_close_timestamp")).append(equity_row)
    result.state.last_candle_close=snapshot.candle_close_timestamp; result.state.status="running"; _atomic_json(spec.state_path,asdict(result.state))
    return {"experiment_id":spec.experiment_id,"status":"running","processed":True,"candle_close_timestamp":snapshot.candle_close_timestamp,"decision":decision.action,"trade_event":result.trade_event,"equity":str(result.equity)}


class ExperimentCoordinator:
    def __init__(self, registry: ExperimentRegistry): self.registry=registry
    def run(self, candles: Sequence[Candle]) -> list[dict]:
        if not candles: return []
        ordered=tuple(sorted(candles,key=lambda c:c.timestamp)); latest=ordered[-1]; results=[]
        enabled=[s for s in self.registry.all() if s.enabled]
        for spec in enabled:
            snap=MarketSnapshot.from_candle(latest,spec.symbol,spec.timeframe)
            try: results.append(process_experiment(spec,snap,ordered))
            except Exception as exc: results.append({"experiment_id":spec.experiment_id,"status":"error","error":type(exc).__name__,"candle_close_timestamp":snap.candle_close_timestamp})
        timestamps={r["candle_close_timestamp"] for r in results}
        if len(timestamps)>1: raise RuntimeError("mismatched candle timestamp")
        return results
