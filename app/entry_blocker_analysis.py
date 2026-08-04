"""Read-only entry-blocker and near-miss diagnostics for scored candidate.

This module is intentionally outside the execution flow.  It classifies causal
closed-candle observations, attributes score deficits, and computes censored
forward outcomes.  It never reads or writes runtime state.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from statistics import mean, median
from typing import Any, Iterable, Sequence

import numpy as np

from app.candle import Candle
from app.risk_allocation import RiskAllocationConfig, risk_fraction
from app.scored_component_analysis import COMPONENTS, ComponentObservation, replay_closed_candles
from app.signal_scoring import SignalScoreConfig


DECISION_CATEGORIES = (
    "NO_BASE_SIGNAL", "SCORE_BELOW_THRESHOLD", "HARD_FILTER_BLOCK", "RISK_BLOCK",
    "DATA_QUALITY_BLOCK", "COOLDOWN_BLOCK", "POSITION_ALREADY_OPEN", "ENTRY_ALLOWED",
    "EXIT_CONTEXT", "UNKNOWN_OR_LEGACY",
)
DISTANCE_65 = (("score_gte_65", 65, math.inf), ("short_0_1", 64, 65), ("short_1_3", 62, 64),
               ("short_3_5", 60, 62), ("short_5_10", 55, 60), ("short_10_20", 45, 55),
               ("short_20_30", 35, 45), ("short_over_30", -math.inf, 35))
DISTANCE_80 = (("score_gte_80", 80, math.inf), ("short_0_5", 75, 80), ("short_5_10", 70, 75),
               ("short_10_20", 60, 70), ("short_over_20", -math.inf, 60))


@dataclass(frozen=True)
class FilterState:
    name: str
    passed: bool
    blocking: bool
    kind: str
    detail: str


@dataclass(frozen=True)
class EntryObservation:
    timestamp: int
    close_timestamp: int
    market_price: float
    score: float
    threshold: float
    components: dict[str, float]
    regime: str
    base_signal: bool
    filters: tuple[FilterState, ...]
    position_open: bool = False
    cooldown: bool = False
    source: str = "offline_replay"

    @property
    def distance_to_entry(self) -> float:
        return self.score - self.threshold


@dataclass(frozen=True)
class BlockerClassification:
    category: str
    primary_reason: str
    additional_reasons: tuple[str, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class ScoreDistanceDistribution:
    threshold: float
    denominator: int
    bands: dict[str, dict[str, float | int]]
    mean_distance: float | None
    median_distance: float | None


@dataclass(frozen=True)
class BlockerCombination:
    combination: str
    count: int
    percentage: float
    average_score: float | None
    median_distance_to_65: float | None
    average_streak: float | None
    regimes: dict[str, int]


@dataclass(frozen=True)
class NearMissAnalysis:
    count: int
    percentage: float
    component_last_points: dict[str, int]
    by_regime: dict[str, int]
    outcomes: dict[str, Any]


@dataclass(frozen=True)
class EntryOpportunityAnalysis:
    observations: int
    decision_categories: dict[str, int]
    base_signal_funnel: dict[str, Any]
    blocker_frequency: dict[str, Any]
    blocker_combinations: list[dict[str, Any]]
    score_distance: dict[str, Any]
    near_misses: dict[str, Any]
    real_entry_comparison: dict[str, Any]
    hard_filter_audit: dict[str, Any]
    regime_breakdown: dict[str, Any]
    time_breakdown: dict[str, Any]
    forward_outcomes: dict[str, Any]
    cost_analysis: dict[str, Any]
    counterfactuals: dict[str, Any]
    technical_findings: list[dict[str, str]]
    verdict: dict[str, Any]
    confidence: dict[str, Any]
    limitations: list[str]
    production_changes: bool = False


@dataclass(frozen=True)
class EntryBlockerReport:
    period: str
    source: dict[str, Any]
    observations: int
    data_quality: dict[str, Any]
    analysis: dict[str, Any]
    decision_categories: dict[str, int]
    base_signal_funnel: dict[str, Any]
    blocker_frequency: dict[str, Any]
    blocker_combinations: list[dict[str, Any]]
    score_distance: dict[str, Any]
    near_misses: dict[str, Any]
    real_entry_comparison: dict[str, Any]
    hard_filter_audit: dict[str, Any]
    regime_breakdown: dict[str, Any]
    time_breakdown: dict[str, Any]
    forward_outcomes: dict[str, Any]
    cost_analysis: dict[str, Any]
    counterfactuals: dict[str, Any]
    technical_findings: list[dict[str, str]]
    verdict: dict[str, Any]
    confidence: dict[str, Any]
    limitations: list[str]
    production_changes: bool = False


def technical_record_findings(record: dict[str, Any], *, timeframe_minutes: int = 60) -> list[dict[str, str]]:
    """Validate a journal-shaped record without accepting or mutating it."""
    findings: list[dict[str, str]] = []
    components = record.get("components")
    if not isinstance(components, dict):
        findings.append({"severity": "WARNING", "code": "MISSING_COMPONENT_FIELD", "detail": "components is absent or not an object"})
    else:
        missing = [f"{name}_score" for name in COMPONENTS if f"{name}_score" not in components and name not in components]
        if missing:
            findings.append({"severity": "WARNING", "code": "MISSING_COMPONENT_FIELD", "detail": ", ".join(missing)})
        if any(isinstance(value, float) and not math.isfinite(value) for value in components.values()):
            findings.append({"severity": "WARNING", "code": "NAN_COMPONENT", "detail": "A component is non-finite"})
    timestamp = record.get("candle_timestamp")
    close_timestamp = record.get("candle_close_timestamp")
    if timestamp is not None and close_timestamp is not None and int(close_timestamp) - int(timestamp) != timeframe_minutes * 60:
        findings.append({"severity": "WARNING", "code": "TIMEFRAME_TIMESTAMP_MISMATCH", "detail": "candle close interval differs from configured timeframe"})
    if not record.get("score_version") and "strategy_name" in record:
        findings.append({"severity": "INFO", "code": "LEGACY_SCHEMA", "detail": "score_version is absent in a strategy journal record"})
    return findings


def classify_observation(observation: EntryObservation) -> BlockerClassification:
    """Apply a deterministic, non-trading classification precedence."""
    filters = {f.name: f for f in observation.filters}
    if any(f.blocking and f.kind == "data_quality" for f in observation.filters):
        reasons = tuple(f.name for f in observation.filters if f.blocking)
        return BlockerClassification("DATA_QUALITY_BLOCK", reasons[0] if reasons else "data_quality", reasons[1:], reasons)
    if observation.position_open:
        return BlockerClassification("POSITION_ALREADY_OPEN", "position_already_open", (), ("position_already_open",))
    if observation.cooldown:
        return BlockerClassification("COOLDOWN_BLOCK", "cooldown", (), ("cooldown",))
    hard = tuple(f.name for f in observation.filters if f.blocking and f.kind == "hard")
    if hard:
        return BlockerClassification("HARD_FILTER_BLOCK", hard[0], hard[1:], hard)
    risk = tuple(f.name for f in observation.filters if f.blocking and f.kind == "risk")
    if risk:
        return BlockerClassification("RISK_BLOCK", risk[0], risk[1:], risk)
    if not observation.base_signal:
        return BlockerClassification("NO_BASE_SIGNAL", "no_base_signal", (), ("no_base_signal",))
    if observation.score < observation.threshold:
        deficits = sorted(COMPONENTS, key=lambda n: (observation.components[n] / _maxima()[n], n))
        blockers = tuple(deficits[:3])
        return BlockerClassification("SCORE_BELOW_THRESHOLD", blockers[0], blockers[1:], blockers)
    return BlockerClassification("ENTRY_ALLOWED", "entry_allowed", (), ())


def _maxima(config: SignalScoreConfig = SignalScoreConfig()) -> dict[str, float]:
    return config.maxima


def _iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def replay_entry_observations(candles: Sequence[Candle], *, threshold: float = 65.0,
                              config: SignalScoreConfig = SignalScoreConfig()) -> tuple[list[EntryObservation], dict[str, Any]]:
    """Replay only closed candles; warmup rows are retained as data-quality rows."""
    ordered = sorted(candles, key=lambda c: c.timestamp)
    unique = {c.timestamp: c for c in ordered}
    duplicate_count = len(ordered) - len(unique)
    rows, quality = replay_closed_candles(tuple(unique.values()), config)
    by_time = {row.timestamp: row for row in rows}
    required = config.slow_ema_period + config.adx_period + 2
    result: list[EntryObservation] = []
    for index, candle in enumerate(sorted(unique.values(), key=lambda c: c.timestamp)):
        scored = by_time.get(candle.timestamp)
        if scored is None:
            filters = (FilterState("insufficient_warmup", False, True, "data_quality", f"need {required} closed candles"),)
            result.append(EntryObservation(candle.timestamp, candle.timestamp + 3600, float(candle.close), 0.0, threshold,
                                           {name: 0.0 for name in COMPONENTS}, "UNKNOWN", False, filters))
            continue
        filters = ()
        result.append(EntryObservation(scored.timestamp, scored.close_timestamp, scored.market_price, scored.score,
                                       threshold, scored.components, scored.regime, True, filters))
    quality = {**quality, "duplicate_candles": duplicate_count, "closed_candles_only": True,
               "warmup_rows_retained": len(result) - len(rows)}
    return result, quality


def _band(value: float, bands: Sequence[tuple[str, float, float]]) -> str:
    for name, low, high in bands:
        if low <= value < high:
            return name
    return bands[-1][0]


def _stats(values: Sequence[float]) -> dict[str, Any]:
    clean = [float(v) for v in values if math.isfinite(float(v))]
    if not clean:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None,
                "positive_rate": None, "adverse_excursion": None, "favorable_excursion": None}
    return {"count": len(clean), "mean": mean(clean), "median": median(clean), "min": min(clean), "max": max(clean),
            "positive_rate": sum(x > 0 for x in clean) * 100 / len(clean)}


def _outcome(candles: Sequence[Candle], index: int, horizon: int, *, fee_rate: float, slippage: float) -> dict[str, float] | None:
    if index + horizon >= len(candles):
        return None
    entry = float(candles[index].close)
    future = candles[index + 1:index + horizon + 1]
    gross = (float(candles[index + horizon].close) / entry - 1) * 100
    friction = (2 * fee_rate + 2 * slippage) * 100
    return {"gross_return_pct": gross, "net_return_pct": gross - friction,
            "adverse_excursion_pct": (min(float(c.low) for c in future) / entry - 1) * 100,
            "favorable_excursion_pct": (max(float(c.high) for c in future) / entry - 1) * 100}


def _outcomes_for(rows: Sequence[EntryObservation], candles: Sequence[Candle], indices: Sequence[int], horizons: Sequence[int], *, fee_rate: float, slippage: float) -> dict[str, Any]:
    lookup = {c.timestamp: i for i, c in enumerate(candles)}
    answer: dict[str, Any] = {}
    for h in horizons:
        items = [_outcome(candles, lookup[rows[i].timestamp], h, fee_rate=fee_rate, slippage=slippage)
                 for i in indices if rows[i].timestamp in lookup]
        items = [x for x in items if x is not None]
        answer[str(h)] = {metric: _stats([x[metric] for x in items]) for metric in
                          ("gross_return_pct", "net_return_pct", "adverse_excursion_pct", "favorable_excursion_pct")}
    return answer


def score_distance_distribution(rows: Sequence[EntryObservation], *, threshold: float = 65.0) -> ScoreDistanceDistribution:
    bands = DISTANCE_65 if threshold == 65 else DISTANCE_80
    counts = {name: 0 for name, _, _ in bands}
    distances = []
    for row in rows:
        counts[_band(row.score, bands)] += 1
        distances.append(row.score - threshold)
    n = len(rows)
    return ScoreDistanceDistribution(threshold, n,
        {name: {"count": count, "percentage": count * 100 / n if n else 0} for name, count in counts.items()},
        mean(distances) if distances else None, median(distances) if distances else None)


def _streak_lengths(keys: Sequence[str]) -> list[int]:
    result: list[int] = []; current = None; length = 0
    for key in keys:
        if key == current: length += 1
        else:
            if length: result.append(length)
            current, length = key, 1
    if length: result.append(length)
    return result


def _combination_rows(rows: Sequence[EntryObservation], classifications: Sequence[BlockerClassification], *, threshold: float) -> list[dict[str, Any]]:
    combos: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i, cls in enumerate(classifications):
        if cls.category == "SCORE_BELOW_THRESHOLD":
            combo = tuple(sorted(set(cls.blockers[:2])))
            if combo: combos[combo].append(i)
    output = []
    labels = [" + ".join(sorted(set(c.blockers[:2]))) if c.category == "SCORE_BELOW_THRESHOLD" else "" for c in classifications]
    for combo, indices in sorted(combos.items(), key=lambda x: (-len(x[1]), x[0]))[:20]:
        keyset = {rows[i].regime for i in indices}
        streaks = []
        current = 0
        for label in labels:
            if label == " + ".join(combo):
                current += 1
            elif current:
                streaks.append(current)
                current = 0
        if current:
            streaks.append(current)
        output.append(asdict(BlockerCombination(" + ".join(combo), len(indices), len(indices) * 100 / len(rows) if rows else 0,
            mean(rows[i].score for i in indices), median(rows[i].score - threshold for i in indices),
            mean(streaks) if streaks else None,
            {regime: sum(rows[i].regime == regime for i in indices) for regime in sorted(keyset)})))
    return output


def analyze_entry_blockers(rows: Sequence[EntryObservation], candles: Sequence[Candle], *, period: str,
                           threshold: float = 65.0, strong_threshold: float = 80.0,
                           horizons: Sequence[int] = (1, 3, 6, 12, 24), include_counterfactuals: bool = False,
                           quality: dict[str, Any] | None = None, config: SignalScoreConfig = SignalScoreConfig(),
                           fee_rate: float | None = None, slippage: float = 0.0005) -> EntryBlockerReport:
    rows = list(rows); n = len(rows); fee = config.fee_rate if fee_rate is None else fee_rate
    classifications = [classify_observation(row) for row in rows]
    category_counts = Counter(cls.category for cls in classifications)
    for category in DECISION_CATEGORIES: category_counts.setdefault(category, 0)
    all_idx = list(range(n)); score_idx = [i for i, cls in enumerate(classifications) if cls.category == "SCORE_BELOW_THRESHOLD"]
    base_idx = [i for i, row in enumerate(rows) if row.base_signal]
    passed_hard = [i for i, cls in enumerate(classifications) if cls.category not in ("DATA_QUALITY_BLOCK", "HARD_FILTER_BLOCK")]
    score_pass = [i for i, row in enumerate(rows) if row.base_signal and row.score >= threshold]
    allowed = [i for i, cls in enumerate(classifications) if cls.category == "ENTRY_ALLOWED" and risk_fraction(rows[i].score, RiskAllocationConfig()) > 0]
    funnel = {"all_closed_candles": n, "base_signal": len(base_idx), "passed_hard_filters": len(passed_hard),
              "score_gte_65": len(score_pass), "allocation_positive": len(allowed), "simulated_entry": len(allowed),
              "conversion_rates_pct": {"base_signal": len(base_idx)*100/n if n else 0, "passed_hard_filters": len(passed_hard)*100/len(base_idx) if base_idx else 0,
                                        "score_gte_65": len(score_pass)*100/len(base_idx) if base_idx else 0,
                                        "allocation_positive": len(allowed)*100/len(score_pass) if score_pass else 0}}
    component_counts = Counter(); primary_counts = Counter(); top2 = Counter(); top3 = Counter(); sole = Counter(); combinations = Counter()
    for i in score_idx:
        cls = classifications[i]; component_counts.update(cls.blockers); primary_counts.update(cls.blockers[:1]); top2.update(cls.blockers[:2]); top3.update(cls.blockers[:3]); sole.update(cls.blockers[:1]); combinations[" + ".join(sorted(set(cls.blockers[:2])))] += 1
    blocker_frequency = {}
    hold_denominator = len([c for c in classifications if c.category not in ("ENTRY_ALLOWED", "DATA_QUALITY_BLOCK")]) or 1
    for name in (*COMPONENTS, "base_signal", "hard_filters", "risk_filters", "cooldown", "data_quality", "regime"):
        count = component_counts[name] if name in COMPONENTS else (sum(not r.base_signal for r in rows) if name == "base_signal" else sum(any(f.blocking and f.kind == name.removesuffix("_filters") for f in r.filters) for r in rows) if name in ("hard_filters", "risk_filters") else sum(r.cooldown for r in rows) if name == "cooldown" else sum(any(f.blocking and f.kind == "data_quality" for f in r.filters) for r in rows) if name == "data_quality" else sum(r.score < threshold for r in rows))
        blocker_frequency[name] = {"count": count, "percent_all": count*100/n if n else 0, "percent_base_signal": count*100/len(base_idx) if base_idx else 0,
                                   "percent_hold": count*100/hold_denominator, "primary_count": primary_counts[name], "top_2_count": top2[name], "top_3_count": top3[name], "sole_count": sole[name]}
    distance = {"all": asdict(score_distance_distribution(rows, threshold=threshold)), "base_signal": asdict(score_distance_distribution([rows[i] for i in base_idx], threshold=threshold)),
                "strong_threshold": asdict(score_distance_distribution(rows, threshold=strong_threshold)),
                "longest_without_65": max(_streak_lengths(["hit" if r.score >= threshold else "miss" for r in rows]), default=0),
                "longest_without_80": max(_streak_lengths(["hit" if r.score >= strong_threshold else "miss" for r in rows]), default=0)}
    near_idx = [i for i, r in enumerate(rows) if 60 <= r.score < 65 and r.base_signal and not any(f.blocking and f.kind in ("risk", "hard", "data_quality") for f in r.filters)]
    near_components = Counter()
    for i in near_idx: near_components.update(sorted(COMPONENTS, key=lambda c: rows[i].components[c] / _maxima()[c])[:3])
    by_regime = Counter(rows[i].regime for i in near_idx)
    near = NearMissAnalysis(len(near_idx), len(near_idx)*100/n if n else 0, dict(near_components), dict(by_regime), _outcomes_for(rows, candles, near_idx, horizons, fee_rate=fee, slippage=slippage))
    groups = {"real_entries_score_65_plus": [i for i, r in enumerate(rows) if r.score >= threshold], "near_miss_60_65": near_idx,
              "hold_40_60": [i for i, r in enumerate(rows) if 40 <= r.score < 60], "hold_below_40": [i for i, r in enumerate(rows) if r.score < 40]}
    comparison = {name: {"count": len(indices), "regimes": dict(Counter(rows[i].regime for i in indices)), "outcomes": _outcomes_for(rows, candles, indices, horizons, fee_rate=fee, slippage=slippage)} for name, indices in groups.items()}
    hard_audit = {}
    for name in sorted({f.name for r in rows for f in r.filters}):
        indices = [i for i, r in enumerate(rows) if any(f.name == name and f.blocking for f in r.filters)]
        hard_audit[name] = {"count": len(indices), "score_gte_65": sum(rows[i].score >= 65 for i in indices), "score_gte_80": sum(rows[i].score >= 80 for i in indices), "outcomes": _outcomes_for(rows, candles, indices, horizons, fee_rate=fee, slippage=slippage)}
    regime_breakdown = {}
    for regime in sorted({r.regime for r in rows}):
        indices = [i for i, r in enumerate(rows) if r.regime == regime]
        regime_breakdown[regime] = {"observations": len(indices), "coverage_pct": len(indices)*100/n if n else 0,
            "base_signal_rate_pct": sum(rows[i].base_signal for i in indices)*100/len(indices) if indices else 0,
            "entry_rate_pct": sum(rows[i].score >= threshold for i in indices)*100/len(indices) if indices else 0,
            "near_miss_rate_pct": sum(i in near_idx for i in indices)*100/len(indices) if indices else 0,
            "categories": dict(Counter(classifications[i].category for i in indices)),
            "forward_outcomes": _outcomes_for(rows, candles, indices, horizons, fee_rate=fee, slippage=slippage)}
    time_breakdown = {}
    for label, fmt in (("weeks", "%G-W%V"), ("months", "%Y-%m"), ("rolling_7d", None), ("rolling_30d", None)):
        if fmt:
            buckets = defaultdict(list)
            for i, r in enumerate(rows): buckets[datetime.fromtimestamp(r.timestamp, timezone.utc).strftime(fmt)].append(i)
            time_breakdown[label] = {k: {"observations": len(v), "entry_rate_pct": sum(rows[i].score >= threshold for i in v)*100/len(v), "near_miss_rate_pct": sum(i in near_idx for i in v)*100/len(v), "blocker_mix": dict(Counter(classifications[i].primary_reason for i in v))} for k, v in buckets.items()}
        else:
            window = 7 if label == "rolling_7d" else 30; time_breakdown[label] = {"window_days": window, "points": []}
            for i, r in enumerate(rows):
                if i % max(1, len(rows)//200) != 0:
                    continue
                indices = [j for j, other in enumerate(rows) if r.timestamp - window*86400 < other.timestamp <= r.timestamp]
                time_breakdown[label]["points"].append({"timestamp": _iso(r.timestamp), "observations": len(indices), "entry_rate_pct": sum(rows[j].score >= threshold for j in indices)*100/len(indices) if indices else 0})
    forward = {"horizons": list(horizons), "all": _outcomes_for(rows, candles, all_idx, horizons, fee_rate=fee, slippage=slippage)}
    cost = {"entry_fee_rate": fee, "exit_fee_rate": fee, "slippage_each_side": slippage, "round_trip_friction_pct": (2*fee+2*slippage)*100,
            "minimum_required_move_pct": (2*fee+2*slippage)*100, "near_miss_net_positive_rate_24h": near.outcomes.get("24", {}).get("net_return_pct", {}).get("positive_rate")}
    counterfactuals: dict[str, Any] = {"status": "NOT_REQUESTED"}
    if include_counterfactuals:
        labels = ["DIAGNOSTIC_ONLY", "NO_PRODUCTION_CHANGE", "NOT_A_TRADING_RECOMMENDATION"]
        counterfactuals = {"labels": labels, "thresholds": {str(t): sum(r.base_signal and r.score >= t for r in rows) for t in (50, 55, 60, 65)},
                           "without_component": {c: sum(r.score - r.components[c] >= threshold for r in rows) for c in COMPONENTS},
                           "pullback_effective_max_16": sum(r.score - r.components["pullback"] + min(16, 20) >= threshold for r in rows),
                           "normalized_effective_ceiling_95_5": sum((r.score / 95.5 * 100) >= threshold for r in rows)}
    findings = [{"severity": "INFO", "code": "NO_SEPARATE_BASE_SIGNAL_FIELD", "detail": "Current scored formula exposes no independent base-signal boolean; valid causal score observations are used as base_signal."},
                {"severity": "INFO", "code": "NO_RUNTIME_HARD_FILTERS_IN_OFFLINE_FORMULA", "detail": "SignalScore hard_blocks are empty after warmup for valid market data; threshold and allocation are analyzed separately."},
                {"severity": "INFO", "code": "LEGACY_SCHEMA_CHECK_AVAILABLE", "detail": "Journal records can be checked for missing components, non-finite values, timestamp mismatch, and legacy fields via technical_record_findings."}]
    if quality and quality.get("duplicate_candles"): findings.append({"severity": "WARNING", "code": "DUPLICATE_CANDLES", "detail": "Duplicate timestamps were deduplicated for analysis."})
    entry_count = len(groups["real_entries_score_65_plus"])
    if n < 500: verdict = "INSUFFICIENT_DATA"
    elif len(base_idx) / n < .01: verdict = "BASE_SIGNAL_TOO_RARE"
    elif entry_count / n < .001: verdict = "OVER_RESTRICTIVE"
    elif category_counts["SCORE_BELOW_THRESHOLD"] / n > .8 and len(near_idx) / max(1, category_counts["SCORE_BELOW_THRESHOLD"]) > .05: verdict = "FILTER_COMBINATION_TOO_STRICT"
    else: verdict = "MARKET_REGIME_EFFECT"
    confidence_level = "high" if n >= 5000 else "medium" if n >= 1000 else "low"
    analysis = EntryOpportunityAnalysis(n, dict(category_counts), funnel, blocker_frequency, _combination_rows(rows, classifications, threshold=threshold), distance, asdict(near), comparison, hard_audit, regime_breakdown, time_breakdown, forward, cost, counterfactuals, findings, {"status": verdict, "evidence": {"entry_count": entry_count, "near_miss_count": len(near_idx), "base_signal_rate_pct": len(base_idx)*100/n if n else 0}, "production_changes": False}, {"level": confidence_level, "observations": n, "near_miss_sample": len(near_idx)}, ["Offline outcomes are observational, not causal.", "No independent base-signal field exists in the current scored formula.", "Runtime journal and offline replay have different coverage windows."])
    return EntryBlockerReport(period, {"type": "historical_market_dataset", "formula_version": config.version}, n, quality or {}, asdict(analysis), dict(category_counts), funnel, blocker_frequency, analysis.blocker_combinations, distance, asdict(near), comparison, hard_audit, regime_breakdown, time_breakdown, forward, cost, counterfactuals, findings, analysis.verdict, analysis.confidence, analysis.limitations, False)
