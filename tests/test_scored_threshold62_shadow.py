import json
from pathlib import Path

from app.candle import Candle
from app.scored_candidate import (
    STRATEGY_NAME as BASELINE_INTERNAL_NAME,
    ScoredCandidateConfig,
    ScoredCandidateStateStore,
    evaluate_shadow_candles,
)
from app.scored_threshold62_diagnostics import summarize_scored_65_62
from app.scored_threshold62_experiment import (
    STRATEGY_NAME,
    configuration_delta,
    experiment_config,
)


def candles(count: int = 90) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            i * 3600,
            100 + i * 0.2,
            101 + i * 0.2,
            99 + i * 0.2,
            100 + i * 0.2,
            10,
        )
        for i in range(count)
    )


def test_threshold62_changes_only_minimum_entry_score() -> None:
    baseline = ScoredCandidateConfig()
    candidate = experiment_config(baseline)
    assert configuration_delta(baseline.allocation, candidate.allocation) == {
        "minimum_entry_score": (65.0, 62.0),
    }
    assert candidate.score == baseline.score
    assert candidate.initial_balance == baseline.initial_balance
    assert candidate.mode == baseline.mode == "shadow"


def test_threshold62_state_journal_and_records_are_fully_isolated(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "scored_candidate_shadow"
    candidate = tmp_path / "scored_candidate_threshold62"
    market = candles()
    evaluate_shadow_candles(
        market,
        state_store=ScoredCandidateStateStore(baseline / "runtime.json"),
        decision_path=baseline / "decisions.jsonl",
    )
    baseline_state = (baseline / "runtime.json").read_bytes()
    baseline_journal = (baseline / "decisions.jsonl").read_bytes()

    evaluate_shadow_candles(
        market,
        state_store=ScoredCandidateStateStore(candidate / "runtime.json"),
        decision_path=candidate / "decisions.jsonl",
        config=experiment_config(),
        strategy_name=STRATEGY_NAME,
    )

    assert (baseline / "runtime.json").read_bytes() == baseline_state
    assert (baseline / "decisions.jsonl").read_bytes() == baseline_journal
    assert (candidate / "runtime.json").exists()
    baseline_row = json.loads(baseline_journal.splitlines()[-1])
    candidate_row = json.loads(
        (candidate / "decisions.jsonl").read_text().splitlines()[-1]
    )
    assert baseline_row["strategy_name"] == BASELINE_INTERNAL_NAME
    assert candidate_row["strategy_name"] == STRATEGY_NAME
    assert candidate_row["mode"] == "shadow"
    assert candidate_row["score"] == baseline_row["score"]
    assert candidate_row["components"] == baseline_row["components"]
    assert set(candidate_row) >= {
        "decision", "risk_fraction", "hard_blocks", "score_breakdown"
    }


def test_pair_report_has_distinct_labels_counters_and_last_observations(
    tmp_path: Path,
) -> None:
    paths = {
        65: tmp_path / "65.jsonl",
        62: tmp_path / "62.jsonl",
    }
    for threshold, path in paths.items():
        path.write_text(
            json.dumps(
                {
                    "candle_timestamp": 0,
                    "candle_close_timestamp": 3600,
                    "strategy_name": f"internal-{threshold}",
                    "decision": "ENTER_LONG" if threshold == 62 else "HOLD",
                    "signal_score": 63,
                    "risk_fraction": 0.1 if threshold == 62 else 0,
                    "components": {},
                    "hard_blocks": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
    report = summarize_scored_65_62(paths[65], paths[62])
    assert set(report) == {"scored_candidate_65", "scored_candidate_62"}
    assert report["scored_candidate_65"]["counters"]["HOLD"] == 1
    assert report["scored_candidate_62"]["counters"]["ENTER_LONG"] == 1
    assert report["scored_candidate_65"]["last"]["candle_timestamp"] == 0
    assert report["scored_candidate_62"]["last"]["candle_timestamp"] == 0


def test_threshold62_systemd_contour_is_optional_and_journal_only() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (
        root / "deploy/systemd/crypto-scored-threshold62-shadow.service"
    ).read_text()
    timer = (
        root / "deploy/systemd/crypto-scored-threshold62-shadow.timer"
    ).read_text()
    assert "scored_candidate_threshold62/runtime.json" in service
    assert "scored_candidate_threshold62/decisions.jsonl" in service
    assert "scored_candidate_threshold62/runtime.lock" in service
    assert "--threshold65-decisions" in service
    assert "After=network-online.target crypto-scored-candidate-shadow.service" in service
    assert "trade" not in service.lower()
    assert "equity" not in service.lower()
    assert "WantedBy=timers.target" in timer

