"""Read-only component calibration for scored-candidate research.

This module never produces decisions, orders, trades, state, or equity files.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from math import isfinite
from statistics import mean, median, pstdev
from typing import Sequence

import pandas as pd

from app.candle import Candle
from app.risk_allocation import RiskAllocationConfig, risk_fraction, size_for_score
from app.signal_scoring import SignalScoreConfig, evaluate_signal
from app.trading_types import PositionSide


COMPONENTS = ("trend", "ema_alignment", "adx", "pullback", "momentum", "volatility", "cost")
HORIZONS = (1, 3, 6, 12, 24)
MFE_HORIZONS = (6, 12, 24)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def pullback_raw(candle: Candle, ema_fast: float, config: SignalScoreConfig) -> dict[str, float | str]:
    """Reproduce the current pullback inputs without changing production code."""
    scale = max(ema_fast, 1e-12)
    touch = _clamp((ema_fast - candle.low) / (scale * config.pullback_tolerance))
    near = _clamp(1.0 - abs(candle.close - ema_fast) / (scale * config.pullback_tolerance))
    retrace = _clamp((ema_fast - candle.close) / (scale * config.pullback_retrace))
    raw = _clamp(0.4 * touch + 0.4 * near + 0.2 * retrace)
    low_distance = (candle.low - ema_fast) / scale
    close_distance = (candle.close - ema_fast) / scale
    if close_distance < -config.pullback_retrace or low_distance < -2 * config.pullback_tolerance:
        zone = "deep_pullback"
    elif touch > 0 and abs(close_distance) <= config.pullback_tolerance:
        zone = "normal_pullback"
    elif low_distance <= config.pullback_tolerance:
        zone = "shallow_pullback"
    else:
        zone = "no_pullback"
    return {
        "touch": touch,
        "near": near,
        "retrace": retrace,
        "composite": raw,
        "low_distance_from_ema": low_distance,
        "close_distance_from_ema": close_distance,
        "zone": zone,
    }


def replay(candles: Sequence[Candle], config: SignalScoreConfig = SignalScoreConfig()) -> list[dict]:
    records: list[dict] = []
    ordered = tuple(sorted(candles, key=lambda candle: candle.timestamp))
    for index, candle in enumerate(ordered):
        score = evaluate_signal(ordered[:index + 1], config)
        if "insufficient_data" in score.hard_blocks:
            records.append({
                "candle_timestamp": candle.timestamp,
                "candle_close_timestamp": candle.timestamp + 3600,
                "total_score": float(score.total_score),
                "components": {name: 0.0 for name in COMPONENTS},
                "hard_blocks": list(score.hard_blocks),
            })
            continue
        raw = pullback_raw(candle, float(score.indicators["ema_fast"]), config)
        components = {name: float(getattr(score, f"{name}_score")) for name in COMPONENTS}
        records.append({
            "candle_timestamp": candle.timestamp,
            "candle_close_timestamp": candle.timestamp + 3600,
            "total_score": float(score.total_score),
            "components": components,
            "raw_pullback": raw,
            "raw_adx": float(score.indicators["adx"]),
            "trend_structure_valid": bool(score.indicators["ema_fast"] > score.indicators["ema_slow"]),
            "hard_blocks": list(score.hard_blocks),
        })
    return records


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    series = pd.Series(values, dtype="float64")
    return float(series.quantile(percentile))


def _describe(values: Sequence[float], maximum: float) -> dict:
    return {
        "maximum_contribution": maximum,
        "min": min(values) if values else None,
        "mean": mean(values) if values else None,
        "median": median(values) if values else None,
        "max": max(values) if values else None,
        "standard_deviation": pstdev(values) if values else None,
        "p10": _percentile(values, .10),
        "p25": _percentile(values, .25),
        "p50": _percentile(values, .50),
        "p75": _percentile(values, .75),
        "p90": _percentile(values, .90),
        "utilization_percent": mean(values) / maximum * 100 if values and maximum else None,
        "mean_deficit": maximum - mean(values) if values else None,
    }


def _outcome(candles: Sequence[Candle], index: int, horizon: int) -> dict[str, float] | None:
    if index + horizon >= len(candles):
        return None
    entry = float(candles[index].close)
    future = candles[index + 1:index + horizon + 1]
    return {
        "return": (float(candles[index + horizon].close) / entry - 1) * 100,
        "mfe": (max(float(candle.high) for candle in future) / entry - 1) * 100,
        "mae": (min(float(candle.low) for candle in future) / entry - 1) * 100,
    }


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return float(pd.Series(xs).rank(method="average").corr(pd.Series(ys).rank(method="average")))


def _outcome_summary(values: Sequence[float]) -> dict:
    clean = [float(value) for value in values if isfinite(value)]
    return {
        "sample_size": len(clean),
        "mean": mean(clean) if clean else None,
        "median": median(clean) if clean else None,
        "positive_rate_percent": sum(value > 0 for value in clean) / len(clean) * 100 if clean else None,
        "downside_p10": _percentile(clean, .10),
        "worst": min(clean) if clean else None,
    }


def analyze(records: Sequence[dict], candles: Sequence[Candle], *, threshold: float = 65.0) -> dict:
    valid = [row for row in records if not row.get("hard_blocks")]
    maxima = SignalScoreConfig().maxima
    limiter_counts = {name: [0, 0, 0] for name in COMPONENTS}
    for row in valid:
        ranked = sorted(COMPONENTS, key=lambda name: row["components"][name] / maxima[name])
        for name in COMPONENTS:
            for rank in range(3):
                limiter_counts[name][rank] += int(name in ranked[:rank + 1])
    component_summary = {}
    for name in COMPONENTS:
        values = [row["components"][name] for row in valid]
        component_summary[name] = {
            **_describe(values, maxima[name]),
            "primary_limiter_percent": limiter_counts[name][0] / len(valid) * 100 if valid else 0,
            "top_2_limiter_percent": limiter_counts[name][1] / len(valid) * 100 if valid else 0,
            "top_3_limiter_percent": limiter_counts[name][2] / len(valid) * 100 if valid else 0,
        }

    candle_index = {candle.timestamp: index for index, candle in enumerate(candles)}
    enriched = []
    for row in valid:
        index = candle_index.get(int(row["candle_timestamp"]))
        outcomes = {}
        if index is not None:
            for horizon in HORIZONS:
                item = _outcome(candles, index, horizon)
                outcomes[f"return_{horizon}h"] = item["return"] if item else None
            for horizon in MFE_HORIZONS:
                item = _outcome(candles, index, horizon)
                outcomes[f"mfe_{horizon}h"] = item["mfe"] if item else None
                outcomes[f"mae_{horizon}h"] = item["mae"] if item else None
        enriched.append({**row, "outcomes": outcomes})

    pb_values = [row["components"]["pullback"] for row in valid]
    pb_bucket_bounds = ((0, .1), (.1, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.0000001))
    pullback_buckets = {}
    for low, high in pb_bucket_bounds:
        selected = [row for row in enriched if low <= row["components"]["pullback"] / maxima["pullback"] < high]
        pullback_buckets[f"{low * 100:g}-{min(high, 1) * 100:g}%"] = {
            "count": len(selected),
            **{f"return_{horizon}h": _outcome_summary([row["outcomes"].get(f"return_{horizon}h") for row in selected if row["outcomes"].get(f"return_{horizon}h") is not None]) for horizon in HORIZONS},
        }
    correlations = {}
    for component in ("pullback", "adx"):
        correlations[component] = {}
        for metric in [*(f"return_{h}h" for h in HORIZONS), *(f"mfe_{h}h" for h in MFE_HORIZONS), *(f"mae_{h}h" for h in MFE_HORIZONS)]:
            pairs = [(row["components"][component], row["outcomes"].get(metric)) for row in enriched if row["outcomes"].get(metric) is not None]
            correlations[component][metric] = {"sample_size": len(pairs), "spearman": _spearman([x for x, _ in pairs], [y for _, y in pairs])}

    marginal = {}
    for component, replacements in {
        "pullback": ("zero", "median", "p75", "max"),
        "adx": ("zero", "median", "p75"),
    }.items():
        values = [row["components"][component] for row in valid]
        replacement_values = {"zero": 0.0, "median": median(values), "p75": _percentile(values, .75), "max": maxima[component]}
        marginal[component] = {}
        for label in replacements:
            replacement = float(replacement_values[label])
            crossings = [row for row in enriched if row["total_score"] < threshold <= row["total_score"] - row["components"][component] + replacement]
            future = [row["outcomes"].get("return_24h") for row in crossings if row["outcomes"].get("return_24h") is not None]
            mfes = [row["outcomes"].get("mfe_24h") for row in crossings if row["outcomes"].get("mfe_24h") is not None]
            maes = [row["outcomes"].get("mae_24h") for row in crossings if row["outcomes"].get("mae_24h") is not None]
            fractions = [risk_fraction(row["total_score"] - row["components"][component] + replacement, RiskAllocationConfig()) for row in crossings]
            sizes = [size_for_score(
                score=row["total_score"] - row["components"][component] + replacement,
                balance=1000.0, entry_price=100.0, stop_loss=98.0,
                side=PositionSide.LONG, allocation=RiskAllocationConfig(),
            ) for row in crossings]
            positions = [item.position.position_value for item in sizes if item.position is not None]
            marginal[component][label] = {
                "replacement_contribution": replacement,
                "threshold_crossings": len(crossings),
                "return_24h": _outcome_summary(future),
                "mfe_24h_mean": mean(mfes) if mfes else None,
                "mae_24h_mean": mean(maes) if maes else None,
                "average_allocation": mean(fractions) if fractions else None,
                "average_hypothetical_position": mean(positions) if positions else None,
                "positions_below_5_usdt": sum(position < 5 for position in positions),
                "capital_cap_count": sum(position >= 1000 for position in positions),
                "fee_to_stop_risk_percent": 10.0 if fractions else None,
                "hard_blocks": dict(Counter(block for row in crossings for block in row.get("hard_blocks", []))),
            }

    good_trend = [row for row in enriched if row["trend_structure_valid"] and row["components"]["trend"] / maxima["trend"] >= .4 and row["components"]["ema_alignment"] / maxima["ema_alignment"] >= .5]
    pullback_only_crossings = [row for row in good_trend if row["total_score"] < threshold <= row["total_score"] - row["components"]["pullback"] + maxima["pullback"]]
    zones = Counter(str(row["raw_pullback"]["zone"]) if row.get("trend_structure_valid") else "structure_break" for row in valid)
    return {
        "valid_setup_decisions": len(valid),
        "excluded_insufficient_data": len(records) - len(valid),
        "threshold": threshold,
        "score": {
            **_describe([row["total_score"] for row in valid], 100.0),
            "above_threshold_count": sum(row["total_score"] >= threshold for row in valid),
        },
        "component_summary": component_summary,
        "primary_limiter": max(COMPONENTS, key=lambda name: component_summary[name]["primary_limiter_percent"]) if valid else None,
        "pullback": {
            "raw": _describe([float(row["raw_pullback"]["composite"]) for row in valid], 1.0),
            "score": _describe(pb_values, maxima["pullback"]),
            "utilization_buckets": pullback_buckets,
            "near_zero_count": sum(value <= maxima["pullback"] * .1 for value in pb_values),
            "zones": dict(zones),
            "good_trend_setups": len(good_trend),
            "good_trend_pullback_only_crossings": len(pullback_only_crossings),
            "near_threshold_raw_metrics": [row["raw_pullback"] for row in pullback_only_crossings],
        },
        "adx": {
            "raw": _describe([float(row["raw_adx"]) for row in valid], max(float(row["raw_adx"]) for row in valid) if valid else 1),
            "score": component_summary["adx"],
        },
        "correlations": correlations,
        "marginal_contribution": marginal,
        "current_pullback_function": {
            "formula": "20 * clamp(0.4*touch + 0.4*near + 0.2*retrace, 0, 1)",
            "touch": "clamp((EMA20-low)/(EMA20*0.0075), 0, 1)",
            "near": "clamp(1-abs(close-EMA20)/(EMA20*0.0075), 0, 1)",
            "retrace": "clamp((EMA20-close)/(EMA20*0.0075), 0, 1)",
            "continuous": True,
            "monotonic": False,
            "discontinuities": [],
            "kinks": ["touch saturation", "near at EMA20 and ±0.75%", "retrace at EMA20 and -0.75%"],
            "explicit_deep_pullback_penalty": False,
            "configured_zones": {
                "ideal": "not explicitly defined; highest composite occurs near EMA with an intrabar touch",
                "weak": "implicit through linear clamp terms",
                "invalid_or_deep": "no explicit invalid/deep zone or structure penalty inside pullback scoring",
            },
            "full_score_reachable": False,
            "observed_maximum": max(pb_values) if pb_values else None,
        },
        "safety": {
            "read_only": True,
            "runtime_decisions_changed": False,
            "threshold_changed": False,
            "score_config": asdict(SignalScoreConfig()),
            "risk_allocation": asdict(RiskAllocationConfig()),
        },
    }
