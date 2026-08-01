"""Deterministic, read-only market-regime and factor research.

This module describes historical candles.  It does not participate in signal
generation, strategy routing, execution, risk, or runtime state.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from math import isfinite
from statistics import mean, pstdev
from typing import Sequence

import pandas as pd

from app.candle import Candle
from app.factor_research import _market_outcomes, _spearman, _summary
from app.indicators import adx, atr
from app.scored_component_calibration import COMPONENTS
from app.signal_scoring import SignalScoreConfig


@dataclass(frozen=True, slots=True)
class RegimeResearchConfig:
    adx_period: int = 14
    fast_ema_period: int = 20
    slow_ema_period: int = 50
    range_adx_below: float = 15.0
    moderate_adx_from: float = 20.0
    strong_adx_from: float = 30.0
    low_volatility_atr_ratio: float = 0.005
    high_volatility_atr_ratio: float = 0.02
    outcome_horizon_hours: int = 24
    score_threshold: float = 65.0
    strong_move_percent: float = 2.0

    def __post_init__(self) -> None:
        if not (0 <= self.range_adx_below < self.moderate_adx_from < self.strong_adx_from):
            raise ValueError("ADX regime bounds must be increasing")
        if not (0 <= self.low_volatility_atr_ratio < self.high_volatility_atr_ratio):
            raise ValueError("volatility regime bounds must be increasing")


def _trend_regime(value: float, config: RegimeResearchConfig) -> str:
    if value < config.range_adx_below:
        return "range"
    if value < config.moderate_adx_from:
        return "weak_trend"
    if value < config.strong_adx_from:
        return "moderate_trend"
    return "strong_trend"


def _volatility_regime(value: float, config: RegimeResearchConfig) -> str:
    if value <= config.low_volatility_atr_ratio:
        return "low_volatility"
    if value >= config.high_volatility_atr_ratio:
        return "high_volatility"
    return "normal_volatility"


def _frame(candles: Sequence[Candle], config: RegimeResearchConfig) -> pd.DataFrame:
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    frame = pd.DataFrame({
        "timestamp": [item.timestamp for item in ordered],
        "open": [item.open for item in ordered],
        "high": [item.high for item in ordered],
        "low": [item.low for item in ordered],
        "close": [item.close for item in ordered],
    })
    close = frame["close"]
    frame["ema_fast"] = close.ewm(span=config.fast_ema_period, adjust=False).mean()
    frame["ema_slow"] = close.ewm(span=config.slow_ema_period, adjust=False).mean()
    frame["adx"] = adx(frame, config.adx_period)
    frame["atr"] = atr(frame, config.adx_period)
    frame["atr_ratio"] = frame["atr"] / close
    frame["ema_spread_percent"] = (frame["ema_fast"] - frame["ema_slow"]) / close * 100
    frame["return_percent"] = close.pct_change() * 100
    frame["realized_volatility_percent"] = frame["return_percent"].rolling(24, min_periods=2).std(ddof=0)
    frame["trend_regime"] = frame["adx"].map(lambda value: _trend_regime(float(value), config) if pd.notna(value) else None)
    frame["volatility_regime"] = frame["atr_ratio"].map(lambda value: _volatility_regime(float(value), config) if pd.notna(value) else None)
    frame["regime"] = frame.apply(
        lambda row: f"{row.trend_regime}/{row.volatility_regime}" if row.trend_regime and row.volatility_regime else None,
        axis=1,
    )
    return frame


def _score_rows(candles: Sequence[Candle], frame: pd.DataFrame, config: RegimeResearchConfig) -> list[dict]:
    """Vectorized reproduction of score_v1 for research-scale history."""
    score_config = SignalScoreConfig()
    maxima = score_config.maxima
    required = score_config.slow_ema_period + score_config.adx_period + 2
    rows: list[dict] = []
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    for index, item in enumerate(frame.itertuples(index=False)):
        if index < required - 1:
            continue
        values = (item.ema_fast, item.ema_slow, item.adx, item.atr_ratio)
        if not all(isfinite(float(value)) and float(value) > 0 for value in values):
            continue
        candle = ordered[index]
        direction = 1.0 if item.ema_fast > item.ema_slow else 0.0
        distance = abs(float(item.ema_fast - item.ema_slow)) / candle.close
        smooth_trend = max(0.0, min(1.0, (distance - .001) / (.03 - .001)))
        smooth_alignment = max(0.0, min(1.0, (distance - .001) / (.02 - .001)))
        adx_quality = max(0.0, min(1.0, (float(item.adx) - score_config.adx_low) / (score_config.adx_full - score_config.adx_low)))
        scale = max(float(item.ema_fast), 1e-12)
        touch = max(0.0, min(1.0, (float(item.ema_fast) - candle.low) / (scale * score_config.pullback_tolerance)))
        near = max(0.0, min(1.0, 1.0 - abs(candle.close - float(item.ema_fast)) / (scale * score_config.pullback_tolerance)))
        retrace = max(0.0, min(1.0, (float(item.ema_fast) - candle.close) / (scale * score_config.pullback_retrace)))
        momentum = max(0.0, min(1.0, (candle.close - candle.open) / max(candle.close * .01, 1e-12) + .5))
        vol_position = max(0.0, min(1.0, (float(item.atr_ratio) - score_config.volatility_low) / (score_config.volatility_full - score_config.volatility_low)))
        raw = {
            "trend": direction * smooth_trend,
            "ema_alignment": direction * (.5 + .5 * smooth_alignment),
            "adx": adx_quality,
            "pullback": max(0.0, min(1.0, .4 * touch + .4 * near + .2 * retrace)),
            "momentum": momentum,
            "volatility": 1.0 - abs(vol_position - .5) * 2,
            "cost": max(0.0, min(1.0, 1.0 - 2 * score_config.fee_rate / score_config.stop_distance_pct)),
        }
        components = {name: raw[name] * maxima[name] for name in COMPONENTS}
        rows.append({
            "candle_timestamp": candle.timestamp,
            "candle_close_timestamp": candle.timestamp + 3600,
            "total_score": sum(components.values()),
            "components": components,
            "utilization": {name: raw[name] * 100 for name in COMPONENTS},
            "outcomes": _market_outcomes(ordered, index),
            "regime": item.regime,
            "year": pd.Timestamp(candle.timestamp, unit="s", tz="UTC").year,
        })
    return rows


def _outcomes(rows: Sequence[dict], metric: str = "return_24h") -> dict:
    values = [float(row["outcomes"][metric]) for row in rows if row["outcomes"].get(metric) is not None]
    return {
        **_summary(values),
        "positive_rate_percent": sum(value > 0 for value in values) / len(values) * 100 if values else None,
    }


def _ranking(rows: Sequence[dict]) -> list[dict]:
    metrics = ("return_1h", "return_3h", "return_6h", "return_12h", "return_24h", "mfe_24h", "mae_24h")
    matrix = pd.DataFrame([
        {**{factor: row["utilization"][factor] for factor in COMPONENTS}, **{metric: row["outcomes"].get(metric) for metric in metrics}}
        for row in rows
    ], columns=(*COMPONENTS, *metrics))
    correlations = matrix.corr(method="spearman") if len(matrix) >= 2 else pd.DataFrame()
    result = []
    for factor in COMPONENTS:
        correlation_by_metric = {metric: (float(correlations.loc[factor, metric]) if factor in correlations.index and pd.notna(correlations.loc[factor, metric]) else None) for metric in metrics}
        factor_correlations = [value for value in correlation_by_metric.values() if value is not None]
        medians = []
        for low in (0, 20, 40, 60, 80):
            values = [float(row["outcomes"]["return_24h"]) for row in rows if low <= row["utilization"][factor] < low + 20.000001 and row["outcomes"].get("return_24h") is not None]
            if values:
                medians.append(float(pd.Series(values).median()))
        monotonicity = _spearman(list(range(len(medians))), medians) or 0.0
        predictive = mean(factor_correlations) if factor_correlations else 0.0
        quality = max(0.0, min(100.0, 100 * (.7 * predictive + .3 * monotonicity)))
        top = [row for row in rows if row["utilization"][factor] >= 50]
        result.append({
            "factor": factor,
            "predictive_quality": quality,
            "spearman_future_return_24h": correlation_by_metric["return_24h"],
            "positive_rate_percent": _outcomes(top)["positive_rate_percent"],
            "future_return_24h_mean": _outcomes(top)["mean"],
            "mfe_24h_mean": _outcomes(top, "mfe_24h")["mean"],
            "mae_24h_mean": _outcomes(top, "mae_24h")["mean"],
            "top_half_sample_size": len(top),
        })
    return sorted(result, key=lambda item: item["predictive_quality"], reverse=True)


def _regime_report(rows: Sequence[dict], market: pd.DataFrame) -> dict:
    total = int(market["regime"].notna().sum())
    reports = {}
    for regime in sorted(str(item) for item in market["regime"].dropna().unique()):
        subset = market[market["regime"] == regime]
        selected = [row for row in rows if row["regime"] == regime]
        ranking = _ranking(selected)
        reports[regime] = {
            "candle_count": len(subset),
            "history_share_percent": len(subset) / total * 100 if total else None,
            "average_return_percent": _summary(subset["return_percent"].dropna().tolist())["mean"],
            "average_realized_volatility_percent": _summary(subset["realized_volatility_percent"].dropna().tolist())["mean"],
            "average_atr": _summary(subset["atr"].dropna().tolist())["mean"],
            "average_adx": _summary(subset["adx"].dropna().tolist())["mean"],
            "average_ema_spread_percent": _summary(subset["ema_spread_percent"].dropna().tolist())["mean"],
            "outcome_24h": _outcomes(selected),
            "factor_ranking": ranking,
        }
    return reports


def _stars(quality: float) -> str:
    return "★" * (5 if quality >= 30 else 4 if quality >= 20 else 3 if quality >= 10 else 2 if quality >= 5 else 1 if quality > 0 else 0) or "—"


def _diagnostic_by_regime(rows: Sequence[dict]) -> dict:
    counts = Counter(str(row["regime"]) for row in rows)
    return {
        "count": len(rows),
        "by_regime": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        "outcome_24h": _outcomes(rows),
        "examples": [{"timestamp": row["candle_close_timestamp"], "regime": row["regime"], "score": row["total_score"], "return_24h": row["outcomes"].get("return_24h")} for row in rows[:20]],
    }


def research(candles: Sequence[Candle], *, config: RegimeResearchConfig = RegimeResearchConfig(), from_timestamp: int | None = None, to_timestamp: int | None = None) -> dict:
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    market = _frame(ordered, config)
    rows = _score_rows(ordered, market, config)
    if from_timestamp is not None:
        market = market[market["timestamp"] + 3600 >= from_timestamp]
        rows = [row for row in rows if row["candle_close_timestamp"] >= from_timestamp]
    if to_timestamp is not None:
        market = market[market["timestamp"] + 3600 <= to_timestamp]
        rows = [row for row in rows if row["candle_close_timestamp"] <= to_timestamp]
    regimes = _regime_report(rows, market)

    annual = {}
    for year in sorted({row["year"] for row in rows}):
        annual[str(year)] = {}
        for regime in regimes:
            selected = [row for row in rows if row["year"] == year and row["regime"] == regime]
            if selected:
                annual[str(year)][regime] = {"sample_size": len(selected), "factor_ranking": _ranking(selected)}

    dated = [(pd.Timestamp(row["candle_close_timestamp"], unit="s", tz="UTC"), row) for row in rows]
    rolling = {}
    if dated:
        first, last = dated[0][0], dated[-1][0]
        # Quarterly observation points keep the three rolling series useful in
        # a normal CLI run without changing their 90/180/365-day lookbacks.
        ends = list(pd.date_range(first.ceil("D"), last, freq="90D"))
        if not ends or ends[-1] != last:
            ends.append(last)
        for days in (90, 180, 365):
            windows = []
            for end in ends:
                start = end - pd.Timedelta(days=days)
                selected = [row for timestamp, row in dated if start < timestamp <= end]
                if len(selected) >= 50:
                    windows.append({"to": end.isoformat(), "from": start.isoformat(), "sample_size": len(selected), "factor_ranking": _ranking(selected)})
            rolling[f"{days}d"] = windows

    transitions = Counter()
    transition_rows: dict[str, list[dict]] = {}
    previous = None
    row_by_timestamp = {row["candle_timestamp"]: row for row in rows}
    for item in market.itertuples():
        if item.regime and previous and item.regime != previous:
            key = f"{previous} -> {item.regime}"
            transitions[key] += 1
            if int(item.timestamp) in row_by_timestamp:
                transition_rows.setdefault(key, []).append(row_by_timestamp[int(item.timestamp)])
        if item.regime:
            previous = item.regime
    transition_report = [{"transition": key, "count": count, "outcome_24h": _outcomes(transition_rows.get(key, []))} for key, count in transitions.most_common()]

    eligible = [row for row in rows if row["outcomes"].get("return_24h") is not None]
    near = [row for row in eligible if 60 <= row["total_score"] < 65]
    false_negatives = [row for row in eligible if row["total_score"] < config.score_threshold and row["outcomes"]["return_24h"] >= config.strong_move_percent]
    false_positives = [row for row in eligible if row["total_score"] >= config.score_threshold and row["outcomes"]["return_24h"] <= 0]

    heatmap = {regime: {item["factor"]: {"stars": _stars(item["predictive_quality"]), "predictive_quality": item["predictive_quality"]} for item in report["factor_ranking"]} for regime, report in regimes.items()}
    observations: dict[str, list[float]] = {factor: [] for factor in COMPONENTS}
    for yearly in annual.values():
        for report in yearly.values():
            for item in report["factor_ranking"]:
                observations[item["factor"]].append(item["predictive_quality"])
    stability = sorted(({
        "factor": factor,
        "observations": len(values),
        "mean_predictive_quality": mean(values) if values else None,
        "standard_deviation": pstdev(values) if values else None,
        "positive_fraction": sum(value > 0 for value in values) / len(values) if values else None,
    } for factor, values in observations.items()), key=lambda item: (item["standard_deviation"] if item["standard_deviation"] is not None else float("inf"), -(item["mean_predictive_quality"] or 0)))

    return {
        "framework": "market_regime_factor_research_v1",
        "mode": "analysis_only",
        "period": {"from": int(market["timestamp"].min() + 3600) if len(market) else None, "to": int(market["timestamp"].max() + 3600) if len(market) else None, "candles": len(market), "factor_setups": len(rows)},
        "classification": {"type": "deterministic_composite", "causal": True, "config": asdict(config), "rules": {"trend_strength": "ADX <15 range; 15..<20 weak; 20..<30 moderate; >=30 strong", "volatility": "ATR(14)/close <=0.5% low; >=2% high; otherwise normal", "assignment": "trend_strength/volatility; exactly one composite regime after indicator warm-up"}},
        "regimes": regimes,
        "annual_stability": annual,
        "rolling_analysis": rolling,
        "factor_stability": stability,
        "heatmap": heatmap,
        "regime_transitions": transition_report,
        "near_threshold_60_65": _diagnostic_by_regime(near),
        "false_negatives": _diagnostic_by_regime(false_negatives),
        "false_positives": _diagnostic_by_regime(false_positives),
        "safety": {"read_only": True, "strategy_changed": False, "score_changed": False, "weights_changed": False, "threshold_changed": False, "risk_changed": False, "paper_changed": False, "real_trading_changed": False},
    }
