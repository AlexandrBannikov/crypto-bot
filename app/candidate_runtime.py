from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Callable, Sequence

import pandas as pd

from app.candle import Candle
from app.causal_execution import process_candle_execution, queue_pending_action
from app.execution_runner import ExecutionRunner
from app.indicators import adx, ema
from app.paper_executor import PaperExecutor
from app.market_continuity import validate_candle_continuity
from app.runtime_versions import version_fields
from app.strategy_v2_relaxed import (
    RelaxedPullbackConfig,
    RelaxedPullbackMode,
    confirms_pullback,
)
from app.trade_journal import JsonlTradeJournal, TradeJournalEntry
from app.trading_controller import TradingController, TradingControllerState
from app.trading_controller_store import (
    controller_state_from_dict,
    controller_state_to_dict,
)
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
    strategy_logic_version: str = field(
        default_factory=lambda: version_fields()["strategy_logic_version"]
    )
    feature_version: str = field(
        default_factory=lambda: version_fields()["feature_version"]
    )
    execution_policy_version: str = field(
        default_factory=lambda: version_fields()["execution_policy_version"]
    )
    ledger_schema_version: str = field(
        default_factory=lambda: version_fields()["ledger_schema_version"]
    )


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
            return self.from_dict(payload)
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid candidate state: {exc}") from exc

    def save(self, state: CandidateState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict(state)
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

    @staticmethod
    def to_dict(state: CandidateState) -> dict:
        payload = asdict(state)
        payload["controller"] = controller_state_to_dict(state.controller)
        return payload

    @staticmethod
    def from_dict(payload: dict) -> CandidateState:
        values = dict(payload)
        raw_controller = values.pop("controller")
        return CandidateState(
            controller=controller_state_from_dict(raw_controller), **values,
        )


class CandidateDecisionJournal:
    def __init__(self, path: Path):
        self.path = path

    def append(self, record: dict) -> bool:
        key = (record["strategy_id"], int(record["candle_timestamp"]))
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                existing = json.loads(line)
                if (existing.get("strategy_id"), existing.get("candle_timestamp")) == key:
                    return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True


class _BufferedTradeJournal:
    def __init__(self) -> None:
        self.entries: list[TradeJournalEntry] = []

    def append(self, entry: TradeJournalEntry) -> None:
        self.entries.append(entry)


class CandidateLifecycleLedger:
    """WAL for candidate strategy state plus both lifecycle journals."""

    def __init__(
        self,
        state_store: CandidateStateStore,
        trade_journal_path: Path,
        decision_journal_path: Path,
        *,
        wal_path: Path | None = None,
        crash_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.state_store = state_store
        self.trade_journal = JsonlTradeJournal(trade_journal_path)
        self.decision_journal = CandidateDecisionJournal(decision_journal_path)
        self.wal_path = wal_path or state_store.path.with_suffix(
            state_store.path.suffix + ".wal"
        )
        self.crash_hook = crash_hook

    def _hook(self, stage: str) -> None:
        if self.crash_hook is not None:
            self.crash_hook(stage)

    def commit(
        self, state: CandidateState, decision: dict,
        trades: Sequence[TradeJournalEntry],
    ) -> None:
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.wal_path.with_suffix(self.wal_path.suffix + ".tmp")
        temporary.write_text(json.dumps({
            "state": self.state_store.to_dict(state),
            "decision": decision,
            "trades": [entry.to_dict() for entry in trades],
        }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(self.wal_path)
        self._hook("after_prepare")
        for entry in trades:
            self.trade_journal.append(entry)
        self._hook("after_trades")
        self.decision_journal.append(decision)
        self._hook("after_decision")
        self.state_store.save(state)
        self._hook("after_state")
        self.wal_path.unlink(missing_ok=True)

    def recover(self) -> CandidateState | None:
        if not self.wal_path.exists():
            return None
        payload = json.loads(self.wal_path.read_text(encoding="utf-8"))
        state = self.state_store.from_dict(payload["state"])
        for raw in payload["trades"]:
            self.trade_journal.append(TradeJournalEntry.from_dict(raw))
        self.decision_journal.append(payload["decision"])
        self.state_store.save(state)
        self.wal_path.unlink(missing_ok=True)
        return state


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
    ledger = CandidateLifecycleLedger(
        state_store, trade_journal_path, decision_journal_path,
    )
    ledger.recover()
    state = state_store.load()
    continuity = validate_candle_continuity(
        candles,
        timeframe_seconds=int(config.timeframe) * 60,
        last_processed_timestamp=state.last_processed_candle,
    )
    ordered = continuity.candles
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
    for candle in new_candles:
        position_before = (
            "LONG" if state.controller.has_open_position else "FLAT"
        )
        buffered_trades = _BufferedTradeJournal()
        controller = TradingController(
            runtime,
            state=state.controller,
            fee_rate=config.fee_rate,
            trade_journal=buffered_trades,
        )
        open_step = process_candle_execution(
            controller,
            symbol=config.symbol,
            candle=candle,
            entry_quantity=config.entry_quantity,
        )
        state.controller = controller.state
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
        reason_code = "no_signal"
        action = TradeAction.HOLD
        allowed = False
        blocked = False
        decision_bars_waited = state.bars_waited

        if cross_down:
            if state.pending_cross_timestamp is not None:
                state.cancelled += 1
                decision = "CANCEL_PULLBACK"
                reason = "EMA20 crossed below EMA50; pending pullback cancelled"
                reason_code = "trend_not_confirmed"
                _clear_pending(state)
            if state.controller.has_open_position:
                decision = "EXIT"
                reason = "EMA cross down; exits are not filtered"
                reason_code = "exit_signal"
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
            reason_code = "pullback_not_detected"
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
                reason_code = "trend_not_confirmed"
                _clear_pending(state)
            elif confirmed:
                state.pullback_confirmations += 1
                state.total_pullback_wait_bars += state.bars_waited
                if adx_value >= config.adx_minimum:
                    if continuity.unresolved_gap:
                        decision = "HOLD"
                        reason = "unresolved market-data gap blocks new entries"
                        reason_code = "market_gap"
                        blocked = True
                    else:
                        decision = "ENTER"
                        reason = "HYBRID pullback confirmed; entry queued for next open"
                        reason_code = "entry_allowed"
                        action = TradeAction.OPEN_LONG
                        allowed = True
                        state.entries += 1
                else:
                    decision = "HOLD"
                    reason = (
                        f"HYBRID pullback confirmed but ADX {adx_value:.2f} "
                        f"is below {config.adx_minimum:.2f}"
                    )
                    reason_code = "adx_below_threshold"
                    blocked = True
                _clear_pending(state)
            elif state.bars_waited >= config.max_wait_bars:
                state.timed_out += 1
                decision = "CANCEL_PULLBACK"
                reason = f"pullback timed out after {state.bars_waited} bars"
                reason_code = "pullback_not_detected"
                _clear_pending(state)
            else:
                decision = "WAIT_PULLBACK"
                reason = "pending HYBRID pullback has not confirmed"
                reason_code = "pullback_not_detected"

        queue_pending_action(
            controller,
            action=action,
            signal_timestamp=candle.timestamp,
            signal_price=Decimal(str(candle.close)),
        )
        state.controller = controller.state
        state.last_processed_candle = candle.timestamp
        state.active_halt = None
        record = {
            "candle_timestamp": candle.timestamp,
            "strategy_id": "candidate_adx_hybrid",
            "signal": decision,
            "action": action.value,
            "position_before": position_before,
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
            "reason_code": reason_code,
            "position_after": "LONG" if state.controller.has_open_position else "FLAT",
            "price": candle.close,
            "signal_timestamp": candle.timestamp if action != TradeAction.HOLD else None,
            "signal_price": candle.close if action != TradeAction.HOLD else None,
            "fill_timestamps": [
                candle.timestamp
                for item in open_step.executions
                if item.execution is not None
                and item.execution.executed_quantity > 0
            ],
            "fill_prices": [
                str(item.execution.average_price)
                for item in open_step.executions
                if item.execution is not None and item.execution.average_price is not None
            ],
            "unresolved_gap": continuity.unresolved_gap,
            "decision_status": "produced",
            "status_reason": None,
            "balance_after": str(state.controller.virtual_balance),
            **version_fields(),
        }
        ledger.commit(state, record, buffered_trades.entries)
    return state


def _clear_pending(state: CandidateState) -> None:
    state.pending_cross_timestamp = None
    state.pending_cross_price = None
    state.bars_waited = 0
