import json
from pathlib import Path

import pytest

from app.candle import Candle
from app.scored_threshold_comparison import compare, render_text


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _row(timestamp: int, score: float, decision: str, allocation: float = 0, position: float | None = None) -> dict:
    return {
        "candle_timestamp": timestamp,
        "candle_close_timestamp": timestamp + 3600,
        "signal_score": score,
        "decision": decision,
        "risk_fraction": allocation,
        "potential_position_size": position,
        "components": {"trend_score": score},
        "hard_blocks": ["score_below_entry_threshold"] if decision == "HOLD" else [],
    }


def test_compare_finds_only_threshold60_entries_and_future_outcomes(tmp_path: Path) -> None:
    baseline = tmp_path / "65.jsonl"
    experiment = tmp_path / "60.jsonl"
    _write(baseline, [_row(0, 62, "HOLD"), _row(3600, 70, "ENTER_LONG", .2, 100)])
    _write(experiment, [_row(0, 62, "ENTER_LONG", .1, 50), _row(3600, 70, "HOLD")])
    candles = tuple(Candle(i * 3600, 100, 101 + i, 99 - i / 10, 100 + i, 10) for i in range(26))
    report = compare(baseline, experiment, candles=candles)
    near = report["near_threshold"]
    assert near["additional_entries"] == 1
    assert near["average_score"] == 62
    assert near["future_outcomes_percent"]["return_3h"] == pytest.approx(3)
    assert near["future_outcomes_percent"]["return_24h"] == pytest.approx(24)
    assert near["future_outcomes_percent"]["mfe_24h"] == pytest.approx(25)
    assert near["future_outcomes_percent"]["mae_24h"] == pytest.approx(-3.4)
    assert report["alignment"]["score_or_component_mismatches"] == 0


def test_comparison_reports_allocation_and_economic_risks(tmp_path: Path) -> None:
    baseline = tmp_path / "65.jsonl"
    experiment = tmp_path / "60.jsonl"
    rows = [_row(0, 62, "ENTER_LONG", .1, 4), _row(3600, 40, "HOLD")]
    _write(baseline, rows)
    _write(experiment, rows)
    report = compare(baseline, experiment)
    item = report["threshold_60"]
    assert item["allocation_distribution"] == {"0.00%": 1, "10.00%": 1}
    assert item["economic"]["minimum_allocation_entries"] == 1
    assert item["economic"]["positions_below_minimum_order"] == 1
    assert item["economic"]["average_round_trip_commission"] == pytest.approx(.008)
    assert "Threshold 60" in render_text(report)


def test_comparison_requires_identical_scores_to_claim_fair_alignment(tmp_path: Path) -> None:
    baseline = tmp_path / "65.jsonl"
    experiment = tmp_path / "60.jsonl"
    _write(baseline, [_row(0, 62, "HOLD")])
    _write(experiment, [_row(0, 63, "ENTER_LONG", .1, 50)])
    report = compare(baseline, experiment)
    assert report["alignment"]["score_or_component_mismatches"] == 1
