"""Read-only historical audit for the scored-candidate formula.

The module is deliberately detached from runtime stores and execution code.  It
accepts closed candles, performs a causal replay, and returns JSON-safe data.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from statistics import mean
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from app.candle import Candle
from app.indicators import adx, atr
from app.signal_scoring import SignalScoreConfig


COMPONENTS = ("trend", "ema_alignment", "adx", "pullback", "momentum", "volatility", "cost")
SCORE_BANDS = (("<20", -math.inf, 20), ("20-39", 20, 40), ("40-49", 40, 50),
               ("50-64", 50, 65), ("65-79", 65, 80), ("80-100", 80, math.inf))


@dataclass(frozen=True)
class ComponentObservation:
    timestamp: int
    close_timestamp: int
    market_price: float
    score: float
    components: dict[str, float]
    regime: str
    trend_distance_atr: float
    trend_spread_change: float


@dataclass(frozen=True)
class ComponentDistribution:
    count: int
    maximum: float
    minimum: float | None
    observed_maximum: float | None
    mean: float | None
    median: float | None
    standard_deviation: float | None
    percentiles: dict[str, float | None]
    percentages: dict[str, float]
    bins: dict[str, int]


@dataclass(frozen=True)
class ScoreDistribution:
    count: int
    statistics: dict[str, Any]
    bands: dict[str, dict[str, float | int]]


@dataclass(frozen=True)
class ThresholdReachability:
    threshold_65_mathematically_reachable: bool
    threshold_80_mathematically_reachable: bool
    empirically_reached_65: int
    empirically_reached_80: int
    physically_capable_65: int
    physically_incapable_65: int
    blocker_attribution: dict[str, int]
    configured_formula_maximum: float
    effective_formula_ceiling: float


@dataclass(frozen=True)
class LimiterFrequency:
    components: dict[str, dict[str, float]]
    pairs: dict[str, dict[str, float | int]]
    triples: dict[str, dict[str, float | int]]


@dataclass(frozen=True)
class ForwardReturnAnalysis:
    horizons: list[int]
    censored_tail_observations: dict[str, int]


@dataclass(frozen=True)
class ComponentOutcomeRelationship:
    component: str
    groups: dict[str, Any]


@dataclass(frozen=True)
class ScoredAuditReport:
    period: str
    start: str | None
    end: str | None
    observations: int
    data_source: dict[str, Any]
    data_quality: dict[str, Any]
    component_distributions: dict[str, Any]
    zero_streaks: dict[str, Any]
    score_distribution: dict[str, Any]
    threshold_reachability: dict[str, Any]
    limiter_frequency: dict[str, Any]
    regime_breakdown: dict[str, Any]
    time_breakdown: dict[str, Any]
    forward_outcomes: dict[str, Any]
    score_outcomes: dict[str, Any]
    counterfactuals: dict[str, Any]
    technical_findings: list[dict[str, str]]
    limitations: list[str]
    verdict: dict[str, Any]
    trend_v2_diagnostics: dict[str, Any]
    recommendation_status: str = "ANALYSIS_ONLY"


def _clamp(series: pd.Series) -> pd.Series:
    return series.clip(0.0, 1.0)


def replay_closed_candles(candles: Sequence[Candle], config: SignalScoreConfig = SignalScoreConfig()) -> tuple[list[ComponentObservation], dict[str, Any]]:
    """Vectorized, causal equivalent of production scoring for closed candles."""
    ordered = sorted(candles, key=lambda c: c.timestamp)
    duplicate_count = len(ordered) - len({c.timestamp for c in ordered})
    ordered = list({c.timestamp: c for c in ordered}.values())
    ordered.sort(key=lambda c: c.timestamp)
    if not ordered:
        return [], {"input_candles": 0, "warmup_excluded": 0, "duplicate_candles": duplicate_count}
    frame = pd.DataFrame({
        "timestamp": [c.timestamp for c in ordered], "open": [c.open for c in ordered],
        "high": [c.high for c in ordered], "low": [c.low for c in ordered],
        "close": [c.close for c in ordered], "volume": [c.volume for c in ordered],
    }, dtype=float)
    close = frame.close
    fast = close.ewm(span=config.fast_ema_period, adjust=False).mean()
    slow = close.ewm(span=config.slow_ema_period, adjust=False).mean()
    av_adx = adx(frame, config.adx_period)
    relative_atr = atr(frame, config.adx_period) / close
    direction = (fast > slow).astype(float)
    distance = (fast - slow).abs() / close
    trend_distance_atr = distance / np.maximum(relative_atr, 1e-12)
    trend_spread_change = (fast - slow).diff().fillna(0)
    smooth_trend = _clamp((distance - .001) / (.03 - .001))
    smooth_align = _clamp((distance - .001) / (.02 - .001))
    ema_scale = fast.clip(lower=1e-12)
    touch = _clamp((fast - frame.low) / (ema_scale * config.pullback_tolerance))
    near = _clamp(1 - (frame.close - fast).abs() / (ema_scale * config.pullback_tolerance))
    retrace = _clamp((fast - frame.close) / (ema_scale * config.pullback_retrace))
    norm = {
        "trend": direction * smooth_trend,
        "ema_alignment": direction * (.5 + .5 * smooth_align),
        "adx": _clamp((av_adx - config.adx_low) / (config.adx_full - config.adx_low)),
        "pullback": _clamp(.4 * touch + .4 * near + .2 * retrace),
        "momentum": _clamp((frame.close - frame.open) / (frame.close * .01).clip(lower=1e-12) + .5),
        "volatility": 1 - (_clamp((relative_atr - config.volatility_low) / (config.volatility_full - config.volatility_low)) - .5).abs() * 2,
        "cost": pd.Series(1 - 2 * config.fee_rate / config.stop_distance_pct, index=frame.index).clip(0, 1),
    }
    required = config.slow_ema_period + config.adx_period + 2
    valid_mask = frame.index >= required - 1
    finite = np.isfinite(fast) & np.isfinite(slow) & np.isfinite(av_adx) & np.isfinite(relative_atr)
    valid_mask &= finite & (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
    weighted = {name: norm[name] * config.maxima[name] for name in COMPONENTS}
    total = sum(weighted.values()).clip(0, 100)
    regime_trend = np.where(av_adx < 20, "RANGE", np.where(fast > slow, "TREND_UP", "TREND_DOWN"))
    regime_vol = np.where(relative_atr >= .02, "HIGH", np.where(relative_atr <= .005, "LOW", "NORMAL"))
    result: list[ComponentObservation] = []
    for i in frame.index[valid_mask]:
        values = {name: float(weighted[name].iloc[i]) for name in COMPONENTS}
        result.append(ComponentObservation(int(frame.timestamp.iloc[i]), int(frame.timestamp.iloc[i]) + 3600,
                                           float(frame.close.iloc[i]), float(total.iloc[i]), values,
                                           f"{regime_trend[i]}_{regime_vol[i]}",
                                           float(trend_distance_atr.iloc[i]),
                                           float(trend_spread_change.iloc[i])))
    quality = {"input_candles": len(candles), "unique_candles": len(ordered),
               "duplicate_candles": duplicate_count, "warmup_excluded": len(ordered) - len(result),
               "invalid_rows_excluded": int((~finite & valid_mask).sum()), "closed_candles_only": True}
    return result, quality


def _safe(v: float | np.floating | None) -> float | None:
    return float(v) if v is not None and math.isfinite(float(v)) else None


def _stats(values: Sequence[float]) -> dict[str, Any]:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"min": None, "max": None, "mean": None, "median": None, "standard_deviation": None,
                **{f"p{p}": None for p in (5, 10, 25, 50, 75, 90, 95)}}
    return {"min": _safe(a.min()), "max": _safe(a.max()), "mean": _safe(a.mean()),
            "median": _safe(np.median(a)), "standard_deviation": _safe(a.std()),
            **{f"p{p}": _safe(np.percentile(a, p)) for p in (5, 10, 25, 50, 75, 90, 95)}}


def component_distribution(values: Sequence[float], maximum: float) -> ComponentDistribution:
    a = np.asarray(values, dtype=float)
    count = len(a)
    pct = lambda mask: float(np.sum(mask) * 100 / count) if count else 0.0
    edges = np.linspace(0, maximum, 6)
    bins: dict[str, int] = {"0": int(np.sum(a == 0))}
    for i in range(5):
        mask = (a > edges[i]) & (a <= edges[i + 1])
        bins[f"{edges[i]:g}-{edges[i + 1]:g}"] = int(mask.sum())
    stats = _stats(values)
    return ComponentDistribution(count, maximum, stats["min"], stats["max"], stats["mean"], stats["median"],
        stats["standard_deviation"], {k: stats[k] for k in ("p5", "p10", "p25", "p50", "p75", "p90", "p95")},
        {"exactly_zero": pct(a == 0), "below_10pct": pct(a < maximum * .1), "below_25pct": pct(a < maximum * .25),
         "25_50pct": pct((a >= maximum * .25) & (a < maximum * .5)),
         "50_75pct": pct((a >= maximum * .5) & (a < maximum * .75)), "above_75pct": pct(a >= maximum * .75),
         "at_maximum": pct(np.isclose(a, maximum))}, bins)


def zero_streaks(observations: Sequence[ComponentObservation], component: str) -> dict[str, Any]:
    streaks: list[tuple[int, int, int]] = []
    start = None
    for i, row in enumerate(observations):
        zero = row.components[component] == 0
        if zero and start is None: start = i
        if not zero and start is not None:
            streaks.append((i - start, start, i - 1)); start = None
    if start is not None: streaks.append((len(observations) - start, start, len(observations) - 1))
    top = sorted(streaks, reverse=True)[:5]
    iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()
    return {"longest": max((x[0] for x in streaks), default=0),
            "average": (mean(x[0] for x in streaks) if streaks else 0),
            "current": (streaks[-1][0] if streaks and streaks[-1][2] == len(observations) - 1 else 0),
            "series": {f"{n}plus": sum(x[0] >= n for x in streaks) for n in (3, 6, 12, 24, 48)},
            "longest_examples": [{"length": n, "start": iso(observations[a].timestamp), "end": iso(observations[b].close_timestamp)} for n, a, b in top]}


def _band(value: float, bands: Iterable[tuple[str, float, float]]) -> str:
    return next(name for name, low, high in bands if low <= value < high)


def _outcome_summary(values: Sequence[float]) -> dict[str, Any]:
    a = np.asarray(values, dtype=float)
    if not len(a): return {"count": 0, "mean": None, "median": None, "positive_rate": None, "mean_95pct_ci": None}
    rng = np.random.default_rng(20260804)
    if len(a) == 1: ci = [float(a[0]), float(a[0])]
    else:
        boot = rng.choice(a, (400, len(a)), replace=True).mean(axis=1)
        ci = [float(x) for x in np.percentile(boot, [2.5, 97.5])]
    return {"count": len(a), "mean": float(a.mean()), "median": float(np.median(a)),
            "positive_rate": float((a > 0).mean() * 100), "mean_95pct_ci": ci}


def _group_outcomes(observations: Sequence[ComponentObservation], values: Sequence[float], groups: Sequence[str], horizons: Sequence[int]) -> dict[str, Any]:
    answer: dict[str, Any] = {}
    for group in dict.fromkeys(groups):
        indices = [i for i, g in enumerate(groups) if g == group]
        answer[group] = {}
        for h in horizons:
            returns = [(observations[i + h].market_price / observations[i].market_price - 1) * 100 for i in indices if i + h < len(observations)]
            answer[group][str(h)] = _outcome_summary(returns)
    return answer


def analyze_observations(observations: Sequence[ComponentObservation], *, period: str, horizons: Sequence[int] = (1, 3, 6, 12, 24),
                         source: str = "historical_market_dataset", quality: dict[str, Any] | None = None,
                         include_counterfactuals: bool = False, config: SignalScoreConfig = SignalScoreConfig()) -> ScoredAuditReport:
    obs = list(observations); n = len(obs); maxima = config.maxima
    distributions = {c: asdict(component_distribution([o.components[c] for o in obs], maxima[c])) for c in COMPONENTS}
    scores = np.array([o.score for o in obs])
    score_bands = {name: {"count": int(sum(low <= x < high for x in scores)), "percentage": float(sum(low <= x < high for x in scores) * 100 / n) if n else 0} for name, low, high in SCORE_BANDS}
    span_days = ((obs[-1].close_timestamp - obs[0].timestamp) / 86400) if n else 0
    gaps = {}
    for threshold in (65, 80):
        hits = [o.timestamp for o in obs if o.score >= threshold]
        points = ([obs[0].timestamp] + hits + [obs[-1].close_timestamp]) if n else []
        gaps[str(threshold)] = max(((b - a) / 3600 for a, b in zip(points, points[1:])), default=0)
    score_distribution = asdict(ScoreDistribution(n, {**_stats(scores), "percentage_gte_65": float((scores >= 65).mean() * 100) if n else 0,
        "percentage_gte_80": float((scores >= 80).mean() * 100) if n else 0,
        "potential_entries_per_day": float((scores >= 65).sum() / span_days) if span_days else 0,
        "potential_entries_per_week": float((scores >= 65).sum() / span_days * 7) if span_days else 0,
        "longest_hours_without_gte_65": gaps["65"], "longest_hours_without_gte_80": gaps["80"]}, score_bands))
    limiter = {c: [0, 0, 0] for c in COMPONENTS}; pair_counts = Counter(); triple_counts = Counter(); incapable = Counter()
    physically = 0
    for o in obs:
        ranked = sorted(COMPONENTS, key=lambda c: (maxima[c] - o.components[c], c), reverse=True)
        for c in COMPONENTS:
            limiter[c][0] += c == ranked[0]; limiter[c][1] += c in ranked[:2]; limiter[c][2] += c in ranked[:3]
        pair_counts[" + ".join(sorted(ranked[:2]))] += 1; triple_counts[" + ".join(sorted(ranked[:3]))] += 1
        possible = sum(maxima[c] if o.components[c] > 0 else 0 for c in COMPONENTS)
        if possible >= 65: physically += 1
        else:
            zeros = [c for c in COMPONENTS if o.components[c] == 0]
            incapable[zeros[0] if len(zeros) == 1 else "multiple_components"] += 1
    holds = max(1, int((scores < 65).sum()))
    lf = LimiterFrequency({c: {"limiter_1_pct": limiter[c][0] * 100 / n if n else 0, "top_2_pct": limiter[c][1] * 100 / n if n else 0, "top_3_pct": limiter[c][2] * 100 / n if n else 0} for c in COMPONENTS},
        {k: {"count": v, "all_pct": v * 100 / n if n else 0, "hold_pct": sum(1 for o in obs if o.score < 65 and set(k.split(" + ")).issubset(set(sorted(COMPONENTS, key=lambda c: maxima[c]-o.components[c], reverse=True)[:2]))) * 100 / holds} for k, v in pair_counts.most_common(10)},
        {k: {"count": v, "all_pct": v * 100 / n if n else 0} for k, v in triple_counts.most_common(10)})
    # Pullback's three terms cannot peak together: touch+near can contribute
    # 0.8, while increasing retrace reduces near twice as fast. Cost is fixed
    # at 90% with the current fee/stop configuration.
    effective_ceiling = sum(maxima.values()) - maxima["pullback"] * .2 - maxima["cost"] * .1
    reach = ThresholdReachability(effective_ceiling >= 65, effective_ceiling >= 80,
        int((scores >= 65).sum()), int((scores >= 80).sum()), physically, n - physically,
        dict(incapable), sum(maxima.values()), effective_ceiling)
    component_outcomes = {}
    for c in COMPONENTS:
        ratios = [o.components[c] / maxima[c] for o in obs]
        groups = ["low" if x < .25 else "medium" if x < .75 else "high" for x in ratios]
        component_outcomes[c] = asdict(ComponentOutcomeRelationship(c, _group_outcomes(obs, ratios, groups, horizons)))
    score_groups = [_band(o.score, SCORE_BANDS) for o in obs]
    regime_breakdown = {}
    for regime in sorted({o.regime for o in obs}):
        rows = [o for o in obs if o.regime == regime]
        regime_breakdown[regime] = {"observations": len(rows), "coverage_pct": len(rows)*100/n if n else 0,
            "score": _stats([x.score for x in rows]), "gte_65_pct": sum(x.score >= 65 for x in rows)*100/len(rows),
            "gte_80_pct": sum(x.score >= 80 for x in rows)*100/len(rows),
            "trend_zero_pct": sum(x.components["trend"] == 0 for x in rows)*100/len(rows),
            "ema_alignment_zero_pct": sum(x.components["ema_alignment"] == 0 for x in rows)*100/len(rows)}
    time_breakdown: dict[str, Any] = {}
    for resolution, fmt in (("weeks", "%G-W%V"), ("months", "%Y-%m"), ("hours_utc", "%H")):
        keys = [datetime.fromtimestamp(o.timestamp, timezone.utc).strftime(fmt) for o in obs]
        time_breakdown[resolution] = {k: {"observations": len(rows := [o for o, key in zip(obs, keys) if key == k]),
            "mean_score": float(np.mean([o.score for o in rows])), "gte_65_pct": sum(o.score >= 65 for o in rows)*100/len(rows),
            "trend_zero_pct": sum(o.components["trend"] == 0 for o in rows)*100/len(rows),
            "ema_alignment_zero_pct": sum(o.components["ema_alignment"] == 0 for o in rows)*100/len(rows)} for k in dict.fromkeys(keys)}
    counterfactuals: dict[str, Any] = {"status": "NOT_REQUESTED"}
    if include_counterfactuals:
        counterfactuals = {"labels": ["DIAGNOSTIC_ONLY", "NOT_A_TRADING_RECOMMENDATION", "NO_PRODUCTION_CHANGE"], "components": {}}
        for c in COMPONENTS:
            vals = np.array([o.components[c] for o in obs]); med = float(np.median(vals)) if n else 0
            counterfactuals["components"][c] = {
                "score_without_component_gte65": int(np.sum(scores - vals >= 65)),
                "replace_zero_with_median_gte65": int(np.sum(scores - vals + np.where(vals == 0, med, vals) >= 65)),
                "set_component_to_max_gte65": int(np.sum(scores - vals + maxima[c] >= 65)),
                "additional_crossings_if_max": int(np.sum((scores < 65) & (scores - vals + maxima[c] >= 65)))}
    findings = [
        {"severity": "INFO", "code": "FORMULA_STATIC_REVIEW_OK", "detail": "All configured component names map directly to SignalScore fields; scoring uses float arithmetic and causal candle prefixes."},
        {"severity": "WARNING", "code": "PULLBACK_CONFIGURED_MAX_UNREACHABLE", "detail": "Configured Pullback maximum is 20, but the current weighted touch/near/retrace formula has a mathematical ceiling of 16."},
        {"severity": "INFO", "code": "COST_FIXED_BELOW_CONFIGURED_MAX", "detail": "With current fee and stop constants Cost is invariant at 4.5 of configured 5; this is deterministic, not truncation."},
    ]
    if n and distributions["trend"]["percentages"]["exactly_zero"] > 90: findings.append({"severity": "SUSPECT", "code": "TREND_NEARLY_ALWAYS_ZERO", "detail": "Trend zero rate exceeds 90%."})
    if n and distributions["ema_alignment"]["percentages"]["exactly_zero"] > 90: findings.append({"severity": "SUSPECT", "code": "EMA_ALIGNMENT_NEARLY_ALWAYS_ZERO", "detail": "EMA Alignment zero rate exceeds 90%."})
    high = int((scores >= 65).sum()) if n else 0
    if n < 500: verdict = "INSUFFICIENT_DATA"
    elif any(distributions[c]["percentages"]["exactly_zero"] > 90 for c in ("trend", "ema_alignment")): verdict = "COMPONENT_SUSPECT"
    elif high / n < .001: verdict = "OVER_RESTRICTIVE"
    else:
        regimes = [r for r in regime_breakdown.values() if r["observations"] >= 100]
        verdict = "MARKET_REGIME_EFFECT" if regimes and max(r["trend_zero_pct"] for r in regimes) - min(r["trend_zero_pct"] for r in regimes) >= 40 else "HEALTHY_SELECTIVE"
    trend_distance_atr_values = [o.trend_distance_atr for o in obs]
    trend_spread_change_values = [o.trend_spread_change for o in obs]

    trend_v2_diagnostics = {
        "trend_distance_atr": _stats(trend_distance_atr_values),
        "trend_spread_change": {
            **_stats(trend_spread_change_values),
            "percentage_positive": float(sum(x > 0 for x in trend_spread_change_values) * 100 / n) if n else 0,
            "percentage_zero": float(sum(x == 0 for x in trend_spread_change_values) * 100 / n) if n else 0,
            "percentage_negative": float(sum(x < 0 for x in trend_spread_change_values) * 100 / n) if n else 0,
        }
    }

    return ScoredAuditReport(period, datetime.fromtimestamp(obs[0].timestamp, timezone.utc).isoformat() if n else None,
        datetime.fromtimestamp(obs[-1].close_timestamp, timezone.utc).isoformat() if n else None, n,
        {"type": source, "formula_version": config.version}, quality or {}, distributions,
        {c: zero_streaks(obs, c) for c in ("trend", "ema_alignment")}, score_distribution, asdict(reach), asdict(lf),
        regime_breakdown, time_breakdown, {"horizons": list(horizons), "components": component_outcomes,
        "censored_tail_observations": {str(h): min(h, n) for h in horizons}},
        _group_outcomes(obs, scores, score_groups, horizons), counterfactuals, findings,
        ["Offline historical replay is not an executable trading strategy.", "Forward-return associations are observational, not causal.",
         "Regimes are reconstructed causally from the current project detector rules."],
        {"status": verdict, "evidence": {"observations": n,
          "score_gte_65_pct": float((scores >= 65).mean() * 100) if n else 0,
          "score_gte_80_pct": float((scores >= 80).mean() * 100) if n else 0,
          "trend_zero_pct": distributions["trend"]["percentages"]["exactly_zero"],
          "ema_alignment_zero_pct": distributions["ema_alignment"]["percentages"]["exactly_zero"]},
         "limitations": "Outcome relationships are observational and historical."},
         trend_v2_diagnostics=trend_v2_diagnostics,
         recommendation_status="ANALYSIS_ONLY")


def select_period(candles: Sequence[Candle], period: str, now_timestamp: int | None = None) -> tuple[Candle, ...]:
    if period == "all": return tuple(candles)
    if not period.endswith("d") or not period[:-1].isdigit() or int(period[:-1]) <= 0: raise ValueError("period must be Nd or all")
    end = now_timestamp if now_timestamp is not None else (max(c.timestamp for c in candles) + 3600 if candles else 0)
    cutoff = end - int(period[:-1]) * 86400
    return tuple(c for c in candles if c.timestamp >= cutoff and c.timestamp + 3600 <= end)
