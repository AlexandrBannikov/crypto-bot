import json

from app.candle import Candle
from app.strong_trend_failure_analysis import FEATURES, analyze
from scripts.analyze_strong_trend_failures import render_csv, render_text


def candles(count: int = 500) -> tuple[Candle, ...]:
    result, price = [], 100.0
    for index in range(count):
        drift = .45 if (index // 80) % 2 == 0 else -.30
        close = price + drift + ((index % 7) - 3) * .12
        result.append(Candle(index * 3600, price, max(price, close) + .8, min(price, close) - .7, close, 100 + index))
        price = close
    return tuple(result)


def test_analysis_is_scoped_and_has_three_groups() -> None:
    report = analyze(candles())
    assert report["mode"] == "analysis_only"
    assert set(report["groups"]) == {"good", "bad", "missed"}
    assert report["definitions"]["regime"] == "strong_trend/normal_volatility"
    assert all(set(group["feature_distributions"]) == set(FEATURES) for group in report["groups"].values())


def test_comparison_contains_statistics_effect_and_ci() -> None:
    report = analyze(candles())
    assert {item["feature"] for item in report["good_vs_bad"]} == set(FEATURES)
    for item in report["good_vs_bad"]:
        assert "percentiles" in item["good"] and "standard_deviation" in item["bad"]
        assert len(item["mean_difference_95pct_ci"]) == 2
        assert "cohens_d" in item


def test_hypotheses_explanations_and_safety_are_reported() -> None:
    report = analyze(candles())
    assert [item["bucket"] for item in report["trend_age"]] == ["1-5", "6-10", "11-20", "21-30", "31-40", "41-50", ">50"]
    assert [item["bucket"] for item in report["pullback_duration"]] == ["0", "1-2", "3-5", ">=6"]
    assert report["candidate_improvements"]
    assert report["safety"]["read_only"] and not report["safety"]["score_changed"]


def test_filters_and_output_formats() -> None:
    full = analyze(candles())
    filtered = analyze(candles(), from_timestamp=300 * 3600, to_timestamp=400 * 3600)
    assert filtered["period"]["subset_count"] <= full["period"]["subset_count"]
    assert "Strong Trend Failure Analysis" in render_text(filtered)
    assert render_csv(filtered).startswith("feature,good_count")
    assert json.loads(json.dumps(filtered))["framework"] == "strong_trend_failure_analysis_v1"
