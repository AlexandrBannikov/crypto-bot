"""Read-only failure analysis for strong-trend/normal-volatility setups."""
from __future__ import annotations

from collections import Counter
from math import sqrt
from statistics import mean, median, pstdev
from typing import Sequence

import pandas as pd

from app.candle import Candle
from app.factor_research import _summary
from app.market_regime_research import RegimeResearchConfig, _frame, _score_rows
from app.scored_component_calibration import COMPONENTS
from app.signal_scoring import SignalScoreConfig


FEATURES = (
    "ema_spread_percent", "ema_slope_3_percent", "adx", "adx_slope_3",
    "atr", "atr_expansion_3_percent", "momentum", "pullback_depth_percent",
    "pullback_duration", "distance_from_ema_percent",
    "distance_from_recent_high_percent", "trend_age", "candles_after_crossover",
    "body_percent", "upper_wick_percent", "lower_wick_percent", "volume",
    "volume_ratio_20",
)


def _streak(values: Sequence[bool]) -> list[int]:
    result, count = [], 0
    for value in values:
        count = count + 1 if value else 0
        result.append(count)
    return result


def _direction_age(values: Sequence[int]) -> list[int]:
    result, previous, count = [], None, 0
    for value in values:
        count = count + 1 if value == previous else 1
        result.append(count)
        previous = value
    return result


def _features(candles: Sequence[Candle], config: RegimeResearchConfig) -> pd.DataFrame:
    frame = _frame(candles, config)
    frame["ema_slope_3_percent"] = frame["ema_fast"].pct_change(3) * 100
    frame["adx_slope_3"] = frame["adx"].diff(3)
    frame["atr_expansion_3_percent"] = frame["atr"].pct_change(3) * 100
    frame["momentum"] = (frame["close"] - frame["open"]) / frame["close"] * 100
    frame["pullback_depth_percent"] = ((frame["ema_fast"] - frame["low"]) / frame["ema_fast"] * 100).clip(lower=0)
    frame["distance_from_ema_percent"] = (frame["close"] - frame["ema_fast"]) / frame["ema_fast"] * 100
    frame["distance_from_recent_high_percent"] = (frame["close"] / frame["high"].rolling(20, min_periods=1).max() - 1) * 100
    trend_direction = (frame["ema_fast"] > frame["ema_slow"]).astype(int).tolist()
    frame["trend_age"] = _direction_age(trend_direction)
    frame["candles_after_crossover"] = frame["trend_age"]
    frame["pullback_duration"] = _streak((frame["close"] < frame["ema_fast"]).tolist())
    candle_range = (frame["high"] - frame["low"]).replace(0, float("nan"))
    body_high = frame[["open", "close"]].max(axis=1)
    body_low = frame[["open", "close"]].min(axis=1)
    frame["body_percent"] = (frame["close"] - frame["open"]).abs() / candle_range * 100
    frame["upper_wick_percent"] = (frame["high"] - body_high) / candle_range * 100
    frame["lower_wick_percent"] = (body_low - frame["low"]) / candle_range * 100
    frame["volume"] = [candle.volume for candle in sorted(candles, key=lambda item: item.timestamp)]
    frame["volume_ratio_20"] = frame["volume"] / frame["volume"].rolling(20, min_periods=1).mean()
    frame["adx_dynamic"] = frame["adx_slope_3"].map(lambda value: "rising" if value > .5 else "falling" if value < -.5 else "flat")
    spread_delta = frame["ema_spread_percent"].diff(3)
    frame["ema_dynamic"] = spread_delta.map(lambda value: "expanding" if value > .05 else "contracting" if value < -.05 else "flat")
    frame["atr_dynamic"] = frame["atr_expansion_3_percent"].map(lambda value: "expanding" if value > 2 else "contracting" if value < -2 else "flat")
    return frame


def _distribution(rows: Sequence[dict], feature: str) -> dict:
    return _summary([row["features"][feature] for row in rows if pd.notna(row["features"].get(feature))])


