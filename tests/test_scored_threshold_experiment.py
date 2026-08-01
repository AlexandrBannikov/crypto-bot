import json
from pathlib import Path

from app.candle import Candle
from app.scored_candidate import (
    STRATEGY_NAME as BASELINE_NAME,
    ScoredCandidateConfig,
    ScoredCandidateStateStore,
    evaluate_shadow_candles,
)
from app.scored_threshold_experiment import (
    STRATEGY_NAME,
    configuration_delta,
    experiment_config,
)
from app.scored_threshold60_diagnostics import summarize_threshold60


def candles(count: int = 90) -> tuple[Candle, ...]:
    return tuple(
        Candle(i * 3600, 100 + i * 0.2, 101 + i * 0.2, 99 + i * 0.2, 100 + i * 0.2, 10)
        for i in range(count)
    )


def test_experiment_changes_only_minimum_entry_score() -> None:
    baseline = ScoredCandidateConfig()
    experiment = experiment_config(baseline)
    assert configuration_delta(baseline.allocation, experiment.allocation) == {
        "minimum_entry_score": (65.0, 60.0),
    }
    assert experiment.score == baseline.score
    assert experiment.initial_balance == baseline.initial_balance
    assert experiment.mode == baseline.mode == "shadow"


def test_threshold60_uses_fully_isolated_runtime_files(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "scored_candidate_shadow"
    experiment_dir = tmp_path / "scored_candidate_threshold60"
    market = candles()
    evaluate_shadow_candles(
        market,
        state_store=ScoredCandidateStateStore(baseline_dir / "runtime.json"),
        decision_path=baseline_dir / "decisions.jsonl",
    )
    baseline_before = (baseline_dir / "decisions.jsonl").read_text()
    evaluate_shadow_candles(
        market,
        state_store=ScoredCandidateStateStore(experiment_dir / "runtime.json"),
        decision_path=experiment_dir / "decisions.jsonl",
        config=experiment_config(),
        strategy_name=STRATEGY_NAME,
    )
    experiment_row = json.loads((experiment_dir / "decisions.jsonl").read_text().splitlines()[-1])
    baseline_row = json.loads(baseline_before.splitlines()[-1])
    assert baseline_row["strategy_name"] == BASELINE_NAME
    assert experiment_row["strategy_name"] == STRATEGY_NAME
    assert (baseline_dir / "decisions.jsonl").read_text() == baseline_before
    assert (experiment_dir / "runtime.json").exists()


def test_threshold60_systemd_runtime_is_optional_and_journal_only() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/crypto-scored-threshold60-shadow.service").read_text()
    timer = (root / "deploy/systemd/crypto-scored-threshold60-shadow.timer").read_text()
    assert "scored_candidate_threshold60/runtime.json" in service
    assert "scored_candidate_threshold60/decisions.jsonl" in service
    assert "scored_candidate_threshold60/runtime.lock" in service
    assert "--threshold65-decisions /opt/crypto-bot/state/scored_candidate_shadow/decisions.jsonl" in service
    assert "After=network-online.target crypto-scored-candidate-shadow.service" in service
    assert "trade" not in service.lower()
    assert "equity" not in service.lower()
    assert "WantedBy=timers.target" in timer


def test_threshold60_has_dedicated_diagnostics(tmp_path: Path) -> None:
    decisions = tmp_path / "threshold60.jsonl"
    decisions.write_text(json.dumps({
        "candle_close_timestamp": 3600,
        "decision": "HOLD",
        "signal_score": 61,
        "risk_fraction": 0,
        "components": {},
        "hard_blocks": [],
    }) + "\n")
    report = summarize_threshold60(decisions)
    assert report["strategy_name"] == STRATEGY_NAME
    assert report["minimum_entry_score"] == 60
