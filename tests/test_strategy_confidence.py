from datetime import datetime, timedelta, timezone

import pytest

from app.strategy_confidence import (
    ConfidenceLevel,
    PromotionConfig,
    calculate_confidence,
    compare_candidate,
    recommendation,
    rolling_metrics,
    stability_from_windows,
)


NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


def config(**changes):
    values = {
        "confidence_weights": {
            "sample": .25, "data_quality": .20, "performance": .10,
            "risk": .15, "stability": .20, "operational": .10,
        },
        "confidence_levels": (
            ConfidenceLevel("VERY_LOW", 0, 19),
            ConfidenceLevel("LOW", 20, 39),
            ConfidenceLevel("MODERATE", 40, 59),
            ConfidenceLevel("GOOD", 60, 79),
            ConfidenceLevel("HIGH", 80, 100),
        ),
        "minimum_days": 7,
        "minimum_closed_trades": 5,
        "minimum_comparable_candles": 20,
        "minimum_decisions": 50,
        "maximum_error_rate": .05,
        "minimum_profit_factor": 1.0,
        "maximum_drawdown_percent": 10.0,
        "ready_confidence": 65,
        "strong_confidence": 80,
        "strong_return_advantage_percent": 2.0,
        "rolling_periods": ("24h", "7d", "14d", "30d", "all"),
    }
    values.update(changes)
    return PromotionConfig(**values)


def metrics(**changes):
    values = {
        "closed_trades_count": 10,
        "number_of_decisions": 100,
        "number_of_errors": 0,
        "number_of_missing": 0,
        "observation_start": (NOW - timedelta(days=30)).isoformat(),
        "profit_factor": 1.5,
        "return_percent": "4",
        "max_drawdown_percent": "2",
        "equity": "1040",
        "total_pnl": "40",
        "fees": "2",
    }
    values.update(changes)
    return values


def windows(*returns):
    return {
        str(index): {
            "history_status": "available",
            "return_percent": value,
            "max_drawdown_percent": "2",
        }
        for index, value in enumerate(returns)
    }


def test_small_sample_and_one_profitable_trade_stay_low():
    item = metrics(
        closed_trades_count=1,
        number_of_decisions=5,
        observation_start=(NOW - timedelta(days=1)).isoformat(),
        profit_factor="N/A",
        return_percent="20",
    )
    result = calculate_confidence(
        item, comparable_candles=3, windows=windows("20"),
        operational={}, config=config(), now=NOW,
    )
    assert result["confidence_score"] <= 39
    assert result["components"]["performance_score"] <= 100


def test_na_pf_does_not_add_pf_credit_and_errors_reduce_score():
    clean = calculate_confidence(
        metrics(profit_factor="N/A"), comparable_candles=100,
        windows=windows("1", "2"), operational={}, config=config(), now=NOW,
    )
    errored = calculate_confidence(
        metrics(profit_factor="N/A", number_of_errors=30),
        comparable_candles=100, windows=windows("1", "2"),
        operational={}, config=config(), now=NOW,
    )
    assert clean["components"]["performance_score"] == 100
    assert errored["confidence_score"] < clean["confidence_score"]


def test_stable_data_increases_confidence():
    stable = calculate_confidence(
        metrics(), comparable_candles=100, windows=windows("1", "2", "3"),
        operational={}, config=config(), now=NOW,
    )
    unstable = calculate_confidence(
        metrics(), comparable_candles=100, windows=windows("5", "-5", "3"),
        operational={}, config=config(), now=NOW,
    )
    assert stable["confidence_score"] > unstable["confidence_score"]


@pytest.mark.parametrize(
    "change",
    [
        {"confidence_weights": {
            "sample": 1, "data_quality": 1, "performance": 1,
            "risk": 1, "stability": 1, "operational": 1,
        }},
        {"confidence_levels": (
            ConfidenceLevel("A", 0, 50), ConfidenceLevel("B", 50, 100)
        )},
        {"rolling_periods": ("0d",)},
        {"ready_confidence": 90, "strong_confidence": 80},
    ],
)
def test_configuration_validation(change):
    with pytest.raises(ValueError):
        config(**change)


def test_stability_statuses_and_recent_deterioration():
    assert stability_from_windows(windows("1"))["status"] == "UNAVAILABLE"
    assert stability_from_windows(windows("8", "-8"))["status"] == "UNSTABLE"
    assert stability_from_windows(windows("2", "-1", "1"))["status"] == "MIXED"
    assert stability_from_windows(windows("1", "1.1", "1.2"))["status"] in {
        "STABLE", "VERY_STABLE"
    }
    assert stability_from_windows(windows("-4", "-3", "-2"))[
        "recent_deterioration"
    ] is True