def _comparison(good: Sequence[dict], bad: Sequence[dict], feature: str) -> dict:
    left = [float(row["features"][feature]) for row in good if pd.notna(row["features"].get(feature))]
    right = [float(row["features"][feature]) for row in bad if pd.notna(row["features"].get(feature))]
    left_summary, right_summary = _summary(left), _summary(right)
    if left and right:
        difference = mean(left) - mean(right)
        se = sqrt((pstdev(left) ** 2 / len(left)) + (pstdev(right) ** 2 / len(right)))
        pooled_denominator = len(left) + len(right) - 2
        pooled = sqrt(((len(left) - 1) * pstdev(left) ** 2 + (len(right) - 1) * pstdev(right) ** 2) / pooled_denominator) if pooled_denominator > 0 else 0
        effect = difference / pooled if pooled else None
        ci = [difference - 1.96 * se, difference + 1.96 * se]
    else:
        difference = effect = None
        ci = [None, None]
    return {"feature": feature, "good": left_summary, "bad": right_summary, "mean_difference_good_minus_bad": difference, "cohens_d": effect, "mean_difference_95pct_ci": ci}


def _outcome(rows: Sequence[dict]) -> dict:
    returns = [float(row["outcomes"]["return_24h"]) for row in rows if row["outcomes"].get("return_24h") is not None]
    return {**_summary(returns), "positive_rate_percent": sum(value > 0 for value in returns) / len(returns) * 100 if returns else None}


def _bucket(rows: Sequence[dict], feature: str, bounds: Sequence[tuple[str, float | None, float | None]]) -> list[dict]:
    result = []
    for label, low, high in bounds:
        selected = [row for row in rows if (low is None or row["features"][feature] > low) and (high is None or row["features"][feature] <= high)]
        result.append({"bucket": label, "count": len(selected), "outcome_24h": _outcome(selected), "above_threshold": sum(row["total_score"] >= 65 for row in selected)})
    return result


def _dynamic(rows: Sequence[dict], feature: str) -> dict:
    return {label: {"count": len(selected), "outcome_24h": _outcome(selected)} for label in ("rising", "flat", "falling", "expanding", "contracting") if (selected := [row for row in rows if row["features"].get(feature) == label])}


def _explanation(row: dict, label: str) -> str:
    feature = row["features"]
    age = "young" if feature["trend_age"] <= 10 else "mature" if feature["trend_age"] <= 30 else "old"
    pullback = "short" if feature["pullback_duration"] <= 2 else "prolonged"
    momentum = "recovered" if feature["momentum"] > 0 else "negative"
    return (
        f"{label}: {age} trend ({feature['trend_age']:.0f} candles); "
        f"ADX {feature['adx_dynamic']} ({feature['adx']:.1f}, Δ3={feature['adx_slope_3']:.1f}); "
        f"EMA spread {feature['ema_dynamic']} ({feature['ema_spread_percent']:.2f}%); "
        f"ATR {feature['atr_dynamic']}; {pullback} pullback ({feature['pullback_duration']:.0f}, depth {feature['pullback_depth_percent']:.2f}%); "
        f"momentum {momentum} ({feature['momentum']:.2f}%); score {row['total_score']:.1f}; return24h {row['outcomes']['return_24h']:.2f}%"
    )


