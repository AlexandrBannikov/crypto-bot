from __future__ import annotations

from dataclasses import asdict
import json
import math

import pytest

from app.candle import Candle
from app.scored_component_analysis import (
    COMPONENTS, ComponentObservation, analyze_observations, component_distribution,
    replay_closed_candles, select_period, zero_streaks,
)
from app.scored_component_calibration import replay as legacy_replay
from app.signal_scoring import SignalScoreConfig
from scripts import analyze_scored_components as cli


MAXIMA = SignalScoreConfig().maxima


def observations(values, component="trend"):
    rows = []
    for i, value in enumerate(values):
        components = {name: MAXIMA[name] * .5 for name in COMPONENTS}
        components[component] = value
        rows.append(ComponentObservation(i * 3600, (i + 1) * 3600, 100 + i, sum(components.values()), components, "RANGE_NORMAL", trend_distance_atr=0.0, trend_spread_change=0.0))
    return rows


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("kind", ("zero", "mixed", "maximum"))
def test_component_distribution_core_cases(component, kind):
    maximum = MAXIMA[component]
    values = {"zero": [0] * 5, "mixed": [0, maximum*.25, maximum*.5, maximum*.75, maximum], "maximum": [maximum] * 5}[kind]
    result = component_distribution(values, maximum)
    assert result.count == 5
    assert result.minimum is not None
    assert 0 <= result.percentages["exactly_zero"] <= 100
    assert sum(result.bins.values()) == 5


@pytest.mark.parametrize("percentile", ("p5", "p10", "p25", "p50", "p75", "p90", "p95"))
def test_percentiles_are_bounded(percentile):
    result = component_distribution(range(11), 10)
    assert 0 <= result.percentiles[percentile] <= 10


@pytest.mark.parametrize("length", (0, 1, 2, 3, 6, 12, 24, 48))
def test_single_zero_streak_lengths(length):
    rows = observations([0] * length + [1])
    result = zero_streaks(rows, "trend")
    assert result["longest"] == length
    assert result["current"] == 0


@pytest.mark.parametrize("threshold", (3, 6, 12, 24, 48))
def test_streak_threshold_counts(threshold):
    rows = observations([0] * threshold + [1, 0, 1])
    result = zero_streaks(rows, "trend")
    assert result["series"][f"{threshold}plus"] == 1


@pytest.mark.parametrize("values,expected,current", [
    ([1, 1], 0, 0), ([0], 1, 1), ([1, 0, 0], 2, 2),
    ([0, 0, 1, 0], 2, 1), ([0, 1, 0, 0, 1], 2, 0),
])
def test_streak_shapes(values, expected, current):
    result = zero_streaks(observations(values), "trend")
    assert result["longest"] == expected
    assert result["current"] == current


@pytest.mark.parametrize("horizon", (1, 3, 6, 12, 24))
def test_forward_outcomes_are_strictly_after_t(horizon):
    rows = observations([MAXIMA["trend"]] * 30)
    report = asdict(analyze_observations(rows, period="all", horizons=(horizon,)))
    high = report["forward_outcomes"]["components"]["trend"]["groups"]["high"][str(horizon)]
    assert high["count"] == 30 - horizon
    assert high["mean"] > 0


@pytest.mark.parametrize("count", (1, 2, 3, 5, 10, 20))
def test_forward_tail_is_censored(count):
    rows = observations([1] * count)
    report = asdict(analyze_observations(rows, period="all", horizons=(24,)))
    assert report["forward_outcomes"]["components"]["trend"]["groups"]["low"]["24"]["count"] == 0


@pytest.mark.parametrize("score", (0, 19.999, 20, 39.999, 40, 49.999, 50, 64.999, 65, 79.999, 80, 100))
def test_score_bands_cover_boundaries(score):
    row = observations([1])[0]
    row = ComponentObservation(row.timestamp, row.close_timestamp, row.market_price, score, row.components, row.regime, trend_distance_atr=0.0, trend_spread_change=0.0)
    report = asdict(analyze_observations([row], period="all"))
    assert sum(x["count"] for x in report["score_distribution"]["bands"].values()) == 1


def candles(count=100):
    return tuple(Candle(i*3600, 100+i*.1, 101+i*.1, 99+i*.1, 100.2+i*.1, 10) for i in range(count))


def test_vector_replay_matches_runtime_formula():
    market = candles()
    actual, quality = replay_closed_candles(market)
    expected = [x for x in legacy_replay(market) if not x["hard_blocks"]]
    assert len(actual) == len(expected) == 35
    for left, right in zip(actual, expected):
        assert left.score == pytest.approx(right["total_score"])
        assert left.components == pytest.approx(right["components"])
    assert quality["warmup_excluded"] == 65


def test_replay_is_causal_no_lookahead():
    market = candles()
    before, _ = replay_closed_candles(market[:-1])
    after, _ = replay_closed_candles(market)
    assert before == after[:-1]


