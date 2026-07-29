from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Sequence

import pandas as pd

from app.candle import Candle
from app.execution_runner import ExecutionRunner
from app.indicators import adx, ema
from app.paper_executor import PaperExecutor
from app.strategy_v2_relaxed import (
    RelaxedPullbackConfig,
    RelaxedPullbackMode,
    confirms_pullback,
)
from app.trade_journal import JsonlTradeJournal
from app.trading_controller import TradingController, TradingControllerState
from app.trading_runtime import TradingRuntime
from app.trading_types import TradeAction


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    symbol: str = "ETHUSDT"
    timeframe: str = "60"
    fast_ema: int = 20
    slow_ema: int = 50
    adx_period: int = 14
    adx_minimum: float = 20.0
    max_wait_bars: int = 8
    tolerance: float = 0.005
    retrace_pct: float = 0.0075
    fee_rate: Decimal = Decimal("0.001")
    entry_quantity: Decimal = Decimal("0.01")
    initial_balance: Decimal = Decimal("1000")

    @property
    def pullback(self) -> RelaxedPullbackConfig:
        return RelaxedPullbackConfig(
            RelaxedPullbackMode.HYBRID,
            self.max_wait_bars,
            tolerance=self.tolerance,
            retrace_pct=self.retrace_pct,
        )


@dataclass(slots=True)
class CandidateState:
    controller: TradingControllerState = field(
        default_factory=TradingControllerState
    )
    last_processed_candle: int | None = None
    baseline_candle: int | None = None
    pending_cross_timestamp: int | None = None
    pending_cross_price: float | None = None
    bars_waited: int = 0
    signals: int = 0
    entries: int = 0
    exits: int = 0
    pullback_confirmations: int = 0
    total_pullback_wait_bars: int = 0
    timed_out: int = 0
    cancelled: int = 0
    active_halt: str | None = None


