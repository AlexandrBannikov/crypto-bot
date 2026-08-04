from __future__ import annotations

from dataclasses import asdict
import json
import math

import pytest

from app.candle import Candle
from app.entry_blocker_analysis import (
    DECISION_CATEGORIES, DISTANCE_65, DISTANCE_80, BlockerClassification, EntryObservation,
    FilterState, analyze_entry_blockers, classify_observation, replay_entry_observations, technical_record_findings,
    score_distance_distribution,
)
from app.scored_component_analysis import COMPONENTS
from app.signal_scoring import SignalScoreConfig

MAX = SignalScoreConfig().maxima


def row(score=50, *, base=True, filters=(), position=False, cooldown=False, ts=0, regime="RANGE_NORMAL"):
    return EntryObservation(ts, ts + 3600, 100 + ts / 3600, score, 65, {c: MAX[c] / 2 for c in COMPONENTS}, regime, base, tuple(filters), position, cooldown)


def market(n=100):
    return tuple(Candle(i * 3600, 100 + i*.1, 101 + i*.1, 99 + i*.1, 100 + i*.1, 10) for i in range(n))


@pytest.mark.parametrize("score,expected", [(0, "SCORE_BELOW_THRESHOLD"), (64.99, "SCORE_BELOW_THRESHOLD"), (65, "ENTRY_ALLOWED"), (100, "ENTRY_ALLOWED")])
def test_score_classification(score, expected):
    assert classify_observation(row(score)).category == expected


@pytest.mark.parametrize("filter_state,expected", [
    (FilterState("ema_cross", False, True, "hard", "cross absent"), "HARD_FILTER_BLOCK"),
    (FilterState("risk_halt", False, True, "risk", "halt"), "RISK_BLOCK"),
    (FilterState("stale_market", False, True, "data_quality", "stale"), "DATA_QUALITY_BLOCK"),
])
def test_hard_risk_data_classification(filter_state, expected):
    assert classify_observation(row(90, filters=(filter_state,))).category == expected


@pytest.mark.parametrize("kwargs,expected", [
    ({"base": False}, "NO_BASE_SIGNAL"), ({"position": True}, "POSITION_ALREADY_OPEN"),
    ({"cooldown": True}, "COOLDOWN_BLOCK"),
])
def test_non_score_categories(kwargs, expected):
    assert classify_observation(row(90, **kwargs)).category == expected


def test_data_quality_precedes_position_and_score():
    state = FilterState("warmup", False, True, "data_quality", "warmup")
    assert classify_observation(row(90, filters=(state,), position=True)).category == "DATA_QUALITY_BLOCK"


def test_additional_reasons_and_blockers_are_preserved():
    states = (FilterState("a", False, True, "hard", "a"), FilterState("b", False, True, "hard", "b"))
    result = classify_observation(row(90, filters=states))
    assert result.primary_reason == "a"
    assert result.additional_reasons == ("b",)
    assert result.blockers == ("a", "b")


@pytest.mark.parametrize("score", (34.9, 35, 44.9, 45, 54.9, 55, 59.9, 60, 61.9, 62, 63.9, 64, 64.99, 65, 79.99, 80))
def test_score_distance_bands_cover_boundaries(score):
    result = asdict(score_distance_distribution([row(score)], threshold=65))
    assert sum(x["count"] for x in result["bands"].values()) == 1


@pytest.mark.parametrize("threshold,bands", [(65, DISTANCE_65), (80, DISTANCE_80)])
def test_score_distance_denominator(threshold, bands):
    result = score_distance_distribution([row(10), row(threshold), row(100)], threshold=threshold)
    assert result.denominator == 3
    assert sum(x["count"] for x in result.bands.values()) == 3


def test_empty_score_distance_is_json_safe():
    assert "NaN" not in json.dumps(asdict(score_distance_distribution([])), allow_nan=False)


def test_replay_retains_warmup_as_data_quality():
    rows, quality = replay_entry_observations(market(70))
    assert len(rows) == 70
    assert rows[0].base_signal is False
    assert classify_observation(rows[0]).category == "DATA_QUALITY_BLOCK"
    assert quality["warmup_rows_retained"] == 65


