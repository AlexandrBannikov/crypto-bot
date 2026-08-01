import json

from app.candle import Candle
from app.market_regime_research import COMPONENTS, RegimeResearchConfig, _frame, _score_rows, research
from app.scored_component_calibration import replay
from scripts.regime_research import render_csv, render_text


def candles(count: int = 500) -> tuple[Candle, ...]:
    result = []
    price = 100.0
    for index in range(count):
        drift = .45 if (index // 80) % 2 == 0 else -.30
        close = price + drift + ((index % 7) - 3) * .12
        result.append(Candle(index * 3600, price, max(price, close) + .8, min(price, close) - .7, close, 100 + index))
        price = close
    return tuple(result)


def test_every_classified_candle_has_exactly_one_transparent_regime() -> None:
    report = research(candles())
    assert report["classification"]["causal"] is True
    assert report["classification"]["type"] == "deterministic_composite"
    assert sum(item["candle_count"] for item in report["regimes"].values()) <= report["period"]["candles"]
    assert all("/" in name for name in report["regimes"])
    assert abs(sum(item["history_share_percent"] for item in report["regimes"].values()) - 100) < 1e-9


def test_regime_reports_all_factors_outcomes_and_heatmap() -> None:
    report = research(candles())
    for regime, item in report["regimes"].items():
        assert {factor["factor"] for factor in item["factor_ranking"]} == set(COMPONENTS)
        assert "average_atr" in item and "average_adx" in item and "average_ema_spread_percent" in item
        assert "positive_rate_percent" in item["outcome_24h"]
        assert set(report["heatmap"][regime]) == set(COMPONENTS)
        assert all("mfe_24h_mean" in factor and "mae_24h_mean" in factor for factor in item["factor_ranking"])


def test_stability_transitions_and_diagnostics_are_present() -> None:
    report = research(candles())
    assert set(report["rolling_analysis"]) == {"90d", "180d", "365d"}
    assert len(report["factor_stability"]) == len(COMPONENTS)
    assert "by_regime" in report["near_threshold_60_65"]
    assert "by_regime" in report["false_negatives"]
    assert "by_regime" in report["false_positives"]


def test_filters_outputs_and_safety() -> None:
    full = research(candles())
    filtered = research(candles(), from_timestamp=300 * 3600, to_timestamp=400 * 3600)
    assert filtered["period"]["candles"] < full["period"]["candles"]
    assert all(filtered["safety"].values()) is False  # mixed explicit unchanged flags
    assert filtered["safety"]["read_only"] is True
    assert "Market Regime Research" in render_text(filtered)
    assert render_csv(filtered).startswith("regime,candle_count")
    assert json.loads(json.dumps(filtered))["mode"] == "analysis_only"


def test_invalid_regime_bounds_are_rejected() -> None:
    try:
        RegimeResearchConfig(range_adx_below=25)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid bounds accepted")


def test_vectorized_research_score_matches_production_score_definition() -> None:
    market = candles(100)
    config = RegimeResearchConfig()
    fast = _score_rows(market, _frame(market, config), config)
    reference = {row["candle_timestamp"]: row for row in replay(market) if not row["hard_blocks"]}
    assert fast
    for row in fast:
        expected = reference[row["candle_timestamp"]]
        assert abs(row["total_score"] - expected["total_score"]) < 1e-9
        assert all(abs(row["components"][name] - expected["components"][name]) < 1e-9 for name in COMPONENTS)
