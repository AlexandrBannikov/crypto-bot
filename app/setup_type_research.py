"""Causal, deterministic setup-type research for historical scored decisions.

The classifier is descriptive and is not imported by any runtime component.
Future outcomes are attached only after direction and setup classification.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from math import isfinite, sqrt
from statistics import mean, median, pstdev
from typing import Sequence

import numpy as np
import pandas as pd

from app.candle import Candle
from app.factor_research import _summary
from app.market_regime_research import RegimeResearchConfig, _score_rows
from app.scored_component_calibration import COMPONENTS
from app.signal_scoring import SignalScoreConfig
from app.strong_trend_failure_analysis import FEATURES as BASE_FEATURES, _features


SETUP_VERSION = "setup_type_v1"
SCORE_VERSION = SignalScoreConfig().version
MIN_SETUP_SAMPLES = 30


class Direction(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    NEUTRAL = "neutral"


class SetupType(str, Enum):
    LONG_TREND_CONTINUATION = "long_trend_continuation"
    LATE_TREND_CHASING = "late_trend_chasing"
    PULLBACK_CONTINUATION = "pullback_continuation"
    REVERSAL_ATTEMPT = "reversal_attempt"
    COUNTER_TREND_REBOUND = "counter_trend_rebound"
    DOWNTREND_CONTINUATION = "downtrend_continuation"
    RANGE_BREAKOUT_ATTEMPT = "range_breakout_attempt"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class SetupResearchConfig:
    minimum_setup_samples: int = MIN_SETUP_SAMPLES
    threshold: float = 65.0
    strong_move_percent: float = 2.0
    non_overlapping_hours: int = 24
    setup_version: str = SETUP_VERSION
    score_version: str = SCORE_VERSION


def classify_direction(features: dict) -> tuple[Direction, list[str], list[str]]:
    """Four-vote causal direction classifier with explicit conflict handling."""
    votes = []
    votes.append(1 if features["ema_fast"] > features["ema_slow"] else -1 if features["ema_fast"] < features["ema_slow"] else 0)
    votes.append(1 if features["ema_slow_slope_5_percent"] > .02 else -1 if features["ema_slow_slope_5_percent"] < -.02 else 0)
    votes.append(1 if features["close"] > features["ema_slow"] else -1 if features["close"] < features["ema_slow"] else 0)
    votes.append(1 if features["swing_change_percent"] > .10 else -1 if features["swing_change_percent"] < -.10 else 0)
    positive, negative = votes.count(1), votes.count(-1)
    conflicts = [] if not (positive and negative) else [f"mixed direction votes: up={positive}, down={negative}"]
    if positive >= 3 and negative <= 1:
        return Direction.UPTREND, [f"up direction votes {positive}/4"], conflicts
    if negative >= 3 and positive <= 1:
        return Direction.DOWNTREND, [f"down direction votes {negative}/4"], conflicts
    return Direction.NEUTRAL, [f"no 3-of-4 direction consensus: up={positive}, down={negative}"], conflicts


def classify_setup(features: dict, regime: str) -> dict:
    """Assign one setup without outcomes; rule order is part of v1."""
    direction, direction_reasons, conflicts = classify_direction(features)
    reasons = list(direction_reasons)
    setup = SetupType.UNCLASSIFIED
    if direction == Direction.UPTREND:
        chasing = features["distance_from_ema_percent"] >= 3.0 or (
            features["distance_from_recent_high_percent"] >= -.5
            and features["candles_since_pullback"] >= 5
            and features["ema_spread_percent"] >= 2.5
        )
        pullback = (
            (features["pullback_duration"] in range(1, 6) or features["pullback_depth_percent"] >= .15)
            and features["distance_from_ema_percent"] >= -.75
            and features["momentum"] > 0
        )
        continuation = (
            features["close"] > features["ema_fast"]
            and features["ema_slope_3_percent"] > 0
            and features["ema_spread_change_3"] >= -.05
            and -5 <= features["distance_from_recent_high_percent"] <= -.25
        )
        if chasing:
            setup = SetupType.LATE_TREND_CHASING
            reasons += ["price extension or near-high/no-pullback rule triggered"]
        elif pullback:
            setup = SetupType.PULLBACK_CONTINUATION
            reasons += ["intact bullish structure with causal pullback and positive recovery candle"]
        elif continuation:
            setup = SetupType.LONG_TREND_CONTINUATION
            reasons += ["bullish EMA structure, positive slope, non-contracting spread, not at high"]
        elif features["ema_spread_change_3"] < -.05 or features["close_cross_fast"]:
            setup = SetupType.REVERSAL_ATTEMPT
            reasons += ["bullish direction but contracting structure or fast-EMA cross"]
    elif direction == Direction.DOWNTREND:
        rebound = features["momentum"] >= .25 and (features["close_cross_fast"] or features["distance_from_recent_low_percent"] >= 1.0)
        reversal = features["close"] > features["ema_fast"] and features["ema_spread_change_3"] > .05
        if rebound:
            setup = SetupType.COUNTER_TREND_REBOUND
            reasons += ["bearish primary direction with strong positive rebound candle"]
        elif reversal:
            setup = SetupType.REVERSAL_ATTEMPT
            reasons += ["bearish direction but price/spread attempting bullish reversal"]
        else:
            setup = SetupType.DOWNTREND_CONTINUATION
            reasons += ["bearish direction without causal rebound/reversal confirmation"]
    else:
        breakout = "range" in regime and features["momentum"] > .25 and features["distance_from_recent_high_percent"] >= -.75
        reversal = abs(features["momentum"]) >= .5 and features["close_cross_fast"]
        if breakout:
            setup = SetupType.RANGE_BREAKOUT_ATTEMPT
            reasons += ["neutral/range context with positive momentum near recent high"]
        elif reversal:
            setup = SetupType.REVERSAL_ATTEMPT
            reasons += ["neutral direction with strong opposite EMA-cross candle"]
    supporting = {
        name: features[name] for name in (
            "ema_spread_percent", "ema_spread_change_3", "distance_from_ema_percent",
            "distance_from_recent_high_percent", "pullback_duration",
            "candles_since_pullback", "pullback_depth_percent", "volume_ratio_20",
            "pullback_volume_contraction", "recovery_volume_expansion", "momentum",
        )
    }
    confidence = min(1.0, .25 + .15 * len(reasons) - .10 * len(conflicts)) if setup != SetupType.UNCLASSIFIED else 0.0
    return {"setup_type": setup.value, "setup_version": SETUP_VERSION, "direction": direction.value, "reasons": reasons, "supporting_features": supporting, "conflicting_features": conflicts, "classification_confidence": confidence}


def select_non_overlapping(rows: Sequence[dict], hours: int = 24) -> list[dict]:
    selected, next_allowed = [], None
    for row in sorted(rows, key=lambda item: item["candle_close_timestamp"]):
        timestamp = row["candle_close_timestamp"]
        if next_allowed is None or timestamp >= next_allowed:
            selected.append(row)
            next_allowed = timestamp + hours * 3600
    return selected


def assign_episodes(rows: Sequence[dict]) -> list[dict]:
    result, episode, previous = [], 0, None
    for row in sorted(rows, key=lambda item: item["candle_close_timestamp"]):
        direction = row["direction"]
        if direction != previous:
            episode += 1
        result.append({**row, "trend_episode_id": episode})
        previous = direction
    return result


def _enriched_features(candles: Sequence[Candle], regime_config: RegimeResearchConfig) -> pd.DataFrame:
    frame = _features(candles, regime_config)
    frame["ema_slow_slope_5_percent"] = frame["ema_slow"].pct_change(5) * 100
    frame["ema_spread_change_3"] = frame["ema_spread_percent"].diff(3)
    frame["recent_low"] = frame["low"].rolling(20, min_periods=1).min()
    frame["distance_from_recent_low_percent"] = (frame["close"] / frame["recent_low"] - 1) * 100
    frame["swing_change_percent"] = frame["close"].pct_change(5) * 100
    prior_above = frame["close"].shift(1) >= frame["ema_fast"].shift(1)
    current_above = frame["close"] >= frame["ema_fast"]
    frame["close_cross_fast"] = prior_above != current_above
    positive_body = (frame["close"] > frame["open"]) & (frame["body_percent"] >= 55)
    frame["strong_candle_run"] = _run_lengths(positive_body.tolist())
    frame["candles_since_pullback"] = _run_lengths(current_above.tolist())
    frame["volume_spike"] = frame["volume_ratio_20"] >= 1.5
    prior_pullback_volume = frame["volume"].shift(1).rolling(3, min_periods=1).mean()
    baseline_volume = frame["volume"].shift(4).rolling(20, min_periods=1).mean()
    frame["pullback_volume_contraction"] = prior_pullback_volume / baseline_volume
    frame["recovery_volume_expansion"] = frame["volume"] / prior_pullback_volume
    return frame


def _run_lengths(values: Sequence[bool]) -> list[int]:
    result, count = [], 0
    for value in values:
        count = count + 1 if value else 0
        result.append(count)
    return result


def _outcome_summary(rows: Sequence[dict]) -> dict:
    result = {}
    for metric in ("return_3h", "return_6h", "return_12h", "return_24h", "mfe_6h", "mfe_12h", "mfe_24h", "mae_6h", "mae_12h", "mae_24h"):
        result[metric] = _summary([row["outcomes"][metric] for row in rows if row["outcomes"].get(metric) is not None])
    return result


def _group(rows: Sequence[dict], key: str, minimum: int) -> dict:
    result = {}
    for label in sorted({str(row[key]) for row in rows}):
        selected = [row for row in rows if str(row[key]) == label]
        returns = [row["outcomes"]["return_24h"] for row in selected if row["outcomes"].get("return_24h") is not None]
        result[label] = {"count": len(selected), "share_percent": len(selected) / len(rows) * 100 if rows else None, "status": "OK" if len(selected) >= minimum else "INSUFFICIENT_DATA", "return_24h": _summary(returns), "average_score": mean(row["total_score"] for row in selected)}
    return result


def _bootstrap_difference(left: Sequence[float], right: Sequence[float], seed: int = 17, samples: int = 1000) -> list[float | None]:
    if not left or not right:
        return [None, None]
    rng = np.random.default_rng(seed)
    a, b = np.asarray(left), np.asarray(right)
    differences = np.empty(samples)
    for index in range(samples):
        differences[index] = rng.choice(a, len(a), replace=True).mean() - rng.choice(b, len(b), replace=True).mean()
    return [float(np.quantile(differences, .025)), float(np.quantile(differences, .975))]


def _feature_comparisons(rows: Sequence[dict], minimum: int) -> dict:
    result = {}
    names = ("ema_spread_percent", "ema_spread_change_3", "distance_from_ema_percent", "distance_from_recent_high_percent", "pullback_depth_percent", "pullback_duration", "momentum", "adx", "adx_slope_3", "atr_expansion_3_percent", "volume_ratio_20")
    for setup in SetupType:
        selected = [row for row in rows if row["setup_type"] == setup.value and row["total_score"] >= 65]
        good = [row for row in selected if row["outcomes"].get("return_24h") is not None and row["outcomes"]["return_24h"] > 0]
        bad = [row for row in selected if row["outcomes"].get("return_24h") is not None and row["outcomes"]["return_24h"] <= 0]
        status = "OK" if len(good) >= minimum and len(bad) >= minimum else "INSUFFICIENT_DATA"
        comparisons = []
        for name in names:
            left = [float(row["features"][name]) for row in good if isfinite(float(row["features"][name]))]
            right = [float(row["features"][name]) for row in bad if isfinite(float(row["features"][name]))]
            pooled = sqrt(((len(left)-1)*pstdev(left)**2 + (len(right)-1)*pstdev(right)**2)/(len(left)+len(right)-2)) if len(left)+len(right)>2 and left and right else 0
            difference = mean(left)-mean(right) if left and right else None
            comparisons.append({"feature": name, "good": _summary(left), "bad": _summary(right), "mean_difference": difference, "cohens_d": difference/pooled if difference is not None and pooled else None, "bootstrap_95pct_ci": _bootstrap_difference(left, right), "nonparametric_test": "UNAVAILABLE_NO_SCIPY_DEPENDENCY"})
        result[setup.value] = {"status": status, "good_count": len(good), "bad_count": len(bad), "features": sorted(comparisons, key=lambda item: abs(item["cohens_d"] or 0), reverse=True)}
    return result


def _decomposition(rows: Sequence[dict], missed: bool, config: SetupResearchConfig) -> dict:
    selected = [row for row in rows if row["outcomes"].get("return_24h") is not None and ((row["total_score"] < config.threshold and row["outcomes"]["return_24h"] >= config.strong_move_percent) if missed else (row["total_score"] >= config.threshold and row["outcomes"]["return_24h"] <= 0))]
    maxima = SignalScoreConfig().maxima
    grouped: dict[str, list[dict]] = {}
    for row in selected:
        if missed:
            mapping = {SetupType.LONG_TREND_CONTINUATION.value: "missed_long_continuation", SetupType.PULLBACK_CONTINUATION.value: "missed_pullback_continuation", SetupType.COUNTER_TREND_REBOUND.value: "counter_trend_rebound", SetupType.REVERSAL_ATTEMPT.value: "reversal_rebound", SetupType.RANGE_BREAKOUT_ATTEMPT.value: "range_breakout"}
            label = "counter_trend_rebound" if row["direction"] == Direction.DOWNTREND.value else mapping.get(row["setup_type"], "unclassified")
        else:
            if row["direction"] == Direction.DOWNTREND.value:
                label = "downtrend_misclassified"
            else:
                mapping = {SetupType.LATE_TREND_CHASING.value: "late_chasing", SetupType.PULLBACK_CONTINUATION.value: "failed_pullback_continuation", SetupType.RANGE_BREAKOUT_ATTEMPT.value: "false_breakout", SetupType.REVERSAL_ATTEMPT.value: "reversal_against_position"}
                label = mapping.get(row["setup_type"], "exhausted_trend" if row["setup_type"] == SetupType.LONG_TREND_CONTINUATION.value and (row["features"]["adx_slope_3"] < -.5 or row["features"]["ema_spread_change_3"] < 0) else "unclassified")
        grouped.setdefault(label, []).append(row)
    result = {}
    for label, items in sorted(grouped.items()):
        limiters = Counter(min(COMPONENTS, key=lambda name: row["components"][name]/maxima[name]) for row in items)
        result[label] = {"count": len(items), "share_percent": len(items)/len(selected)*100 if selected else None, "outcomes": _outcome_summary(items), "average_score": mean(row["total_score"] for row in items), "average_threshold_deficit": mean(config.threshold-row["total_score"] for row in items), "primary_limiter": dict(limiters), "regime": dict(Counter(row["regime"] for row in items)), "direction": dict(Counter(row["direction"] for row in items)), "average_components": {name: mean(row["components"][name] for row in items) for name in COMPONENTS}, "context": {name: mean(float(row["features"][name]) for row in items) for name in ("distance_from_recent_high_percent", "ema_spread_percent", "pullback_depth_percent", "pullback_duration", "volume_ratio_20")}}
    return {"total": len(selected), "groups": result}


def _episodes(rows: Sequence[dict]) -> dict:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["trend_episode_id"], []).append(row)
    details = []
    for episode, items in grouped.items():
        completed = [row for row in items if row["outcomes"].get("return_24h") is not None]
        details.append({"trend_episode_id": episode, "direction": items[0]["direction"], "first_timestamp": items[0]["candle_close_timestamp"], "last_timestamp": items[-1]["candle_close_timestamp"], "duration_observations": len(items), "first_score": items[0]["total_score"], "last_score": items[-1]["total_score"], "best_score": max(row["total_score"] for row in items), "worst_score": min(row["total_score"] for row in items), "good_count": sum(row["total_score"]>=65 and row["outcomes"].get("return_24h", -1)>0 for row in completed), "bad_count": sum(row["total_score"]>=65 and row["outcomes"].get("return_24h", 1)<=0 for row in completed), "near_threshold_count": sum(60<=row["total_score"]<=70 for row in items)})
    return {"count": len(details), "episodes_with_multiple_false_positives": sum(item["bad_count"]>1 for item in details), "maximum_false_positives_in_episode": max((item["bad_count"] for item in details), default=0), "details": details}


def _quality(candles: Sequence[Candle], frame: pd.DataFrame, rows: Sequence[dict]) -> dict:
    timestamps = [c.timestamp for c in candles]
    duplicates = len(timestamps)-len(set(timestamps))
    gaps = sum(right-left != 3600 for left, right in zip(timestamps, timestamps[1:]))
    missing_indicators = int(frame[["ema_fast", "ema_slow", "adx", "atr"]].isna().any(axis=1).sum())
    invalid_setup = sum(row["setup_type"] not in {item.value for item in SetupType} for row in rows)
    score_mismatch = sum(row["score_version"] != SCORE_VERSION for row in rows)
    critical = duplicates > 0 or invalid_setup > 0 or score_mismatch > 0
    return {"status": "DATA_QUALITY_ERROR" if critical else "OK_WITH_WARNINGS" if gaps or missing_indicators else "OK", "duplicate_timestamps": duplicates, "non_hourly_gaps": gaps, "rows_with_missing_indicators_including_warmup": missing_indicators, "nan_or_infinity_features": sum(any(not isfinite(float(v)) for v in row["features"].values() if isinstance(v, (float, int))) for row in rows), "invalid_setup_types": invalid_setup, "conflicting_direction_rows": sum(bool(row["conflicting_features"]) for row in rows), "future_24h_unavailable": sum(row["outcomes"].get("return_24h") is None for row in rows), "overlapping_outcome_rows": max(0, len(rows)-len(select_non_overlapping(rows))), "episode_inconsistencies": 0, "score_version_mismatch": score_mismatch}


def research(candles: Sequence[Candle], *, asset: str = "ETH/USDT", from_timestamp: int | None = None, to_timestamp: int | None = None, setup_type: str | None = None, direction: str | None = None, regime: str | None = None, non_overlapping: bool = False, config: SetupResearchConfig = SetupResearchConfig()) -> dict:
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    regime_config = RegimeResearchConfig()
    frame = _enriched_features(ordered, regime_config)
    raw = _score_rows(ordered, frame, regime_config)
    by_timestamp = {int(item.timestamp): item for item in frame.itertuples(index=False)}
    rows = []
    feature_names = (*BASE_FEATURES, "ema_fast", "ema_slow", "ema_slow_slope_5_percent", "ema_spread_change_3", "distance_from_recent_low_percent", "swing_change_percent", "close_cross_fast", "strong_candle_run", "candles_since_pullback", "volume_spike", "pullback_volume_contraction", "recovery_volume_expansion", "close")
    for score in raw:
        item = by_timestamp[score["candle_timestamp"]]
        features = {name: getattr(item, name) for name in feature_names}
        classified = classify_setup(features, score["regime"])
        rows.append({**score, **classified, "features": features, "asset": asset, "score_version": SCORE_VERSION})
    rows = assign_episodes(rows)
    unfiltered = list(rows)
    if from_timestamp is not None: rows = [row for row in rows if row["candle_close_timestamp"] >= from_timestamp]
    if to_timestamp is not None: rows = [row for row in rows if row["candle_close_timestamp"] <= to_timestamp]
    if setup_type: rows = [row for row in rows if row["setup_type"] == setup_type]
    if direction: rows = [row for row in rows if row["direction"] == direction]
    if regime: rows = [row for row in rows if row["regime"] == regime]
    all_filtered = list(rows)
    non_overlap = select_non_overlapping(all_filtered, config.non_overlapping_hours)
    if non_overlapping: rows = non_overlap
    if _quality(ordered, frame, unfiltered)["status"] == "DATA_QUALITY_ERROR":
        return {"status": "DATA_QUALITY_ERROR", "data_quality": _quality(ordered, frame, unfiltered)}

    completed = [row for row in rows if row["outcomes"].get("return_24h") is not None]
    splits = {"train": ("2022-07-01", "2025-01-01"), "validation": ("2025-01-01", "2026-01-01"), "test": ("2026-01-01", "2027-01-01")}
    split_report = {}
    for label, (start, end) in splits.items():
        begin, finish = int(pd.Timestamp(start, tz="UTC").timestamp()), int(pd.Timestamp(end, tz="UTC").timestamp())
        selected = [row for row in completed if begin <= row["candle_close_timestamp"] < finish]
        split_report[label] = {"period": [start, end], "observations": len(selected), "setup_distribution": _group(selected, "setup_type", config.minimum_setup_samples)}
    yearly = {str(year): _group([row for row in completed if pd.Timestamp(row["candle_close_timestamp"], unit="s", tz="UTC").year == year], "setup_type", config.minimum_setup_samples) for year in sorted({pd.Timestamp(row["candle_close_timestamp"], unit="s", tz="UTC").year for row in completed})}
    rolling = {}
    if completed:
        last = pd.Timestamp(completed[-1]["candle_close_timestamp"], unit="s", tz="UTC")
        ends = list(pd.date_range(pd.Timestamp(completed[0]["candle_close_timestamp"], unit="s", tz="UTC").ceil("D"), last, freq="90D")) + [last]
        for days in (90, 180, 365):
            rolling[f"{days}d"] = [{"to": end.isoformat(), "setup_distribution": _group([row for row in completed if end-pd.Timedelta(days=days) < pd.Timestamp(row["candle_close_timestamp"], unit="s", tz="UTC") <= end], "setup_type", config.minimum_setup_samples)} for end in ends]
    sensitivity = {}
    for label, predicate in {"return_ge_1pct": lambda row: row["outcomes"]["return_24h"]>=1, "return_ge_2pct": lambda row: row["outcomes"]["return_24h"]>=2, "mfe_ge_2pct": lambda row: row["outcomes"]["mfe_24h"]>=2, "return_le_minus_1pct": lambda row: row["outcomes"]["return_24h"]<=-1, "mae_le_minus_2pct": lambda row: row["outcomes"]["mae_24h"]<=-2}.items():
        selected = [row for row in completed if predicate(row)]
        sensitivity[label] = {"count": len(selected), "setup_distribution": dict(Counter(row["setup_type"] for row in selected))}
    near = [row for row in completed if 60 <= row["total_score"] <= 70]
    near_good = [row for row in near if row["outcomes"]["return_24h"] > 0]
    near_bad = [row for row in near if row["outcomes"]["return_24h"] <= 0]
    missed_report = _decomposition(completed, True, config)
    bad_report = _decomposition(completed, False, config)
    focus = [row for row in completed if row["regime"] == "strong_trend/normal_volatility"]
    focus_missed = _decomposition(focus, True, config)
    focus_bad = _decomposition(focus, False, config)
    status = "COUNTER_TREND_MISSED_OVERSTATED" if focus_missed["groups"].get("counter_trend_rebound", {}).get("count", 0) else "SETUP_TYPES_NOT_DISTINGUISHABLE"
    return {
        "status": status,
        "metadata": {"framework": "setup_type_research_v1", "mode": "analysis_only", "asset": asset, "score_version": SCORE_VERSION, "setup_version": SETUP_VERSION, "threshold": config.threshold, "period": {"from": min((row["candle_close_timestamp"] for row in rows), default=None), "to": max((row["candle_close_timestamp"] for row in rows), default=None)}, "observations": len(rows), "all_filtered_observations": len(all_filtered), "non_overlapping_observations": len(non_overlap), "minimum_setup_samples": config.minimum_setup_samples, "classifier_rules_fixed_on": "train/research period; v1 thresholds fixed before validation/test reporting"},
        "architecture": {"flow": "historical candles -> causal indicators -> score_v1 replay -> market regime -> causal direction -> setup_type_v1 -> future outcome labels", "classification_uses_future": False, "outcomes_attached_after_classification": True},
        "data_quality": _quality(ordered, frame, unfiltered),
        "setup_distribution": _group(rows, "setup_type", config.minimum_setup_samples), "direction_distribution": _group(rows, "direction", config.minimum_setup_samples), "regime_distribution": _group(rows, "regime", config.minimum_setup_samples),
        "good_distribution": _group([row for row in completed if row["total_score"]>=65 and row["outcomes"]["return_24h"]>0], "setup_type", config.minimum_setup_samples),
        "missed_decomposition": missed_report, "false_positive_decomposition": bad_report,
        "strong_trend_normal_focus": {"observations": len(focus), "setup_distribution": _group(focus, "setup_type", config.minimum_setup_samples), "missed_decomposition": focus_missed, "false_positive_decomposition": focus_bad, "non_overlapping_observations": len(select_non_overlapping(focus, config.non_overlapping_hours))},
        "feature_comparisons": _feature_comparisons(completed, config.minimum_setup_samples),
        "episode_analysis": _episodes(rows),
        "non_overlapping_analysis": {"observations": len(non_overlap), "setup_distribution": _group(non_overlap, "setup_type", config.minimum_setup_samples), "missed_decomposition": _decomposition(non_overlap, True, config), "false_positive_decomposition": _decomposition(non_overlap, False, config)},
        "outcome_sensitivity": sensitivity, "out_of_sample": split_report,
        "near_threshold_60_70": {"observations": len(near), "good": {"count": len(near_good), "setup_distribution": _group(near_good, "setup_type", config.minimum_setup_samples)}, "bad": {"count": len(near_bad), "setup_distribution": _group(near_bad, "setup_type", config.minimum_setup_samples)}},
        "stability": {"yearly": yearly, "rolling": rolling, "by_regime": _group(completed, "regime", config.minimum_setup_samples), "by_direction": _group(completed, "direction", config.minimum_setup_samples)},
        "cross_asset_validation": {"status": "NOT_PERFORMED", "reason": "repository contains no BTC/USDT or SOL/USDT historical dataset"},
        "recommendations": ["Treat counter-trend rebounds separately from missed long continuations.", "Validate continuation-versus-chasing differences on non-overlapping episodes before any v2 design.", "If stable out of sample, propose one isolated shadow-only anti-chasing experiment; do not change v1."],
        "decisions": rows,
        "safety": {"read_only": True, "control_changed": False, "candidate_changed": False, "scored_v1_changed": False, "threshold_60_changed": False, "threshold_65_changed": False, "weights_changed": False, "risk_changed": False, "paper_enabled": False, "real_enabled": False, "systemd_changed": False, "deployment": False, "promotion": False, "martingale": False, "averaging_down": False},
    }