def analyze(candles: Sequence[Candle], *, from_timestamp: int | None = None, to_timestamp: int | None = None, config: RegimeResearchConfig = RegimeResearchConfig()) -> dict:
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    feature_frame = _features(ordered, config)
    score_rows = _score_rows(ordered, feature_frame, config)
    feature_by_timestamp = {int(item.timestamp): {name: getattr(item, name) for name in FEATURES + ("adx_dynamic", "ema_dynamic", "atr_dynamic")} for item in feature_frame.itertuples(index=False)}
    subset = []
    for row in score_rows:
        if row["regime"] != "strong_trend/normal_volatility" or row["outcomes"].get("return_24h") is None:
            continue
        if from_timestamp is not None and row["candle_close_timestamp"] < from_timestamp:
            continue
        if to_timestamp is not None and row["candle_close_timestamp"] > to_timestamp:
            continue
        subset.append({**row, "features": feature_by_timestamp[row["candle_timestamp"]]})
    good = [row for row in subset if row["total_score"] >= 65 and row["outcomes"]["return_24h"] > 0]
    bad = [row for row in subset if row["total_score"] >= 65 and row["outcomes"]["return_24h"] <= 0]
    missed = [row for row in subset if row["total_score"] < 65 and row["outcomes"]["return_24h"] >= config.strong_move_percent]
    groups = {"good": good, "bad": bad, "missed": missed}
    comparison = sorted((_comparison(good, bad, feature) for feature in FEATURES), key=lambda item: abs(item["cohens_d"] or 0), reverse=True)

    maxima = SignalScoreConfig().maxima
    def component_diagnostic(selected: Sequence[dict]) -> dict:
        limiter = Counter(min(COMPONENTS, key=lambda name: row["components"][name] / maxima[name]) for row in selected)
        return {"primary_limiter": dict(limiter), "mean_utilization": {name: mean(row["utilization"][name] for row in selected) if selected else None for name in COMPONENTS}, "mean_threshold_gap": mean(65 - row["total_score"] for row in selected) if selected else None}

    near = [row for row in subset if 60 <= row["total_score"] <= 70]
    near_good = [row for row in near if row["outcomes"]["return_24h"] > 0]
    near_bad = [row for row in near if row["outcomes"]["return_24h"] <= 0]
    ranked_good = sorted(good, key=lambda row: row["outcomes"]["return_24h"], reverse=True)[:50]
    ranked_bad = sorted(bad, key=lambda row: row["outcomes"]["return_24h"])[:50]
    overvaluation = sorted(({"factor": name, "bad_mean_utilization": mean(row["utilization"][name] for row in bad) if bad else None, "good_mean_utilization": mean(row["utilization"][name] for row in good) if good else None, "bad_minus_good": (mean(row["utilization"][name] for row in bad) - mean(row["utilization"][name] for row in good)) if bad and good else None} for name in COMPONENTS), key=lambda item: item["bad_minus_good"] or 0, reverse=True)

    return {
        "framework": "strong_trend_failure_analysis_v1", "mode": "analysis_only",
        "period": {"from": min((row["candle_close_timestamp"] for row in subset), default=None), "to": max((row["candle_close_timestamp"] for row in subset), default=None), "subset_count": len(subset)},
        "definitions": {"regime": "strong_trend/normal_volatility", "good": "score >=65 and return_24h >0", "bad": "score >=65 and return_24h <=0", "missed": "score <65 and return_24h >=2%", "slopes": "3-candle backward differences", "recent_high": "causal rolling 20-candle high", "confidence_interval": "normal 95% CI for difference of independent means; descriptive because outcomes overlap"},
        "groups": {name: {"count": len(rows), "outcome_24h": _outcome(rows), "feature_distributions": {feature: _distribution(rows, feature) for feature in FEATURES}} for name, rows in groups.items()},
        "good_vs_bad": comparison,
        "false_negatives": {"count": len(missed), **component_diagnostic(missed)},
        "false_positives": {"count": len(bad), **component_diagnostic(bad), "component_overvaluation": overvaluation},
        "near_threshold_60_70": {"count": len(near), "good": {"count": len(near_good), "outcome_24h": _outcome(near_good)}, "bad": {"count": len(near_bad), "outcome_24h": _outcome(near_bad)}, "feature_comparison": sorted((_comparison(near_good, near_bad, feature) for feature in FEATURES), key=lambda item: abs(item["cohens_d"] or 0), reverse=True)},
        "trend_age": _bucket(subset, "trend_age", (("1-5", 0, 5), ("6-10", 5, 10), ("11-20", 10, 20), ("21-30", 20, 30), ("31-40", 30, 40), ("41-50", 40, 50), (">50", 50, None))),
        "pullback_duration": _bucket(subset, "pullback_duration", (("0", None, 0), ("1-2", 0, 2), ("3-5", 2, 5), (">=6", 5, None))),
        "adx_dynamics": _dynamic(subset, "adx_dynamic"), "ema_dynamics": _dynamic(subset, "ema_dynamic"), "atr_dynamics": _dynamic(subset, "atr_dynamic"),
        "explainability": {"best_50": [{"timestamp": row["candle_close_timestamp"], "explanation": _explanation(row, "GOOD")} for row in ranked_good], "worst_50": [{"timestamp": row["candle_close_timestamp"], "explanation": _explanation(row, "BAD")} for row in ranked_bad]},
        "candidate_improvements": [
            "Do not add an ADX-falling penalty: this sample does not support it.",
            "Research EMA-spread magnitude jointly with expansion/contraction instead of relying only on absolute alignment.",
            "Do not add a simple old-trend penalty: age is non-monotonic; validate age bands on non-overlapping out-of-sample cohorts.",
            "Research pullback duration jointly with depth; GOOD signals have modestly deeper and longer pullbacks than BAD signals, but effects are small.",
            "Research distance from the recent high and volume confirmation as potential anti-chasing/context features for a future shadow-only v2.",
            "Revisit the saturated ADX and EMA-alignment contributions: both are near maximum in GOOD and BAD and barely discriminate outcomes.",
        ],
        "safety": {"read_only": True, "strategy_changed": False, "score_changed": False, "weights_changed": False, "threshold_changed": False, "risk_changed": False, "paper_changed": False, "real_changed": False, "systemd_changed": False, "candidate_created": False},
    }
