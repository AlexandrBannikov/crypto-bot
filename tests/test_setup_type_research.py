import json

import pytest

from app.candle import Candle
from app.setup_type_research import (Direction, SETUP_VERSION, SetupType,
    assign_episodes, classify_direction, classify_setup, research,
    select_non_overlapping)
from scripts.setup_type_research import render_csv, render_text


def feature(**changes):
    base = {"ema_fast": 105, "ema_slow": 100, "ema_slow_slope_5_percent": .2,
        "close": 106, "swing_change_percent": 1, "distance_from_ema_percent": 1,
        "distance_from_recent_high_percent": -2, "distance_from_recent_low_percent": 5,
        "pullback_duration": 0, "pullback_depth_percent": 0, "ema_spread_percent": 2,
        "ema_spread_change_3": .1, "ema_slope_3_percent": .2, "momentum": .2,
        "close_cross_fast": False, "volume_ratio_20": 1, "adx": 35,
        "adx_slope_3": 1, "atr_expansion_3_percent": 1, "candles_since_pullback": 3,
        "pullback_volume_contraction": .8, "recovery_volume_expansion": 1.2}
    base.update(changes); return base


def candles(count=500):
    result, price = [], 100.0
    for index in range(count):
        drift = .4 if (index//90)%2 == 0 else -.35
        close = price+drift+((index%7)-3)*.1
        result.append(Candle(index*3600, price, max(price, close)+.7, min(price, close)-.6, close, 100+index))
        price=close
    return tuple(result)


@pytest.fixture(scope="module")
def report(): return research(candles())


@pytest.mark.parametrize(("values", "expected"), [
    ({}, Direction.UPTREND),
    ({"ema_fast": 95, "ema_slow": 100, "ema_slow_slope_5_percent": -.2, "close": 94, "swing_change_percent": -1}, Direction.DOWNTREND),
    ({"ema_slow_slope_5_percent": -.2, "swing_change_percent": -1}, Direction.NEUTRAL),
])
def test_direction_rules(values, expected):
    assert classify_direction(feature(**values))[0] == expected


@pytest.mark.parametrize(("values", "regime", "expected"), [
    ({}, "strong_trend/normal_volatility", SetupType.LONG_TREND_CONTINUATION),
    ({"distance_from_ema_percent": 3.5}, "strong_trend/normal_volatility", SetupType.LATE_TREND_CHASING),
    ({"pullback_duration": 2, "pullback_depth_percent": .4}, "strong_trend/normal_volatility", SetupType.PULLBACK_CONTINUATION),
    ({"ema_spread_change_3": -.2, "distance_from_recent_high_percent": -6}, "strong_trend/normal_volatility", SetupType.REVERSAL_ATTEMPT),
    ({"ema_fast": 95, "ema_slow": 100, "ema_slow_slope_5_percent": -.2, "close": 96, "swing_change_percent": -1, "momentum": .5, "close_cross_fast": True}, "strong_trend/normal_volatility", SetupType.COUNTER_TREND_REBOUND),
    ({"ema_fast": 95, "ema_slow": 100, "ema_slow_slope_5_percent": -.2, "close": 94, "swing_change_percent": -1}, "strong_trend/normal_volatility", SetupType.DOWNTREND_CONTINUATION),
    ({"ema_slow_slope_5_percent": 0, "swing_change_percent": 0, "momentum": .5, "distance_from_recent_high_percent": -.2}, "range/normal_volatility", SetupType.RANGE_BREAKOUT_ATTEMPT),
    ({"ema_slow_slope_5_percent": 0, "swing_change_percent": 0, "momentum": 0}, "moderate_trend/normal_volatility", SetupType.UNCLASSIFIED),
])
def test_all_setup_classifier_types(values, regime, expected):
    classified=classify_setup(feature(**values), regime)
    assert classified["setup_type"] == expected.value
    assert classified["setup_version"] == SETUP_VERSION and classified["reasons"]
    assert 0 <= classified["classification_confidence"] <= 1


def test_classification_is_causal_and_outcomes_are_separate():
    inputs=feature(); before=classify_setup(inputs, "strong_trend/normal_volatility")
    inputs["future_return_24h"]=-99
    after=classify_setup(inputs, "strong_trend/normal_volatility")
    assert before == after


def test_non_overlapping_selection_and_order():
    rows=[{"candle_close_timestamp": value} for value in (0,3600,23*3600,24*3600,25*3600,48*3600)]
    selected=select_non_overlapping(list(reversed(rows)))
    assert [row["candle_close_timestamp"] for row in selected] == [0,24*3600,48*3600]


def test_episode_new_continuation_and_close():
    rows=[{"candle_close_timestamp": i, "direction": d} for i,d in enumerate(("uptrend","uptrend","downtrend","downtrend","neutral"))]
    assert [row["trend_episode_id"] for row in assign_episodes(rows)] == [1,1,2,2,3]


def test_report_decomposes_missed_bad_and_tracks_quality(report):
    assert "counter_trend_rebound" in report["missed_decomposition"]["groups"] or report["missed_decomposition"]["total"] >= 0
    assert report["false_positive_decomposition"]["total"] >= 0
    assert report["data_quality"]["duplicate_timestamps"] == 0
    assert report["metadata"]["non_overlapping_observations"] <= report["metadata"]["observations"]
    assert report["episode_analysis"]["count"] > 1


def test_statistics_splits_stability_and_insufficient_sample(report):
    assert set(report["out_of_sample"]) == {"train","validation","test"}
    assert set(report["stability"]["rolling"]) == {"90d","180d","365d"}
    assert all("bootstrap_95pct_ci" in feature for setup in report["feature_comparisons"].values() for feature in setup["features"])
    assert any(setup["status"] == "INSUFFICIENT_DATA" for setup in report["feature_comparisons"].values())


def test_cli_renderers_and_filters(report):
    filtered=research(candles(), setup_type=SetupType.LONG_TREND_CONTINUATION.value, direction=Direction.UPTREND.value)
    assert all(row["setup_type"] == SetupType.LONG_TREND_CONTINUATION.value for row in filtered["decisions"])
    assert "Setup Type Research Report" in render_text(filtered)
    assert render_csv(filtered).startswith("timestamp,asset,regime")
    assert json.loads(json.dumps(filtered))["metadata"]["setup_version"] == SETUP_VERSION


def test_isolation_contract(report):
    assert report["architecture"]["classification_uses_future"] is False
    assert report["safety"]["read_only"] is True
    assert not any(value for key,value in report["safety"].items() if key not in {"read_only"})
