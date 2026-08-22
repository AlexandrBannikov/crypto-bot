from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from app.candle import Candle
from app.candidate_runtime import (
    CandidateConfig,
    CandidateLifecycleLedger,
    CandidateState,
    CandidateStateStore,
    ensure_paper_only,
    process_candidate_candles,
)
from app.trade_journal import JsonlTradeJournal
from tests.test_trade_journal import make_entry
from app.strategy_v2_relaxed import RelaxedPullbackMode
from app.trading_controller import TradingControllerState


def candles(count=60):
    return tuple(
        Candle(i * 3600, 100 + i / 10, 102 + i / 10, 98 + i / 10, 100 + i / 10)
        for i in range(count)
    )


def test_candidate_parameters_and_paths_are_isolated(tmp_path):
    config = CandidateConfig()
    assert config.max_wait_bars == 8
    assert config.tolerance == 0.005
    assert config.retrace_pct == 0.0075
    assert config.pullback.mode is RelaxedPullbackMode.HYBRID
    production = tmp_path / "production.json"
    production.write_text("untouched")
    store = CandidateStateStore(tmp_path / "candidate.json")
    store.save(store.load())
    assert production.read_text() == "untouched"
    assert store.path != production


def test_live_trading_guard(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    with pytest.raises(RuntimeError, match="must be false"):
        ensure_paper_only()


def test_first_run_is_baseline_and_repeated_run_is_deterministic(tmp_path):
    market = candles()
    state_path = tmp_path / "candidate.json"
    trades = tmp_path / "candidate-trades.jsonl"
    decisions = tmp_path / "candidate-decisions.jsonl"
    store = CandidateStateStore(state_path)
    first = process_candidate_candles(
        market, state_store=store, trade_journal_path=trades,
        decision_journal_path=decisions,
    )
    before = state_path.read_bytes()
    second = process_candidate_candles(
        market, state_store=store, trade_journal_path=trades,
        decision_journal_path=decisions,
    )
    assert first.baseline_candle == market[-1].timestamp
    assert first.controller.virtual_balance == Decimal("1000")
    assert not trades.exists()
    assert not decisions.exists()
    assert second.last_processed_candle == first.last_processed_candle
    assert state_path.read_bytes() == before


def test_pending_persists_then_times_out(monkeypatch, tmp_path):
    market = candles(61)
    store = CandidateStateStore(tmp_path / "candidate.json")
    store.save(
        CandidateState(
            controller=TradingControllerState(),
            last_processed_candle=market[-2].timestamp,
            baseline_candle=market[-2].timestamp,
            pending_cross_timestamp=market[-2].timestamp - 7 * 3600,
            pending_cross_price=90.0,
            bars_waited=7,
        )
    )
    frame = pd.DataFrame(
        {
            "ema20": [101.0] * 60 + [101.0],
            "ema50": [100.0] * 61,
            "adx": [25.0] * 61,
        }
    )
    monkeypatch.setattr("app.candidate_runtime._features", lambda *args: frame)
    result = process_candidate_candles(
        market, state_store=store,
        trade_journal_path=tmp_path / "trades.jsonl",
        decision_journal_path=tmp_path / "decisions.jsonl",
    )
    assert result.pending_cross_timestamp is None
    assert result.timed_out == 1
    assert result.controller.virtual_balance == Decimal("1000")


def test_pending_pullback_enters_once_when_hybrid_and_adx_confirm(monkeypatch, tmp_path):
    market = candles(61)
    store = CandidateStateStore(tmp_path / "candidate.json")
    store.save(
        CandidateState(
            last_processed_candle=market[-2].timestamp,
            baseline_candle=market[-2].timestamp,
            pending_cross_timestamp=market[-2].timestamp,
            pending_cross_price=market[-2].close,
        )
    )
    frame = pd.DataFrame(
        {
            "ema20": [106.0] * 61,
            "ema50": [100.0] * 61,
            "adx": [25.0] * 61,
        }
    )
    monkeypatch.setattr("app.candidate_runtime._features", lambda *args: frame)
    decisions = tmp_path / "candidate-decisions.jsonl"
    result = process_candidate_candles(
        market, state_store=store,
        trade_journal_path=tmp_path / "candidate-trades.jsonl",
        decision_journal_path=decisions,
    )
    assert not result.controller.has_open_position
    assert result.controller.pending_action.value == "open_long"
    assert result.entries == 1
    assert result.pullback_confirmations == 1
    assert '"decision":"ENTER"' in decisions.read_text()
    next_market = candles(62)
    filled = process_candidate_candles(
        next_market, state_store=store,
        trade_journal_path=tmp_path / "candidate-trades.jsonl",
        decision_journal_path=decisions,
    )
    assert filled.controller.has_open_position
    assert filled.controller.entry_price == Decimal(str(next_market[-1].open))
    before = decisions.read_bytes()
    process_candidate_candles(
        next_market, state_store=store,
        trade_journal_path=tmp_path / "candidate-trades.jsonl",
        decision_journal_path=decisions,
    )
    assert decisions.read_bytes() == before


def test_cross_down_cancels_pending(monkeypatch, tmp_path):
    market = candles(61)
    store = CandidateStateStore(tmp_path / "candidate.json")
    store.save(
        CandidateState(
            last_processed_candle=market[-2].timestamp,
            baseline_candle=market[-2].timestamp,
            pending_cross_timestamp=market[-2].timestamp,
            pending_cross_price=market[-2].close,
        )
    )
    frame = pd.DataFrame(
        {
            "ema20": [101.0] * 60 + [99.0],
            "ema50": [100.0] * 61,
            "adx": [25.0] * 61,
        }
    )
    monkeypatch.setattr("app.candidate_runtime._features", lambda *args: frame)
    result = process_candidate_candles(
        market, state_store=store,
        trade_journal_path=tmp_path / "candidate-trades.jsonl",
        decision_journal_path=tmp_path / "candidate-decisions.jsonl",
    )
    assert result.pending_cross_timestamp is None
    assert result.cancelled == 1


def test_exit_is_not_filtered(monkeypatch, tmp_path):
    market = candles(61)
    store = CandidateStateStore(tmp_path / "candidate.json")
    store.save(
        CandidateState(
            controller=TradingControllerState(
                position_quantity=Decimal("0.01"),
                entry_price=Decimal("100"),
                virtual_balance=Decimal("998.999"),
                entry_fee=Decimal("0.001"),
                opened_at="2026-01-01T00:00:00+00:00",
            ),
            last_processed_candle=market[-2].timestamp,
            baseline_candle=market[-2].timestamp,
        )
    )
    frame = pd.DataFrame(
        {
            "ema20": [101.0] * 60 + [99.0],
            "ema50": [100.0] * 61,
            "adx": [0.0] * 61,
        }
    )
    monkeypatch.setattr("app.candidate_runtime._features", lambda *args: frame)
    result = process_candidate_candles(
        market, state_store=store,
        trade_journal_path=tmp_path / "candidate-trades.jsonl",
        decision_journal_path=tmp_path / "candidate-decisions.jsonl",
    )
    assert result.controller.has_open_position
    assert result.controller.pending_action.value == "close_long"
    assert result.exits == 1
    result = process_candidate_candles(
        candles(62), state_store=store,
        trade_journal_path=tmp_path / "candidate-trades.jsonl",
        decision_journal_path=tmp_path / "candidate-decisions.jsonl",
    )
    assert not result.controller.has_open_position
    assert (tmp_path / "candidate-trades.jsonl").exists()


def test_trade_and_decision_journals_are_different_paths(tmp_path):
    assert tmp_path / "candidate-trades.jsonl" != tmp_path / "candidate-decisions.jsonl"


@pytest.mark.parametrize(
    "crash_stage", ["after_prepare", "after_trades", "after_decision", "after_state"],
)
def test_candidate_lifecycle_recovers_every_crash_boundary(tmp_path, crash_stage):
    store = CandidateStateStore(tmp_path / "candidate.json")
    trades = tmp_path / "trades.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    target = CandidateState(last_processed_candle=3600, entries=1)
    decision = {
        "strategy_id": "candidate_adx_hybrid",
        "candle_timestamp": 3600,
        "decision": "ENTER",
    }

    def crash(stage):
        if stage == crash_stage:
            raise RuntimeError("injected crash")

    ledger = CandidateLifecycleLedger(
        store, trades, decisions, crash_hook=crash,
    )
    with pytest.raises(RuntimeError, match="injected"):
        ledger.commit(target, decision, [make_entry()])

    recovered = CandidateLifecycleLedger(store, trades, decisions).recover()
    assert recovered == target
    assert store.load() == target
    assert [item.record_id for item in JsonlTradeJournal(trades).read_all()] == ["record-1"]
    assert len(decisions.read_text().splitlines()) == 1