def test_replay_is_causal():
    before, _ = replay_entry_observations(market(80))
    after, _ = replay_entry_observations(market(81))
    assert before == after[:-1]


def test_replay_duplicate_is_reported():
    m = market(70)
    rows, quality = replay_entry_observations(m + (m[-1],))
    assert len(rows) == 70
    assert quality["duplicate_candles"] == 1


def test_funnel_counts_are_consistent():
    rows, quality = replay_entry_observations(market(100))
    report = asdict(analyze_entry_blockers(rows, market(100), period="all", quality=quality))
    funnel = report["base_signal_funnel"]
    assert funnel["all_closed_candles"] == 100
    assert funnel["base_signal"] == 35
    assert funnel["score_gte_65"] <= funnel["base_signal"]
    assert sum(report["decision_categories"].values()) == 100


@pytest.mark.parametrize("count", (0, 1, 2, 3, 5, 10, 20, 50))
def test_blocker_frequency_denominators(count):
    rows = [row(50, ts=i*3600) for i in range(count)]
    report = asdict(analyze_entry_blockers(rows, market(max(count, 1)), period="all"))
    for value in report["blocker_frequency"].values():
        assert value["count"] >= 0
        assert 0 <= value["percent_all"] <= 100 if count else value["percent_all"] == 0


def test_component_blockers_have_top2_and_top3():
    rows = [row(50, ts=i*3600) for i in range(10)]
    report = asdict(analyze_entry_blockers(rows, market(10), period="all"))
    component = report["blocker_frequency"]["trend"]
    assert component["top_2_count"] >= component["primary_count"]
    assert component["top_3_count"] >= component["top_2_count"]


def test_combinations_are_reported():
    rows = [row(50, ts=i*3600) for i in range(20)]
    report = asdict(analyze_entry_blockers(rows, market(20), period="all"))
    assert report["blocker_combinations"]
    assert "+" in report["blocker_combinations"][0]["combination"]


@pytest.mark.parametrize("horizon", (1, 3, 6, 12, 24))
def test_near_miss_outcome_horizons(horizon):
    rows = [row(62, ts=i*3600) for i in range(40)]
    report = asdict(analyze_entry_blockers(rows, market(40), period="all", horizons=(horizon,)))
    assert report["near_misses"]["count"] == 40
    assert report["near_misses"]["outcomes"][str(horizon)]["gross_return_pct"]["count"] == 40 - horizon


def test_near_miss_excludes_hard_filtered_score():
    state = FilterState("stale", False, True, "data_quality", "stale")
    rows = [row(62, filters=(state,), ts=i*3600) for i in range(20)]
    report = asdict(analyze_entry_blockers(rows, market(20), period="all"))
    assert report["near_misses"]["count"] == 0


def test_near_miss_components_and_regime():
    rows = [row(62, ts=i*3600, regime="TREND_UP_NORMAL") for i in range(10)]
    report = asdict(analyze_entry_blockers(rows, market(10), period="all"))
    assert report["near_misses"]["by_regime"] == {"TREND_UP_NORMAL": 10}
    assert sum(report["near_misses"]["component_last_points"].values()) == 30


def test_commission_adjustment_is_explicit():
    report = asdict(analyze_entry_blockers([row(62, ts=i*3600) for i in range(30)], market(30), period="all"))
    assert report["cost_analysis"]["round_trip_friction_pct"] == pytest.approx(.3)
    assert report["cost_analysis"]["minimum_required_move_pct"] == pytest.approx(.3)


def test_forward_outcome_no_future_data_is_censored():
    report = asdict(analyze_entry_blockers([row(62, ts=i*3600) for i in range(3)], market(3), period="all", horizons=(24,)))
    assert report["near_misses"]["outcomes"]["24"]["gross_return_pct"]["count"] == 0


def test_comparison_groups_exist():
    report = asdict(analyze_entry_blockers([row(x, ts=i*3600) for i, x in enumerate((20, 45, 62, 65, 80))], market(5), period="all"))
    assert set(report["real_entry_comparison"]) == {"real_entries_score_65_plus", "near_miss_60_65", "hold_40_60", "hold_below_40"}


