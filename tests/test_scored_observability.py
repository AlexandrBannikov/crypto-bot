from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from app.candle import Candle
from app.risk_allocation import RiskAllocationConfig, risk_fraction
from app.scored_candidate import ScoredCandidateConfig, ScoredCandidateStateStore, evaluate_shadow_candles
from app.scored_observability import (
    ScoredReportingConfig, aggregate, breakdown_from_record,
    build_score_breakdown, format_breakdown, threshold_distance_text,
)
from app.signal_scoring import ScoreContribution, SignalScore, SignalScoreConfig, evaluate_signal
from scripts.check_runtime import check_scored_observability
from scripts.show_scored_candidate import main as cli_main


NAMES = ("trend", "ema_alignment", "adx", "pullback", "momentum", "volatility", "cost")
MAXIMA = (25, 15, 20, 20, 10, 5, 5)


def signal(values=(10, 8, 12, 9, 6, 3, 4), *, total=None, missing=(), raw=-1.0):
    contributions = tuple(
        ScoreContribution(name, value, maximum, f"reason {name}", raw, value / maximum)
        for name, value, maximum in zip(NAMES, values, MAXIMA) if name not in missing
    )
    scores = dict(zip(NAMES, values))
    return SignalScore(float(sum(values) if total is None else total), *(float(scores[name]) for name in NAMES), (), contributions, "score_v1", {})


def breakdown(score=None, **kwargs):
    item = score or signal()
    defaults = dict(decision="HOLD", entry_threshold=65, strong_entry_threshold=80,
                    risk_fraction=0, risk_allocation_amount=0, baseline_position_amount=500,
                    blocking_factors=["score_below_entry_threshold"], candle_timestamp=100,
                    allocation_rule_id="risk_curve_v1")
    defaults.update(kwargs)
    return build_score_breakdown(item, **defaults)


def record(detail=None):
    value = (detail or breakdown()).to_dict()
    return {"score_breakdown": value, "candle_close_timestamp": 200,
            "candle_timestamp": 100, "decision": value["decision"],
            "score_total": value["total_score"], "entry_threshold": value["entry_threshold"],
            "risk_allocation_pct": value["risk_allocation_pct"],
            "score_components": value["score_components"], "main_limiters": value["main_limiters"]}


@pytest.mark.parametrize("score_value,entry,strong,expected_entry,expected_strong", [
    (0, 65, 80, -65, -80), (34.373621, 65, 80, -30.626379, -45.626379),
    (65, 65, 80, 0, -15), (79.999, 65, 80, 14.999, -.001),
    (80, 65, 80, 15, 0), (100, 65, 80, 35, 20),
])
def test_distances(score_value, entry, strong, expected_entry, expected_strong):
    item = signal((score_value, 0, 0, 0, 0, 0, 0), total=score_value)
    result = breakdown(item, entry_threshold=entry, strong_entry_threshold=strong)
    assert result.distance_to_entry == pytest.approx(expected_entry)
    assert result.distance_to_strong_entry == pytest.approx(expected_strong)


@pytest.mark.parametrize("value,expected", [(-30.626379, "До минимального входа: 30.63 балла"),
                                              (0, "Выше минимального порога на: 0.00 балла"),
                                              (7.25, "Выше минимального порога на: 7.25 балла")])
def test_distance_wording(value, expected):
    assert threshold_distance_text(value) == expected


@pytest.mark.parametrize("completion,status", [(0, "weak"), (39.99, "weak"), (40, "neutral"),
                                                 (69.99, "neutral"), (70, "strong"), (100, "strong")])
def test_component_status(completion, status):
    value = 25 * completion / 100
    result = breakdown(signal((value, 8, 12, 9, 6, 3, 4)))
    assert result.score_components["trend"].status == status


def test_component_sum_consistent():
    assert breakdown().score_consistent is True


def test_component_sum_mismatch_warns_without_decision_change():
    result = breakdown(signal(total=51), decision="HOLD")
    assert result.score_consistent is False and result.decision == "HOLD" and result.reconciliation_warning


def test_missing_component_is_unavailable():
    assert breakdown(signal(missing=("adx",))).score_components["adx"].status == "unavailable"


def test_unavailable_excluded_from_limiters():
    assert all(item["component"] != "adx" for item in breakdown(signal(missing=("adx",))).main_limiters)


