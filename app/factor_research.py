"""Read-only factor quality research for Scored Candidate.

The framework evaluates existing factor contributions. It never changes score
configuration, runtime decisions, state, execution, risk, or market data.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite
from statistics import mean, median, pstdev
from typing import Sequence

import pandas as pd

from app.candle import Candle
from app.scored_component_calibration import COMPONENTS, replay
from app.signal_scoring import SignalScoreConfig


RETURN_HORIZONS = (1, 3, 6, 12, 24)
EXCURSION_HORIZONS = (6, 12, 24)
BUCKETS = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 100.000001))


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    return float(pd.Series(values, dtype="float64").quantile(quantile)) if values else None


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return float(pd.Series(xs).rank(method="average").corr(pd.Series(ys).rank(method="average")))


def _summary(values: Sequence[float]) -> dict:
    clean = [float(value) for value in values if isfinite(float(value))]
    return {
        "count": len(clean),
        "min": min(clean) if clean else None,
        "max": max(clean) if clean else None,
        "mean": mean(clean) if clean else None,
        "median": median(clean) if clean else None,
        "standard_deviation": pstdev(clean) if clean else None,
        "percentiles": {f"p{int(q * 100)}": _percentile(clean, q) for q in (.10, .25, .50, .75, .90)},
    }


def _market_outcomes(candles: Sequence[Candle], index: int) -> dict[str, float | None]:
    entry = float(candles[index].close)
    outcomes: dict[str, float | None] = {}
    for horizon in RETURN_HORIZONS:
        outcomes[f"return_{horizon}h"] = (
            (float(candles[index + horizon].close) / entry - 1) * 100
            if index + horizon < len(candles) else None
        )
    for horizon in EXCURSION_HORIZONS:
        if index + horizon < len(candles):
            future = candles[index + 1:index + horizon + 1]
            outcomes[f"mfe_{horizon}h"] = (max(float(candle.high) for candle in future) / entry - 1) * 100
            outcomes[f"mae_{horizon}h"] = (min(float(candle.low) for candle in future) / entry - 1) * 100
        else:
            outcomes[f"mfe_{horizon}h"] = None
            outcomes[f"mae_{horizon}h"] = None
    return outcomes


def _outcome_stats(rows: Sequence[dict], metric: str) -> dict:
    values = [float(row["outcomes"][metric]) for row in rows if row["outcomes"].get(metric) is not None]
    base = _summary(values)
    return {
        **base,
        "positive_rate_percent": sum(value > 0 for value in values) / len(values) * 100 if values else None,
        "downside_p10": _percentile(values, .10),
        "worst": min(values) if values else None,
    }


def _factor_profile(rows: Sequence[dict], factor: str, maximum: float) -> dict:
    contributions = [float(row["components"][factor]) for row in rows]
    utilization = [value / maximum * 100 for value in contributions]
    correlations = {}
    metrics = [
        *(f"return_{horizon}h" for horizon in RETURN_HORIZONS),
        *(f"mfe_{horizon}h" for horizon in EXCURSION_HORIZONS),
        *(f"mae_{horizon}h" for horizon in EXCURSION_HORIZONS),
    ]
    for metric in metrics:
        pairs = [(u, row["outcomes"].get(metric)) for u, row in zip(utilization, rows) if row["outcomes"].get(metric) is not None]
        correlations[metric] = {
            "sample_size": len(pairs),
            "spearman": _spearman([x for x, _ in pairs], [float(y) for _, y in pairs]),
        }
    buckets = []
    for low, high in BUCKETS:
        selected = [row for row, value in zip(rows, utilization) if low <= value < high]
        buckets.append({
            "range": f"{low}-{min(high, 100):g}",
            "count": len(selected),
            "returns": {f"{horizon}h": _outcome_stats(selected, f"return_{horizon}h") for horizon in RETURN_HORIZONS},
            "mfe": {f"{horizon}h": _outcome_stats(selected, f"mfe_{horizon}h") for horizon in EXCURSION_HORIZONS},
            "mae": {f"{horizon}h": _outcome_stats(selected, f"mae_{horizon}h") for horizon in EXCURSION_HORIZONS},
        })
    return_correlations = [correlations[f"return_{horizon}h"]["spearman"] for horizon in RETURN_HORIZONS]
    excursion_correlations = [correlations["mfe_24h"]["spearman"], correlations["mae_24h"]["spearman"]]
    predictive = mean(value for value in return_correlations + excursion_correlations if value is not None) if any(value is not None for value in return_correlations + excursion_correlations) else 0.0
    populated = [bucket for bucket in buckets if bucket["returns"]["24h"]["median"] is not None]
    monotonicity = _spearman(
        list(range(len(populated))),
        [float(bucket["returns"]["24h"]["median"]) for bucket in populated],
    ) or 0.0
    quality = max(0.0, min(100.0, 100 * (0.7 * predictive + 0.3 * monotonicity)))
    return {
        "contribution": _summary(contributions),
        "utilization_percent": _summary(utilization),
        "distribution": buckets,
        "correlations": correlations,
        "ranking_diagnostics": {
            "mean_predictive_spearman": predictive,
            "bucket_24h_median_monotonicity": monotonicity,
            "predictive_quality": quality,
        },
    }


def _cohort(rows: Sequence[dict], *, highest: bool, count: int) -> dict:
    eligible = [row for row in rows if row["outcomes"].get("return_24h") is not None]
    selected = sorted(eligible, key=lambda row: row["outcomes"]["return_24h"], reverse=highest)[:count]
    return {
        "count": len(selected),
        "return_24h": _outcome_stats(selected, "return_24h"),
        "factor_mean_utilization": {
            factor: mean(row["utilization"][factor] for row in selected) if selected else None
            for factor in COMPONENTS
        },
        "examples": [{
            "candle_close_timestamp": row["candle_close_timestamp"],
            "score": row["total_score"],
            "return_24h": row["outcomes"]["return_24h"],
            "factor_utilization": row["utilization"],
        } for row in selected],
    }


def research(candles: Sequence[Candle], *, threshold: float = 65.0, strong_move_percent: float = 2.0, cohort_size: int = 20, from_timestamp: int | None = None, to_timestamp: int | None = None) -> dict:
    """Build a causal factor report on a single comparable candle set."""
    ordered = tuple(sorted(candles, key=lambda candle: candle.timestamp))
    raw_records = [row for row in replay(ordered) if not row.get("hard_blocks")]
    maxima = SignalScoreConfig().maxima
    candle_index = {candle.timestamp: index for index, candle in enumerate(ordered)}
    rows = []
    for row in raw_records:
        close_timestamp = int(row["candle_close_timestamp"])
        if from_timestamp is not None and close_timestamp < from_timestamp:
            continue
        if to_timestamp is not None and close_timestamp > to_timestamp:
            continue
        index = candle_index[int(row["candle_timestamp"])]
        rows.append({
            **row,
            "utilization": {factor: float(row["components"][factor]) / maxima[factor] * 100 for factor in COMPONENTS},
            "outcomes": _market_outcomes(ordered, index),
        })
    factors = {factor: _factor_profile(rows, factor, maxima[factor]) for factor in COMPONENTS}
    ranking = sorted(
        ({"factor": factor, "predictive_quality": profile["ranking_diagnostics"]["predictive_quality"]} for factor, profile in factors.items()),
        key=lambda item: item["predictive_quality"], reverse=True,
    )
    matrix = {}
    for left in COMPONENTS:
        matrix[left] = {}
        for right in COMPONENTS:
            matrix[left][right] = _spearman(
                [row["utilization"][left] for row in rows],
                [row["utilization"][right] for row in rows],
            )
    redundant = []
    for left_index, left in enumerate(COMPONENTS):
        for right in COMPONENTS[left_index + 1:]:
            correlation = matrix[left][right]
            if correlation is not None and abs(correlation) >= .80:
                redundant.append({"left": left, "right": right, "spearman": correlation})

    loo = {}
    for horizon in RETURN_HORIZONS:
        eligible = [row for row in rows if row["outcomes"].get(f"return_{horizon}h") is not None]
        outcomes = [float(row["outcomes"][f"return_{horizon}h"]) for row in eligible]
        baseline = _spearman([row["total_score"] for row in eligible], outcomes)
        for factor in COMPONENTS:
            without = _spearman([row["total_score"] - row["components"][factor] for row in eligible], outcomes)
            loo.setdefault(factor, {})[f"{horizon}h"] = {
                "baseline_spearman": baseline,
                "without_factor_spearman": without,
                "importance": baseline - without if baseline is not None and without is not None else None,
            }
    for factor in COMPONENTS:
        values = [item["importance"] for item in loo[factor].values() if item["importance"] is not None]
        loo[factor]["mean_importance"] = mean(values) if values else None

    def limiter(row: dict) -> str:
        return min(COMPONENTS, key=lambda factor: row["utilization"][factor])

    near_miss = [row for row in rows if 55 <= row["total_score"] < threshold and row["outcomes"].get("return_24h") is not None]
    near_good = [row for row in near_miss if row["outcomes"]["return_24h"] >= strong_move_percent]
    false_negatives = [row for row in rows if row["total_score"] < threshold and row["outcomes"].get("return_24h") is not None and row["outcomes"]["return_24h"] >= strong_move_percent]
    false_positives = [row for row in rows if row["total_score"] >= threshold and row["outcomes"].get("return_24h") is not None and row["outcomes"]["return_24h"] <= 0]

    def diagnostic(selected: Sequence[dict]) -> dict:
        return {
            "count": len(selected),
            "return_24h": _outcome_stats(selected, "return_24h"),
            "primary_limiter": dict(Counter(limiter(row) for row in selected)),
            "highest_utilization_factor": dict(Counter(
                max(COMPONENTS, key=lambda factor: row["utilization"][factor])
                for row in selected
            )),
            "factor_mean_utilization": {factor: mean(row["utilization"][factor] for row in selected) if selected else None for factor in COMPONENTS},
            "examples": [{
                "candle_close_timestamp": row["candle_close_timestamp"],
                "score": row["total_score"],
                "return_24h": row["outcomes"]["return_24h"],
                "primary_limiter": limiter(row),
                "factor_utilization": row["utilization"],
            } for row in selected[:20]],
        }

    return {
        "framework": "scored_candidate_factor_research_v1",
        "mode": "analysis_only",
        "period": {
            "from": min((row["candle_close_timestamp"] for row in rows), default=None),
            "to": max((row["candle_close_timestamp"] for row in rows), default=None),
            "candles": len(ordered),
            "valid_setups": len(rows),
            "filter_from": from_timestamp,
            "filter_to": to_timestamp,
        },
        "threshold": threshold,
        "strong_move_percent": strong_move_percent,
        "quality_metric": {
            "range": "0..100",
            "formula": "100 * max(0, 0.7 * mean predictive Spearman + 0.3 * 24h bucket-median monotonicity)",
            "predictive_inputs": [*(f"return_{h}h" for h in RETURN_HORIZONS), "mfe_24h", "mae_24h"],
            "interpretation": {"strong": ">=30", "moderate": "15..30", "weak": "5..15", "negligible": "<5"},
        },
        "ranking": ranking,
        "factors": factors,
        "factor_correlation_matrix": matrix,
        "redundant_factor_pairs": redundant,
        "leave_one_factor_out": loo,
        "good_trades": _cohort(rows, highest=True, count=cohort_size),
        "bad_trades": _cohort(rows, highest=False, count=cohort_size),
        "near_miss_55_to_threshold": {"all": diagnostic(near_miss), "strong_positive": diagnostic(near_good)},
        "false_negatives": diagnostic(false_negatives),
        "false_positives": diagnostic(false_positives),
        "safety": {
            "read_only": True,
            "look_ahead_in_factors": False,
            "runtime_models_created": False,
            "configuration_changed": False,
        },
    }