def test_regime_breakdown_has_coverage():
    rows = [row(50, regime="RANGE_NORMAL", ts=0), row(70, regime="TREND_UP_NORMAL", ts=3600)]
    report = asdict(analyze_entry_blockers(rows, market(2), period="all"))
    assert report["regime_breakdown"]["RANGE_NORMAL"]["coverage_pct"] == 50


@pytest.mark.parametrize("resolution", ("weeks", "months", "rolling_7d", "rolling_30d"))
def test_time_breakdown_resolutions(resolution):
    report = asdict(analyze_entry_blockers([row(50, ts=i*3600) for i in range(50)], market(50), period="all"))
    assert resolution in report["time_breakdown"]


def test_counterfactuals_are_marked_diagnostic():
    report = asdict(analyze_entry_blockers([row(50, ts=i*3600) for i in range(20)], market(20), period="all", include_counterfactuals=True))
    assert report["counterfactuals"]["labels"] == ["DIAGNOSTIC_ONLY", "NO_PRODUCTION_CHANGE", "NOT_A_TRADING_RECOMMENDATION"]
    assert report["counterfactuals"]["thresholds"]["60"] == 0


def test_default_counterfactuals_not_requested():
    report = asdict(analyze_entry_blockers([row(50)], market(1), period="all"))
    assert report["counterfactuals"] == {"status": "NOT_REQUESTED"}


def test_decision_categories_are_complete():
    report = asdict(analyze_entry_blockers([row(50)], market(1), period="all"))
    assert set(DECISION_CATEGORIES) == set(report["decision_categories"])


def test_no_lookahead_price_change_affects_only_future():
    first = market(40)
    changed = list(first); changed[-1] = Candle(changed[-1].timestamp, 100, 101, 99, 500, 10)
    before, _ = replay_entry_observations(first)
    after, _ = replay_entry_observations(tuple(changed))
    assert before[:-1] == after[:-1]


def test_missing_data_has_no_nan_output():
    rows = [row(50, ts=i*3600) for i in range(5)]
    report = asdict(analyze_entry_blockers(rows, market(5), period="all"))
    assert "NaN" not in json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("name", COMPONENTS)
def test_all_real_components_are_in_blocker_report(name):
    report = asdict(analyze_entry_blockers([row(50, ts=i*3600) for i in range(5)], market(5), period="all"))
    assert name in report["blocker_frequency"]


@pytest.mark.parametrize("category", DECISION_CATEGORIES)
def test_category_names_are_stable(category):
    assert isinstance(category, str) and category


def test_report_is_read_only_for_input_rows():
    rows = [row(62, ts=i*3600) for i in range(20)]
    before = repr(rows)
    analyze_entry_blockers(rows, market(20), period="all", include_counterfactuals=True)
    assert repr(rows) == before


def test_production_changes_false():
    report = asdict(analyze_entry_blockers([row(50)], market(1), period="all"))
    assert report["production_changes"] is False
    assert report["verdict"]["production_changes"] is False


def test_confidence_depends_on_observation_count():
    report = asdict(analyze_entry_blockers([row(50, ts=i*3600) for i in range(1000)], market(1000), period="all"))
    assert report["confidence"]["level"] == "medium"


def test_technical_missing_component():
    assert technical_record_findings({"components": {}})[0]["code"] == "MISSING_COMPONENT_FIELD"


def test_technical_nan_component():
    record = {"components": {f"{c}_score": 1.0 for c in COMPONENTS}}
    record["components"]["trend_score"] = math.nan
    assert technical_record_findings(record)[0]["code"] == "NAN_COMPONENT"


def test_technical_timestamp_mismatch():
    record = {"components": {}, "candle_timestamp": 0, "candle_close_timestamp": 3000}
    assert any(x["code"] == "TIMEFRAME_TIMESTAMP_MISMATCH" for x in technical_record_findings(record))


def test_technical_legacy_schema():
    record = {"strategy_name": "scored_candidate_v1", "components": {c: 1 for c in COMPONENTS}}
    assert any(x["code"] == "LEGACY_SCHEMA" for x in technical_record_findings(record))
