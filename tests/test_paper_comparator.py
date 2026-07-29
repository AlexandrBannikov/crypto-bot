from pathlib import Path

from app.candidate_runtime import CandidateStateStore
from app.paper_comparator import compare_paper_runtimes
from app.trading_controller_store import TradingControllerStateStore


def test_comparator_keeps_runtime_inputs_separate(tmp_path):
    production = tmp_path / "production.json"
    candidate = tmp_path / "candidate.json"
    TradingControllerStateStore(production).save(
        TradingControllerStateStore(production).load()
    )
    CandidateStateStore(candidate).save(CandidateStateStore(candidate).load())
    report = compare_paper_runtimes(
        production_state=production,
        production_trades=tmp_path / "prod-trades",
        production_decisions=tmp_path / "prod-decisions",
        candidate_state=candidate,
        candidate_trades=tmp_path / "cand-trades",
        candidate_decisions=tmp_path / "cand-decisions",
    )
    assert report["balance_difference"] == "0"
    assert report["decision_divergences"] == 0
    assert report["candidate_pullback_confirmations"] == 0