def test_duplicate_candles_are_reported_and_deduplicated():
    market = candles(70)
    rows, quality = replay_closed_candles(market + (market[-1],))
    assert quality["duplicate_candles"] == 1
    assert len(rows) == 5


def test_nan_market_data_is_excluded():
    market = list(candles(70)); market[-1] = Candle(market[-1].timestamp, 1, 2, 1, math.nan, 1)
    rows, _ = replay_closed_candles(market)
    assert all(math.isfinite(x.score) for x in rows)


def test_empty_distribution_has_no_nan():
    payload = json.dumps(asdict(component_distribution([], 25)), allow_nan=False)
    assert "NaN" not in payload


def test_threshold_reachability_never_and_sometimes():
    low = observations([0] * 10)
    for i, row in enumerate(low):
        low[i] = ComponentObservation(row.timestamp, row.close_timestamp, row.market_price, 0,
                                      {c: 0 for c in COMPONENTS}, row.regime, trend_distance_atr=0.0, trend_spread_change=0.0)
    assert asdict(analyze_observations(low, period="all"))["threshold_reachability"]["physically_capable_65"] == 0
    high = observations([MAXIMA["trend"]] * 10)
    assert asdict(analyze_observations(high, period="all"))["threshold_reachability"]["physically_capable_65"] == 10


def test_effective_formula_ceiling_documents_unreachable_pullback_max():
    report = asdict(analyze_observations(observations([1]), period="all"))
    reach = report["threshold_reachability"]
    assert reach["configured_formula_maximum"] == 100
    assert reach["effective_formula_ceiling"] == pytest.approx(95.5)
    assert "PULLBACK_CONFIGURED_MAX_UNREACHABLE" in {x["code"] for x in report["technical_findings"]}


def test_limiter_ties_are_deterministic():
    report = asdict(analyze_observations(observations([MAXIMA["trend"]*.5] * 5), period="all"))
    assert sum(x["limiter_1_pct"] for x in report["limiter_frequency"]["components"].values()) == pytest.approx(100)


def test_pairs_and_triples_are_reported():
    report = asdict(analyze_observations(observations([0, 1, 2]), period="all"))
    assert report["limiter_frequency"]["pairs"]
    assert report["limiter_frequency"]["triples"]


def test_counterfactuals_are_diagnostic_only():
    report = asdict(analyze_observations(observations([0, 1]), period="all", include_counterfactuals=True))
    assert report["counterfactuals"]["labels"] == ["DIAGNOSTIC_ONLY", "NOT_A_TRADING_RECOMMENDATION", "NO_PRODUCTION_CHANGE"]


def test_default_counterfactual_does_nothing():
    report = asdict(analyze_observations(observations([0]), period="all"))
    assert report["counterfactuals"] == {"status": "NOT_REQUESTED"}


@pytest.mark.parametrize("period,expected", (("1d", 24), ("2d", 48), ("all", 100)))
def test_period_selection(period, expected):
    assert len(select_period(candles(), period)) == expected


@pytest.mark.parametrize("period", ("", "0d", "-1d", "week", "1h"))
def test_invalid_period(period):
    with pytest.raises(ValueError): select_period(candles(), period)


def test_cli_default_does_not_write(tmp_path, capsys):
    path = tmp_path / "market.csv"
    path.write_text("datetime,open,high,low,close,volume\n" + "\n".join(
        f"1970-01-01 {i:02d}:00:00+00:00,100,101,99,100,10" for i in range(24)), encoding="utf-8")
    assert cli.main(["--data", str(path), "--period", "all", "--json"]) == 0
    assert sorted(x.name for x in tmp_path.iterdir()) == ["market.csv"]
    assert json.loads(capsys.readouterr().out)["recommendation_status"] == "ANALYSIS_ONLY"


def test_explicit_cli_output_is_only_write(tmp_path):
    path = tmp_path / "market.csv"; output = tmp_path / "report.json"
    path.write_text("datetime,open,high,low,close,volume\n" + "\n".join(
        f"1970-01-{1+i//24:02d} {i%24:02d}:00:00+00:00,100,101,99,100,10" for i in range(70)), encoding="utf-8")
    assert cli.main(["--data", str(path), "--period", "all", "--output", str(output)]) == 0
    assert json.loads(output.read_text())["recommendation_status"] == "ANALYSIS_ONLY"


def test_report_schema_and_json_are_complete():
    report = asdict(analyze_observations(observations([0, 1, 2]), period="all"))
    required = {"period", "start", "end", "observations", "data_source", "data_quality", "component_distributions",
        "zero_streaks", "score_distribution", "threshold_reachability", "limiter_frequency", "regime_breakdown",
        "time_breakdown", "forward_outcomes", "score_outcomes", "counterfactuals", "technical_findings",
        "limitations", "verdict", "recommendation_status", "trend_v2_diagnostics"}
    assert required == set(report)
    json.dumps(report, allow_nan=False)


def test_analysis_does_not_mutate_observations():
    rows = observations([0, 1, 2]); before = repr(rows)
    analyze_observations(rows, period="all", include_counterfactuals=True)
    assert repr(rows) == before