def test_negative_raw_value_is_preserved():
    assert breakdown().score_components["trend"].raw_value == -1


def test_normalized_value_is_capped_by_scoring():
    assert evaluate_signal(candles()).contributions[0].normalized_score <= 1


@pytest.mark.parametrize("limit,expected", [(1, 1), (2, 2), (3, 3)])
def test_limiter_top_n(limit, expected):
    reporting = ScoredReportingConfig(max_limiters=limit, limiter_min_deficit_pct=0)
    assert len(breakdown(reporting=reporting).main_limiters) == expected


def test_limiter_deficit_filter_can_remove_all():
    reporting = ScoredReportingConfig(limiter_min_deficit_pct=101)
    assert breakdown(reporting=reporting).main_limiters == ()


def test_limiter_order_by_absolute_deficit():
    result = breakdown(signal((0, 0, 20, 20, 10, 5, 5)), reporting=ScoredReportingConfig(limiter_min_deficit_pct=0))
    assert [x["component"] for x in result.main_limiters[:2]] == ["trend", "ema_alignment"]


def test_limiter_tie_uses_configuration_order():
    result = breakdown(signal((15, 5, 20, 20, 10, 5, 5)), reporting=ScoredReportingConfig(limiter_min_deficit_pct=0))
    assert [x["component"] for x in result.main_limiters[:2]] == ["trend", "ema_alignment"]


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_positive_top_n(limit):
    result = breakdown(reporting=ScoredReportingConfig(max_positive_factors=limit, positive_factor_min_pct=0))
    assert len(result.positive_factors) == limit


def test_positive_strongest_first():
    result = breakdown(signal((25, 0, 10, 0, 0, 0, 0)), reporting=ScoredReportingConfig(positive_factor_min_pct=0))
    assert result.positive_factors[0]["component"] == "trend"


def test_no_positive_factors():
    assert breakdown(signal((0, 0, 0, 0, 0, 0, 0)), reporting=ScoredReportingConfig()).positive_factors == ()


@pytest.mark.parametrize("score_value,band", [(0, "below_entry"), (64.999, "below_entry"),
                                               (65, "reduced"), (79.999, "reduced"),
                                               (80, "strong"), (100, "strong")])
def test_score_bands(score_value, band):
    assert breakdown(signal((score_value, 0, 0, 0, 0, 0, 0), total=score_value)).score_band == band


@pytest.mark.parametrize("score_value", [0, 64.999])
def test_below_entry_allocation_zero(score_value):
    assert risk_fraction(score_value) == 0


@pytest.mark.parametrize("score_value", [65, 72, 79.999])
def test_reduced_allocation_uses_existing_function(score_value):
    fraction = risk_fraction(score_value)
    result = breakdown(signal((score_value, 0, 0, 0, 0, 0, 0), total=score_value), risk_fraction=fraction)
    assert result.risk_allocation_pct == pytest.approx(fraction * 100)


@pytest.mark.parametrize("score_value", [80, 93, 100])
def test_strong_band_does_not_replace_sizing_curve(score_value):
    result = breakdown(signal((score_value, 0, 0, 0, 0, 0, 0), total=score_value), risk_fraction=risk_fraction(score_value))
    assert result.score_band == "strong" and result.risk_allocation_pct == pytest.approx(risk_fraction(score_value) * 100)


def test_baseline_and_amount_round_trip():
    result = breakdown(risk_allocation_amount=12.3456, baseline_position_amount=500.123)
    assert result.risk_allocation_amount == 12.3456 and result.baseline_position_amount == 500.123


def test_allocation_rule_id_and_zero_reason():
    result = breakdown()
    assert result.allocation_rule_id == "risk_curve_v1" and result.allocation_reason == "score below 65"


def test_new_record_is_machine_readable():
    assert breakdown_from_record(record())["calculation_version"] == "score_breakdown_v1"


@pytest.mark.parametrize("bad", [{}, {"score_breakdown": {}}, {"score_breakdown": {"score_components": {}}},
                                  {"score_breakdown": {"score_components": {}, "total_score": "secret"}}])
def test_legacy_or_malformed_record_safe(bad):
    assert breakdown_from_record(bad) is None
    assert "N/A" in format_breakdown(bad)