class CandidateStateStore:
    def __init__(self, path: Path, *, initial_balance: Decimal = Decimal("1000")):
        self.path = path
        self.initial_balance = initial_balance

    def load(self) -> CandidateState:
        if not self.path.exists():
            return CandidateState(
                controller=TradingControllerState(
                    virtual_balance=self.initial_balance
                )
            )
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            raw_controller = payload.pop("controller")
            controller = TradingControllerState(
                position_quantity=Decimal(raw_controller["position_quantity"]),
                entry_price=_decimal_or_none(raw_controller["entry_price"]),
                stop_loss=_decimal_or_none(raw_controller["stop_loss"]),
                virtual_balance=Decimal(raw_controller["virtual_balance"]),
                total_fees=Decimal(raw_controller["total_fees"]),
                realized_pnl=Decimal(raw_controller["realized_pnl"]),
                closed_trades=int(raw_controller["closed_trades"]),
                entry_fee=Decimal(raw_controller["entry_fee"]),
                opened_at=raw_controller.get("opened_at"),
            )
            return CandidateState(controller=controller, **payload)
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid candidate state: {exc}") from exc

    def save(self, state: CandidateState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        controller = asdict(state.controller)
        for key, value in controller.items():
            if isinstance(value, Decimal):
                controller[key] = str(value)
        payload = asdict(state)
        payload["controller"] = controller
        descriptor, name = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
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


def _decimal_or_none(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class CandidateDecisionJournal:
    def __init__(self, path: Path):
        self.path = path

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")


def ensure_paper_only(environ: dict[str, str] | None = None) -> None:
    raw = (environ or os.environ).get("LIVE_TRADING_ENABLED", "false")
    if raw.strip().lower() not in {"0", "false", "no", "off"}:
        raise RuntimeError(
            "candidate refuses to start: LIVE_TRADING_ENABLED must be false"
        )


def _features(candles: Sequence[Candle], config: CandidateConfig) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    )
    frame["ema20"] = ema(frame["close"], config.fast_ema)
    frame["ema50"] = ema(frame["close"], config.slow_ema)
    frame["adx"] = adx(frame[["high", "low", "close"]], config.adx_period)
    return frame


def process_candidate_candles(
    candles: Sequence[Candle],
    *,
    state_store: CandidateStateStore,
    trade_journal_path: Path,
    decision_journal_path: Path,
    config: CandidateConfig = CandidateConfig(),
) -> CandidateState:
    ensure_paper_only()
    if len(candles) < config.slow_ema + 2:
        raise RuntimeError("insufficient closed candle history for candidate")
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    state = state_store.load()
    latest = ordered[-1]
    if state.last_processed_candle is None:
        state.last_processed_candle = latest.timestamp
        state.baseline_candle = latest.timestamp
        state.active_halt = None
        state_store.save(state)
        return state

    new_candles = [
        candle for candle in ordered
        if candle.timestamp > state.last_processed_candle
    ]
    if not new_candles:
        return state

    runtime = TradingRuntime(ExecutionRunner(PaperExecutor(), allow_live=False))
    decision_journal = CandidateDecisionJournal(decision_journal_path)
    for candle in new_candles:
        causal = tuple(c for c in ordered if c.timestamp <= candle.timestamp)
        frame = _features(causal, config)
        row = frame.iloc[-1]
        previous = frame.iloc[-2]
        fast = float(row["ema20"])
        slow = float(row["ema50"])
        adx_value = float(row["adx"])
        if not all(math.isfinite(value) for value in (fast, slow, adx_value)):
            raise RuntimeError("candidate indicators are not finite")
        cross_up = bool(previous["ema20"] <= previous["ema50"] and fast > slow)
        cross_down = bool(previous["ema20"] >= previous["ema50"] and fast < slow)
        low_touch = candle.low <= fast
        close_near = abs(candle.close - fast) / fast <= config.tolerance
        retraced = (
            state.pending_cross_price is not None
            and (state.pending_cross_price - candle.close)
            / state.pending_cross_price
            >= config.retrace_pct
        )
        decision = "HOLD"
        reason = "no new EMA event"
        action = TradeAction.HOLD
        allowed = False
        blocked = False
        decision_bars_waited = state.bars_waited

        if cross_down:
            if state.pending_cross_timestamp is not None:
                state.cancelled += 1
                decision = "CANCEL_PULLBACK"
                reason = "EMA20 crossed below EMA50; pending pullback cancelled"
                _clear_pending(state)
            if state.controller.has_open_position:
                decision = "EXIT"
                reason = "EMA cross down; exits are not filtered"
                action = TradeAction.CLOSE_LONG
                allowed = True
                state.exits += 1
        elif cross_up and not state.controller.has_open_position:
            state.signals += 1
            state.pending_cross_timestamp = candle.timestamp
            state.pending_cross_price = candle.close
            state.bars_waited = 0
            decision = "WAIT_PULLBACK"
            reason = "EMA cross up detected; waiting for HYBRID pullback"
        elif state.pending_cross_timestamp is not None:
            state.bars_waited += 1
            decision_bars_waited = state.bars_waited
            confirmed = confirms_pullback(
                config.pullback,
                low=candle.low,
                close=candle.close,
                fast_ema=fast,
                cross_price=state.pending_cross_price,
            )
            if fast <= slow:
                state.cancelled += 1
                decision = "CANCEL_PULLBACK"
                reason = "bullish EMA structure no longer valid"
                _clear_pending(state)
            elif confirmed:
                state.pullback_confirmations += 1
                state.total_pullback_wait_bars += state.bars_waited
                if adx_value >= config.adx_minimum:
                    decision = "ENTER"
                    reason = "HYBRID pullback confirmed and ADX threshold passed"
                    action = TradeAction.OPEN_LONG
                    allowed = True
                    state.entries += 1
                else:
                    decision = "HOLD"
                    reason = (
                        f"HYBRID pullback confirmed but ADX {adx_value:.2f} "
                        f"is below {config.adx_minimum:.2f}"
                    )
                    blocked = True
                _clear_pending(state)
            elif state.bars_waited >= config.max_wait_bars:
                state.timed_out += 1
                decision = "CANCEL_PULLBACK"
                reason = f"pullback timed out after {state.bars_waited} bars"
                _clear_pending(state)
            else:
                decision = "WAIT_PULLBACK"
                reason = "pending HYBRID pullback has not confirmed"

        controller = TradingController(
            runtime,
            state=state.controller,
            fee_rate=config.fee_rate,
            trade_journal=JsonlTradeJournal(trade_journal_path),
        )
        result = controller.process_signal(
            symbol=config.symbol,
            signal=action,
            entry_quantity=config.entry_quantity,
            price=Decimal(str(candle.close)),
            client_order_id=f"candidate-{candle.timestamp}",
        )
        state.controller = result.state
        state.last_processed_candle = candle.timestamp
        state.active_halt = None
        record = {
            "candle_timestamp": candle.timestamp,
            "close": candle.close,
            "ema20": fast,
            "ema50": slow,
            "adx": adx_value,
            "ema_cross_status": (
                "UP" if cross_up else "DOWN" if cross_down else "NONE"
            ),
            "pullback_pending": state.pending_cross_timestamp is not None,
            "bars_waited": decision_bars_waited,
            "low_touch": low_touch,
            "close_near": close_near,
            "retraced": retraced,
            "entry_allowed": allowed,
            "entry_blocked": blocked,
            "decision": decision,
            "reason": reason,
            "position_after": "LONG" if state.controller.has_open_position else "FLAT",
            "balance_after": str(state.controller.virtual_balance),
        }
        decision_journal.append(record)
        state_store.save(state)
    return state


def _clear_pending(state: CandidateState) -> None:
    state.pending_cross_timestamp = None
    state.pending_cross_price = None
    state.bars_waited = 0