def base_comparison(**changes):
    result = {
        "candidate_better_return": True,
        "candidate_lower_drawdown": True,
        "candidate_better_pf": True,
        "candidate_more_stable": True,
        "candidate_fewer_errors": True,
        "delta_return": "3",
    }
    result.update(changes)
    return result


def confidence(score=70, status="STABLE", days=10, error_rate=0):
    return {
        "confidence_score": score,
        "confidence_level": "GOOD",
        "observation_days": days,
        "error_rate": error_rate,
        "stability": {"score": 70, "status": status},
    }


@pytest.mark.parametrize(
    ("candidate", "conf", "comparison", "comparable", "operational", "expected"),
    [
        (metrics(closed_trades_count=1), confidence(days=1), base_comparison(), 3, {}, "INSUFFICIENT_DATA"),
        (metrics(), confidence(score=50), base_comparison(), 30, {}, "CONTINUE_OBSERVATION"),
        (metrics(profit_factor=".5"), confidence(), base_comparison(), 30, {}, "REJECT_FOR_NOW"),
        (metrics(), confidence(score=70), base_comparison(), 30, {}, "READY_FOR_REVIEW"),
        (metrics(), confidence(score=90, status="VERY_STABLE"), base_comparison(delta_return="3"), 30, {}, "STRONG_CANDIDATE"),
        (metrics(), confidence(), base_comparison(), 30, {"active_halt": "risk"}, "INSUFFICIENT_DATA"),
        (metrics(), confidence(), base_comparison(), 30, {"timer_active": False}, "INSUFFICIENT_DATA"),
        (metrics(), confidence(), base_comparison(), 30, {"stale_data": True}, "INSUFFICIENT_DATA"),
    ],
)
def test_recommendation_states(
    candidate, conf, comparison, comparable, operational, expected
):
    result = recommendation(
        candidate, metrics(), conf, comparison,
        comparable_candles=comparable, operational=operational,
        config=config(),
    )
    assert result["recommendation"] == expected
    assert result["automatic_promotion"] is False


def test_comparison_preserves_na_and_directions():
    candidate = metrics(profit_factor="N/A", number_of_errors=1)
    production = metrics(
        return_percent="5", max_drawdown_percent="4",
        profit_factor="N/A", number_of_errors=3,
    )
    candidate_conf = confidence(score=80)
    production_conf = confidence(score=60)
    result = compare_candidate(
        candidate, production, candidate_conf, production_conf
    )
    assert result["candidate_better_return"] is False
    assert result["candidate_lower_drawdown"] is True
    assert result["candidate_better_pf"] == "N/A"
    assert result["candidate_fewer_errors"] is True
    assert result["delta_confidence"] == 20


def test_rolling_periods_and_insufficient_open_history(monkeypatch):
    calls = []

    def fake_report(_lab, *, period, now, timezone_name):
        calls.append(period)
        duration = (
            timedelta(hours=24)
            if period == "24h"
            else timedelta(days=int(period.removesuffix("d")))
            if period != "all"
            else None
        )
        start = None if duration is None else (NOW - duration).isoformat()
        return {
            "period": {"start": start},
            "strategies": {
                "production": {
                    **metrics(),
                    "period_realized_pnl": "5",
                    "number_of_missing": 0,
                    "win_rate": 50,
                    "fees": "1",
                    "exposure_percent": "0",
                    "daily_returns": [1, 2],
                    "open_position_status": "FLAT",
                    "opened_at": None,
                },
                "candidate": {
                    **metrics(
                        observation_start=(NOW - timedelta(days=1)).isoformat()
                    ),
                    "period_realized_pnl": "0",
                    "number_of_missing": 0,
                    "win_rate": "N/A",
                    "fees": "0",
                    "exposure_percent": "10",
                    "daily_returns": [],
                    "open_position_status": "OPEN",
                    "opened_at": (NOW - timedelta(days=2)).isoformat(),
                    "unrealized_pnl": "2",
                },
            },
        }

    monkeypatch.setattr(
        "app.strategy_confidence.build_report", fake_report
    )
    lab = object()
    result = rolling_metrics(
        lab, config(), now=NOW, timezone_name="UTC"
    )
    assert calls == ["24h", "7d", "14d", "30d", "all"]
    assert result["production"]["24h"]["history_status"] == "available"
    assert result["production"]["24h"]["daily_return_volatility"] == .5
    assert result["candidate"]["7d"]["history_status"] == "insufficient history"
    assert result["candidate"]["7d"]["pnl"] == "N/A"
    assert result["candidate"]["all"]["unrealized_pnl"] == "2"
