import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.candle import Candle
from app.scored_candidate import (
    ScoredCandidateLifecycleLedger,
    ScoredCandidateState,
    ScoredCandidateStateStore,
    evaluate_shadow_candles,
)
from app.scored_candidate_diagnostics import summarize


def candles(count=90):
    return tuple(Candle(i * 3600, 100 + i * .2, 101 + i * .2, 99 + i * .2, 100 + i * .2, 10) for i in range(count))


def test_runtime_has_isolated_state_journal_and_complete_record(tmp_path: Path):
    control = tmp_path / "control.json"
    candidate = tmp_path / "candidate.json"
    control.write_text("control")
    candidate.write_text("candidate")
    runtime = tmp_path / "scored_candidate_shadow"
    state = runtime / "runtime.json"
    decisions = runtime / "decisions.jsonl"
    evaluate_shadow_candles(candles(), state_store=ScoredCandidateStateStore(state), decision_path=decisions)
    record = json.loads(decisions.read_text().splitlines()[-1])
    assert state.exists() and decisions.exists()
    assert record["strategy_name"] == "scored_candidate_v1"
    assert record["decision"] in {"ENTER_LONG", "EXIT_LONG", "HOLD"}
    assert set(record["components"]) == {f"{name}_score" for name in ("trend", "ema_alignment", "adx", "pullback", "momentum", "volatility", "cost")}
    assert isinstance(record["hard_blocks"], list)
    assert "risk_fraction" in record and "potential_position_size" in record
    assert control.read_text() == "control" and candidate.read_text() == "candidate"


def test_journal_key_is_idempotent_even_if_state_is_lost(tmp_path: Path):
    state = tmp_path / "runtime.json"
    decisions = tmp_path / "decisions.jsonl"
    evaluate_shadow_candles(candles(), state_store=ScoredCandidateStateStore(state), decision_path=decisions)
    before = decisions.read_text()
    state.unlink()
    evaluate_shadow_candles(candles(), state_store=ScoredCandidateStateStore(state), decision_path=decisions)
    assert decisions.read_text() == before


def test_diagnostics_distribution_buckets_and_limiters(tmp_path: Path):
    path = tmp_path / "decisions.jsonl"
    rows = [
        {"candle_close_timestamp": 100, "decision": "HOLD", "signal_score": 15, "risk_fraction": 0, "components": {"trend_score": 2, "ema_alignment_score": 5, "adx_score": 10, "pullback_score": 10, "momentum_score": 5, "volatility_score": 3, "cost_score": 4}, "hard_blocks": ["score_below_entry_threshold"]},
        {"candle_close_timestamp": 200, "decision": "ENTER_LONG", "signal_score": 75, "risk_fraction": .4, "components": {"trend_score": 20, "ema_alignment_score": 12, "adx_score": 15, "pullback_score": 2, "momentum_score": 8, "volatility_score": 4, "cost_score": 4}, "hard_blocks": []},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    report = summarize(path, now=datetime(1970, 1, 1, tzinfo=timezone.utc))
    assert report["score_distribution"]["10-20"]["hold"] == 1
    assert report["score_distribution"]["70-80"]["enter"] == 1
    assert report["score"]["average"] == 45
    assert report["main_limiters"]["pullback"]["count"] == 1


def test_systemd_runtime_is_journal_only():
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/crypto-scored-candidate-shadow.service").read_text()
    assert "run_scored_candidate_shadow.py" in service
    assert "scored_candidate_shadow/runtime.json" in service
    assert "scored_candidate_shadow/decisions.jsonl" in service
    assert "trade" not in service.lower()
    assert "equity" not in service.lower()


@pytest.mark.parametrize(
    "crash_stage", ["after_prepare", "after_decision", "after_state"],
)
def test_scored_candidate_recovers_every_crash_boundary(tmp_path, crash_stage):
    store = ScoredCandidateStateStore(tmp_path / "runtime.json")
    decisions = tmp_path / "decisions.jsonl"
    target = ScoredCandidateState(last_candle=3600, hypothetical_position=True)
    record = {
        "strategy_name": "scored_candidate_v1",
        "candle_close_timestamp": 7200,
        "candle_timestamp": 3600,
        "decision": "ENTER_LONG",
    }

    def crash(stage):
        if stage == crash_stage:
            raise RuntimeError("injected crash")

    ledger = ScoredCandidateLifecycleLedger(
        store, decisions, crash_hook=crash,
    )
    with pytest.raises(RuntimeError, match="injected"):
        ledger.commit(target, record)

    recovered = ScoredCandidateLifecycleLedger(store, decisions).recover()
    assert recovered == target
    assert store.load() == target
    assert len(decisions.read_text().splitlines()) == 1