def test_telegram_compact_top_five_and_remaining():
    text = format_breakdown(record(), component_limit=5)
    assert "Ещё компонентов: 2" in text and len(text) < 4096


def test_telegram_thresholds_distance_allocation_reason():
    text = format_breakdown(record())
    assert "Entry threshold: 65" in text and "Strong threshold: 80" in text
    assert "До минимального входа" in text and "score below 65" in text


def test_aggregate_metrics(tmp_path):
    path = tmp_path / "decisions.jsonl"
    details = [breakdown(signal((s, 0, 0, 0, 0, 0, 0), total=s), risk_fraction=risk_fraction(s)) for s in (30, 65, 80)]
    path.write_text("\n".join(json.dumps(record(item)) for item in details) + "\n")
    result = aggregate(path)
    assert result["decisions_total"] == 3 and result["score"]["median"] == 65
    assert result["score_bands"]["below_65_pct"] == pytest.approx(100 / 3)


def test_cli_latest_json_and_read_only(tmp_path, capsys):
    path = tmp_path / "decisions.jsonl"
    path.write_text(json.dumps(record()) + "\n")
    before = path.read_bytes()
    assert cli_main(["--decisions", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["total_score"] == breakdown().total_score
    assert path.read_bytes() == before


@pytest.mark.parametrize("period", ["24h", "7d", "all"])
def test_cli_aggregates(period, tmp_path, capsys):
    path = tmp_path / "decisions.jsonl"
    row = record(); row["candle_close_timestamp"] = int(datetime.now(timezone.utc).timestamp())
    path.write_text(json.dumps(row) + "\n")
    assert cli_main(["--decisions", str(path), "--aggregate", period, "--json"]) == 0
    assert "decisions_total" in json.loads(capsys.readouterr().out)


def test_runtime_checks_pass(tmp_path):
    journal, state = tmp_path / "decisions.jsonl", tmp_path / "runtime.json"
    row = record(); row["candle_close_timestamp"] = int(datetime.now(timezone.utc).timestamp())
    journal.write_text(json.dumps(row) + "\n"); state.write_text(json.dumps({"last_candle": 100}))
    checks = check_scored_observability(state, journal)
    assert [name for status, name, _ in checks] == ["scored_breakdown", "scored_reconciliation", "scored_thresholds", "scored_allocation", "scored_journal_freshness"]
    assert all(status == "PASS" for status, _, _ in checks)


def test_runtime_legacy_is_warn_not_fail(tmp_path):
    path = tmp_path / "decisions.jsonl"; path.write_text(json.dumps({"signal_score": 34}) + "\n")
    assert all(status == "WARN" for status, _, _ in check_scored_observability(tmp_path / "missing", path))


def candles(count=90):
    return tuple(Candle(i * 3600, 100 + i * .2, 101 + i * .2, 99 + i * .2, 100 + i * .2, 10) for i in range(count))


def test_runtime_journal_extended_without_score_or_sizing_change(tmp_path):
    data = candles(); expected_score = evaluate_signal(data).total_score
    path, state = tmp_path / "decisions.jsonl", tmp_path / "runtime.json"
    evaluate_shadow_candles(data, state_store=ScoredCandidateStateStore(state), decision_path=path)
    row = json.loads(path.read_text().splitlines()[-1])
    assert row["score_total"] == expected_score
    assert row["risk_fraction"] == pytest.approx(risk_fraction(expected_score)) if row["decision"] == "ENTER_LONG" else row["risk_fraction"] == 0
    before = path.read_bytes(); evaluate_shadow_candles(data, state_store=ScoredCandidateStateStore(state), decision_path=path)
    assert path.read_bytes() == before


def test_reporting_config_does_not_change_action(tmp_path):
    data = candles(); actions = []
    for index, reporting in enumerate((ScoredReportingConfig(max_limiters=1), ScoredReportingConfig(max_limiters=3))):
        path, state = tmp_path / f"d{index}.jsonl", tmp_path / f"s{index}.json"
        evaluate_shadow_candles(data, state_store=ScoredCandidateStateStore(state), decision_path=path,
                                config=ScoredCandidateConfig(reporting=reporting))
        actions.append([json.loads(line)["decision"] for line in path.read_text().splitlines()])
    assert actions[0] == actions[1]
