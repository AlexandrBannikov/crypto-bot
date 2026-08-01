import json

from app.candle import Candle
from app.factor_research import COMPONENTS, _market_outcomes, research
from scripts.factor_research import _csv, render_text
from scripts.factor_research import _timestamp


def candles(count: int = 120) -> tuple[Candle, ...]:
    result = []
    price = 100.0
    for index in range(count):
        drift = .4 if (index // 12) % 2 == 0 else -.25
        close = price + drift + ((index % 5) - 2) * .08
        result.append(Candle(index * 3600, price, max(price, close) + .6, min(price, close) - .5, close, 10 + index))
        price = close
    return tuple(result)


def test_framework_profiles_every_existing_factor() -> None:
    report = research(candles())
    assert report["mode"] == "analysis_only"
    assert set(report["factors"]) == set(COMPONENTS)
    assert {item["factor"] for item in report["ranking"]} == set(COMPONENTS)
    for profile in report["factors"].values():
        assert len(profile["distribution"]) == 5
        assert 0 <= profile["ranking_diagnostics"]["predictive_quality"] <= 100
        assert "return_24h" in profile["correlations"]
        assert "mfe_24h" in profile["correlations"]
        assert "mae_24h" in profile["correlations"]


def test_factor_independence_and_leave_one_out_are_complete() -> None:
    report = research(candles())
    matrix = report["factor_correlation_matrix"]
    assert set(matrix) == set(COMPONENTS)
    assert all(set(row) == set(COMPONENTS) for row in matrix.values())
    assert set(report["leave_one_factor_out"]) == set(COMPONENTS)
    assert all("mean_importance" in item for item in report["leave_one_factor_out"].values())


def test_future_outcomes_are_censored_and_causal() -> None:
    market = candles(70)
    last = _market_outcomes(market, len(market) - 1)
    assert all(value is None for value in last.values())
    earlier_before = _market_outcomes(market[:69], 63)
    earlier_after = _market_outcomes(market, 63)
    assert earlier_before["return_3h"] == earlier_after["return_3h"]
    assert earlier_before["return_6h"] is None
    assert earlier_after["return_6h"] is not None


def test_date_filters_select_setups_without_removing_indicator_warmup() -> None:
    market = candles()
    full = research(market)
    filtered = research(market, from_timestamp=100 * 3600, to_timestamp=110 * 3600)
    assert 0 < filtered["period"]["valid_setups"] < full["period"]["valid_setups"]
    assert filtered["period"]["from"] >= 100 * 3600
    assert filtered["period"]["to"] <= 110 * 3600


def test_human_json_and_csv_outputs_are_serializable() -> None:
    report = research(candles())
    assert "Predictive quality ranking" in render_text(report)
    assert "record_type,factor,bucket" in _csv(report)
    assert json.loads(json.dumps(report))["framework"] == "scored_candidate_factor_research_v1"


def test_good_bad_near_miss_and_false_signal_sections_exist() -> None:
    report = research(candles(), strong_move_percent=.1, cohort_size=5)
    assert report["good_trades"]["count"] == 5
    assert report["bad_trades"]["count"] == 5
    assert "strong_positive" in report["near_miss_55_to_threshold"]
    assert "primary_limiter" in report["false_negatives"]
    assert "primary_limiter" in report["false_positives"]
    assert "highest_utilization_factor" in report["false_positives"]


def test_cli_date_parser_accepts_dates_and_utc_timestamps() -> None:
    assert _timestamp("2026-07-01") == _timestamp("2026-07-01T00:00:00Z")
