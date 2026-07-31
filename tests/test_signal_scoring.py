from dataclasses import replace
from pathlib import Path

import pytest

from app.candle import Candle
from app.risk_allocation import RiskAllocationConfig, risk_fraction, size_for_score
from app.scored_candidate import ScoredCandidateStateStore, evaluate_shadow_candles
from app.signal_scoring import SignalScoreConfig, evaluate_signal
from app.trading_types import PositionSide


def candles(count=90):
    return tuple(
        Candle(i * 3600, 100 + i * .2, 101 + i * .2, 99 + i * .2, 100 + i * .2, 10)
        for i in range(count)
    )


def test_score_is_deterministic_and_bounded():
    config = SignalScoreConfig()
    left = evaluate_signal(candles(), config)
    right = evaluate_signal(candles(), config)
    assert left == right
    assert 0 <= left.total_score <= 100
    assert sum(item.maximum for item in left.contributions) == 100


def test_insufficient_and_nonfinite_data_are_hard_blocks():
    assert "insufficient_data" in evaluate_signal(candles(3)).hard_blocks
    bad = list(candles())
    bad[-1] = replace(bad[-1], close=float("nan"))
    assert "invalid_indicator" in evaluate_signal(bad).hard_blocks


def test_allocation_is_continuous_monotonic_and_bounded():
    config = RiskAllocationConfig(curve="power", curve_exponent=2)
    values = [risk_fraction(score, config) for score in range(65, 94)]
    assert values == sorted(values)
    assert all(0 <= value <= 1 for value in values)
    assert risk_fraction(64.99, config) == 0
    assert risk_fraction(93, config) == 1


def test_position_sizing_respects_stop_and_zero_allocation():
    sized = size_for_score(score=80, balance=1000, entry_price=100, stop_loss=98, side=PositionSide.LONG)
    assert sized.position is not None
    assert sized.position.risk_amount <= 10
    assert size_for_score(score=40, balance=1000, entry_price=100, stop_loss=98, side=PositionSide.LONG).position is None


def test_shadow_runtime_is_idempotent_and_does_not_trade(tmp_path: Path):
    state_path = tmp_path / "state.json"
    journal = tmp_path / "decisions.jsonl"
    evaluate_shadow_candles(candles(), state_store=ScoredCandidateStateStore(state_path), decision_path=journal)
    first = journal.read_text()
    evaluate_shadow_candles(candles(), state_store=ScoredCandidateStateStore(state_path), decision_path=journal)
    assert journal.read_text() == first
    assert all("trade" not in line.lower() for line in journal.read_text().splitlines())
