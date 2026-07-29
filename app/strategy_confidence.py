from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
from statistics import pstdev
from typing import Any

from app.strategy_lab import LaboratoryConfig, NA, build_report
from app.runtime_health import candle_timing_diagnostics, read_jsonl_safely


RECOMMENDATIONS = {
    "INSUFFICIENT_DATA",
    "CONTINUE_OBSERVATION",
    "REJECT_FOR_NOW",
    "READY_FOR_REVIEW",
    "STRONG_CANDIDATE",
}


@dataclass(frozen=True, slots=True)
class ConfidenceLevel:
    name: str
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class PromotionConfig:
    confidence_weights: dict[str, float]
    confidence_levels: tuple[ConfidenceLevel, ...]
    minimum_days: int
    minimum_closed_trades: int
    minimum_comparable_candles: int
    minimum_decisions: int
    maximum_error_rate: float
    minimum_profit_factor: float
    maximum_drawdown_percent: float
    ready_confidence: int
    strong_confidence: int
    strong_return_advantage_percent: float
    rolling_periods: tuple[str, ...]
    block_on_active_halt: bool = True
    block_on_inactive_timer: bool = True
    block_on_stale_data: bool = True
    block_on_incompatible_config: bool = True

    def __post_init__(self) -> None:
        expected = {
            "sample", "data_quality", "performance", "risk",
            "stability", "operational",
        }
        if set(self.confidence_weights) != expected:
            raise ValueError("confidence weights have invalid components")
        if not math.isclose(sum(self.confidence_weights.values()), 1.0):
            raise ValueError("confidence weights must sum to 1.0")
        if any(value < 0 for value in self.confidence_weights.values()):
            raise ValueError("confidence weights must not be negative")
        levels = sorted(self.confidence_levels, key=lambda item: item.minimum)
        if not levels or levels[0].minimum != 0 or levels[-1].maximum != 100:
            raise ValueError("confidence levels must cover 0..100")
        for left, right in zip(levels, levels[1:]):
            if left.maximum + 1 != right.minimum:
                raise ValueError("confidence levels overlap or have gaps")
        if any(item.minimum > item.maximum for item in levels):
            raise ValueError("invalid confidence level range")
        positive = (
            self.minimum_days, self.minimum_closed_trades,
            self.minimum_comparable_candles, self.minimum_decisions,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("promotion minimum thresholds must be positive")
        if not 0 <= self.maximum_error_rate <= 1:
            raise ValueError("maximum_error_rate must be in 0..1")
        if not 0 <= self.ready_confidence <= self.strong_confidence <= 100:
            raise ValueError("confidence recommendation thresholds conflict")
        allowed = {"24h", "7d", "14d", "30d", "all"}
        if (
            not self.rolling_periods
            or len(set(self.rolling_periods)) != len(self.rolling_periods)
            or any(item not in allowed for item in self.rolling_periods)
        ):
            raise ValueError("rolling periods are invalid")


def load_promotion_config(path: Path) -> PromotionConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("promotion_review")
    if raw is None:
        return default_promotion_config()
    return PromotionConfig(
        confidence_weights={
            str(key): float(value)
            for key, value in raw["confidence_weights"].items()
        },
        confidence_levels=tuple(
            ConfidenceLevel(**item) for item in raw["confidence_levels"]
        ),
        minimum_days=int(raw["minimum_days"]),
        minimum_closed_trades=int(raw["minimum_closed_trades"]),
        minimum_comparable_candles=int(raw["minimum_comparable_candles"]),
        minimum_decisions=int(raw["minimum_decisions"]),
        maximum_error_rate=float(raw["maximum_error_rate"]),
        minimum_profit_factor=float(raw["minimum_profit_factor"]),
        maximum_drawdown_percent=float(raw["maximum_drawdown_percent"]),
        ready_confidence=int(raw["ready_confidence"]),
        strong_confidence=int(raw["strong_confidence"]),
        strong_return_advantage_percent=float(
            raw["strong_return_advantage_percent"]
        ),
        rolling_periods=tuple(raw["rolling_periods"]),
        block_on_active_halt=bool(raw.get("block_on_active_halt", True)),
        block_on_inactive_timer=bool(raw.get("block_on_inactive_timer", True)),
        block_on_stale_data=bool(raw.get("block_on_stale_data", True)),
        block_on_incompatible_config=bool(
            raw.get("block_on_incompatible_config", True)
        ),
    )


def default_promotion_config() -> PromotionConfig:
    return PromotionConfig(
        confidence_weights={
            "sample": .25, "data_quality": .20, "performance": .10,
            "risk": .15, "stability": .20, "operational": .10,
        },
        confidence_levels=(
            ConfidenceLevel("VERY_LOW", 0, 19),
            ConfidenceLevel("LOW", 20, 39),
            ConfidenceLevel("MODERATE", 40, 59),
            ConfidenceLevel("GOOD", 60, 79),
            ConfidenceLevel("HIGH", 80, 100),
        ),
        minimum_days=7,
        minimum_closed_trades=5,
        minimum_comparable_candles=20,
        minimum_decisions=50,
        maximum_error_rate=.05,
        minimum_profit_factor=1.0,
        maximum_drawdown_percent=10.0,
        ready_confidence=65,
        strong_confidence=80,
        strong_return_advantage_percent=2.0,
        rolling_periods=("24h", "7d", "14d", "30d", "all"),
    )


def _number(value: Any) -> Decimal | None:
    if value in {None, NA}:
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except Exception:
        return None


def _ratio(value: int, target: int) -> float:
    return min(1.0, max(0.0, value / target))


def confidence_level(score: int, levels: tuple[ConfidenceLevel, ...]) -> str:
    for level in levels:
        if level.minimum <= score <= level.maximum:
            return level.name
    raise ValueError("confidence score is outside configured levels")


def stability_from_windows(
    windows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    usable = [
        item for item in windows.values()
        if item.get("history_status") == "available"
        and _number(item.get("return_percent")) is not None
    ]
    if len(usable) < 2:
        return {
            "score": 0,
            "status": "UNAVAILABLE",
            "reason": "fewer than two independent rolling windows",
        }
    returns = [float(_number(item["return_percent"])) for item in usable]
    drawdowns = [
        float(_number(item["max_drawdown_percent"]) or Decimal("0"))
        for item in usable
    ]
    same_sign = all(value >= 0 for value in returns) or all(
        value <= 0 for value in returns
    )
    positive_share = sum(value > 0 for value in returns) / len(returns)
    dispersion = pstdev(returns) if len(returns) >= 2 else 0.0
    recent_worse = len(returns) >= 2 and returns[0] < returns[-1] - 1.0
    score = 35.0
    score += 20 if same_sign else 5
    score += positive_share * 25
    score += max(0, 15 - dispersion * 5)
    score -= min(25, max(drawdowns) * 2)
    score -= min(30, dispersion * 2)
    score -= 15 if recent_worse else 0
    score = round(max(0, min(100, score)))
    status = (
        "VERY_STABLE" if score >= 80 else
        "STABLE" if score >= 65 else
        "MIXED" if score >= 40 else
        "UNSTABLE"
    )
    return {
        "score": score,
        "status": status,
        "same_return_sign": same_sign,
        "return_dispersion": dispersion,
        "recent_deterioration": recent_worse,
        "usable_windows": len(usable),
    }


def rolling_metrics(
    laboratory: LaboratoryConfig,
    promotion: PromotionConfig,
    *,
    now: datetime,
    timezone_name: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {}
    for period in promotion.rolling_periods:
        report = build_report(
            laboratory, period=period, now=now, timezone_name=timezone_name
        )
        for strategy_id, metrics in report["strategies"].items():
            realized = _number(metrics.get("period_realized_pnl"))
            end = _number(metrics.get("equity"))
            decisions = int(metrics.get("number_of_decisions", 0))
            observation_start = metrics.get("observation_start")
            period_start = report["period"].get("start")
            covers_window = (
                period == "all"
                or (
                    observation_start is not None
                    and period_start is not None
                    and datetime.fromisoformat(observation_start)
                    <= datetime.fromisoformat(period_start)
                )
            )
            history_available = (
                decisions > 0 and realized is not None and covers_window
            )
            opened_at = metrics.get("opened_at")
            if (
                metrics.get("open_position_status") == "OPEN"
                and period != "all"
                and opened_at
                and period_start
                and datetime.fromisoformat(opened_at)
                < datetime.fromisoformat(period_start)
            ):
                history_available = False
            unrealized = _number(metrics.get("unrealized_pnl"))
            pnl = (
                realized + (unrealized or Decimal("0"))
                if history_available else None
            )
            start = end - pnl if end is not None and pnl is not None else None
            daily_returns = metrics.get("daily_returns", [])
            output.setdefault(strategy_id, {})[period] = {
                "start_equity": str(start) if start is not None else NA,
                "end_equity": str(end) if end is not None else NA,
                "pnl": str(pnl) if pnl is not None else NA,
                "return_percent": (
                    str(pnl / start * Decimal("100"))
                    if pnl is not None and start else NA
                ),
                "realized_pnl": str(realized) if realized is not None else NA,
                "unrealized_pnl": (
                    str(unrealized) if unrealized is not None else NA
                ),
                "max_drawdown_percent": metrics["max_drawdown_percent"],
                "closed_trades": metrics["closed_trades_count"],
                "win_rate": metrics["win_rate"],
                "profit_factor": metrics["profit_factor"],
                "fees": metrics["fees"],
                "errors": metrics["number_of_errors"],
                "missing_decisions": metrics.get("number_of_missing", 0),
                "exposure_percent": metrics["exposure_percent"],
                "daily_return_volatility": (
                    pstdev(daily_returns) if len(daily_returns) >= 2 else NA
                ),
                "history_status": (
                    "available" if history_available
                    else "insufficient history"
                ),
            }
    return output


def _observation_days(metrics: dict[str, Any], now: datetime) -> int:
    start = metrics.get("observation_start")
    if not start:
        return 0
    return max(0, (now - datetime.fromisoformat(start)).days)


def calculate_confidence(
    metrics: dict[str, Any],
    *,
    comparable_candles: int,
    windows: dict[str, dict[str, Any]],
    operational: dict[str, Any],
    config: PromotionConfig,
    now: datetime,
) -> dict[str, Any]:
    days = _observation_days(metrics, now)
    trades = int(metrics["closed_trades_count"])
    decisions = int(metrics["number_of_decisions"])
    errors = int(metrics["number_of_errors"])
    missing = int(metrics.get("number_of_missing", 0))
    total_records = decisions + errors + missing
    error_rate = errors / total_records if total_records else None
    completeness = decisions / total_records if total_records else None
    sample = 100 * (
        _ratio(days, config.minimum_days)
        + _ratio(trades, config.minimum_closed_trades)
        + _ratio(decisions, config.minimum_decisions)
        + _ratio(comparable_candles, config.minimum_comparable_candles)
    ) / 4
    quality_parts = []
    if error_rate is not None:
        quality_parts.append(max(0.0, 1 - error_rate / max(config.maximum_error_rate, .001)))
    if completeness is not None:
        quality_parts.append(completeness)
    data_quality = 100 * sum(quality_parts) / len(quality_parts) if quality_parts else 0
    pf = _number(metrics.get("profit_factor"))
    result = _number(metrics.get("return_percent"))
    performance_parts: list[float] = []
    if trades >= config.minimum_closed_trades and pf is not None:
        performance_parts.append(min(1.0, float(pf) / max(config.minimum_profit_factor, .01)))
    if result is not None:
        performance_parts.append(1.0 if result > 0 else .5 if result == 0 else 0.0)
    performance = (
        100 * sum(performance_parts) / len(performance_parts)
        if performance_parts else 0
    )
    drawdown = _number(metrics.get("max_drawdown_percent"))
    risk = (
        max(0.0, 100 * (1 - float(drawdown) / config.maximum_drawdown_percent))
        if drawdown is not None else 0
    )
    stability = stability_from_windows(windows)
    if days < config.minimum_days:
        stability = {
            "score": 0,
            "status": "UNAVAILABLE",
            "reason": (
                f"only {days}/{config.minimum_days} observation days"
            ),
        }
    critical = bool(
        operational.get("active_halt")
        or operational.get("timer_active") is False
        or operational.get("stale_data")
        or operational.get("critical_warnings")
    )
    operational_score = 0 if critical else 100
    components = {
        "sample_score": round(sample, 2),
        "data_quality_score": round(data_quality, 2),
        "performance_score": round(performance, 2),
        "risk_score": round(risk, 2),
        "stability_score": stability["score"],
        "operational_score": operational_score,
    }
    weighted = sum(
        components[f"{name}_score"] * weight
        for name, weight in config.confidence_weights.items()
    )
    # Sample adequacy is a hard confidence ceiling, preventing a lucky trade
    # from being promoted by return or PF.
    sample_ceiling = 39 if trades < config.minimum_closed_trades else 100
    score = round(min(weighted, sample, sample_ceiling))
    score = max(0, min(100, score))
    return {
        "confidence_score": score,
        "confidence_level": confidence_level(score, config.confidence_levels),
        "components": components,
        "error_rate": error_rate if error_rate is not None else NA,
        "data_completeness": completeness if completeness is not None else NA,
        "observation_days": days,
        "stability": stability,
    }


def compare_candidate(
    candidate: dict[str, Any],
    production: dict[str, Any],
    candidate_confidence: dict[str, Any],
    production_confidence: dict[str, Any],
) -> dict[str, Any]:
    pairs = {
        "delta_equity": "equity",
        "delta_return": "return_percent",
        "delta_pnl": "total_pnl",
        "delta_drawdown": "max_drawdown_percent",
        "delta_profit_factor": "profit_factor",
        "delta_fees": "fees",
        "delta_errors": "number_of_errors",
    }
    result: dict[str, Any] = {}
    for output, key in pairs.items():
        left, right = _number(candidate.get(key)), _number(production.get(key))
        result[output] = str(left - right) if left is not None and right is not None else NA
    result["delta_stability"] = (
        candidate_confidence["stability"]["score"]
        - production_confidence["stability"]["score"]
    )
    result["delta_confidence"] = (
        candidate_confidence["confidence_score"]
        - production_confidence["confidence_score"]
    )
    for name, delta, lower in (
        ("candidate_better_return", "delta_return", False),
        ("candidate_lower_drawdown", "delta_drawdown", True),
        ("candidate_better_pf", "delta_profit_factor", False),
        ("candidate_more_stable", "delta_stability", False),
        ("candidate_fewer_errors", "delta_errors", True),
    ):
        value = result[delta]
        numeric = _number(value)
        result[name] = (
            NA if numeric is None
            else numeric < 0 if lower
            else numeric > 0
        )
    return result


def recommendation(
    candidate: dict[str, Any],
    production: dict[str, Any],
    confidence: dict[str, Any],
    comparison: dict[str, Any],
    *,
    comparable_candles: int,
    operational: dict[str, Any],
    config: PromotionConfig,
) -> dict[str, Any]:
    blockers: list[str] = []
    limits: list[str] = []
    positives: list[str] = []
    days = confidence["observation_days"]
    trades = int(candidate["closed_trades_count"])
    error_rate = confidence["error_rate"]
    if days < config.minimum_days:
        blockers.append(f"only {days}/{config.minimum_days} observation days")
    if trades < config.minimum_closed_trades:
        blockers.append(f"only {trades}/{config.minimum_closed_trades} closed trades")
    if comparable_candles < config.minimum_comparable_candles:
        blockers.append(
            f"only {comparable_candles}/{config.minimum_comparable_candles} comparable candles"
        )
    if error_rate != NA and error_rate > config.maximum_error_rate:
        blockers.append(
            f"error rate {error_rate:.2%} exceeds {config.maximum_error_rate:.2%}"
        )
    if operational.get("state_complete") is False:
        blockers.append("state is damaged or incomplete")
    if config.block_on_active_halt and operational.get("active_halt"):
        blockers.append(f"active halt: {operational['active_halt']}")
    if config.block_on_inactive_timer and operational.get("timer_active") is False:
        blockers.append("candidate timer is inactive")
    if config.block_on_stale_data and operational.get("stale_data"):
        blockers.append("market data or strategy state is stale")
    if operational.get("cycles_running") is False:
        blockers.append("trading cycles are not running")
    if operational.get("same_candles") is False:
        blockers.append("production and candidate use different candle sets")
    if (
        config.block_on_incompatible_config
        and operational.get("compatible_config") is False
    ):
        blockers.append("capital or fee configuration is incompatible")
    for label, key in (
        ("candidate has better return", "candidate_better_return"),
        ("candidate has lower drawdown", "candidate_lower_drawdown"),
        ("candidate has better profit factor", "candidate_better_pf"),
        ("candidate is more stable", "candidate_more_stable"),
        ("candidate has fewer errors", "candidate_fewer_errors"),
    ):
        if comparison.get(key) is True:
            positives.append(label)
    pf = _number(candidate.get("profit_factor"))
    if pf is None:
        limits.append("profit factor is unavailable")
    elif pf < Decimal(str(config.minimum_profit_factor)):
        limits.append("profit factor is below the configured minimum")
    if confidence["stability"]["status"] == "UNAVAILABLE":
        limits.append("insufficient rolling windows")
    reject = (
        comparison.get("candidate_better_return") is False
        and comparison.get("candidate_lower_drawdown") is False
    ) or (
        pf is not None
        and trades >= config.minimum_closed_trades
        and pf < Decimal(str(config.minimum_profit_factor))
    ) or confidence["stability"]["status"] == "UNSTABLE"
    sample_blockers = blockers[:]
    if sample_blockers:
        value = "INSUFFICIENT_DATA"
    elif reject:
        value = "REJECT_FOR_NOW"
    elif confidence["confidence_score"] < config.ready_confidence:
        value = "CONTINUE_OBSERVATION"
    else:
        advantage = _number(comparison.get("delta_return"))
        strong = (
            confidence["confidence_score"] >= config.strong_confidence
            and advantage is not None
            and advantage >= Decimal(str(config.strong_return_advantage_percent))
            and comparison.get("candidate_lower_drawdown") is not False
            and confidence["stability"]["status"] in {"STABLE", "VERY_STABLE"}
        )
        value = "STRONG_CANDIDATE" if strong else "READY_FOR_REVIEW"
    assert value in RECOMMENDATIONS
    return {
        "recommendation": value,
        "confidence_score": confidence["confidence_score"],
        "confidence_level": confidence["confidence_level"],
        "positive_factors": positives or ["no material positive factor established yet"],
        "limiting_factors": limits,
        "blocking_conditions": blockers,
        "based_on": {
            "observation_days": days,
            "closed_trades": trades,
            "comparable_candles": comparable_candles,
            "error_rate": error_rate,
            "profit_factor": candidate["profit_factor"],
            "return_percent": candidate["return_percent"],
            "max_drawdown_percent": candidate["max_drawdown_percent"],
            "stability": confidence["stability"]["status"],
        },
        "automatic_promotion": False,
    }


def build_promotion_review(
    laboratory: LaboratoryConfig,
    promotion: PromotionConfig,
    *,
    period: str = "24h",
    strategy_filter: str | None = None,
    now: datetime | None = None,
    timezone_name: str = "UTC",
    operational: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    base = build_report(
        laboratory, period=period, strategy_filter=None,
        now=current, timezone_name=timezone_name,
    )
    windows = rolling_metrics(
        laboratory, promotion, now=current, timezone_name=timezone_name
    )
    derived_operational = _default_operational(laboratory, current)
    for strategy_id, values in (operational or {}).items():
        derived_operational.setdefault(strategy_id, {}).update(values)
    operational = derived_operational
    confidences: dict[str, dict[str, Any]] = {}
    for strategy_id, metrics in base["strategies"].items():
        comparable = (
            max(
                (
                    item["comparable_candles"]
                    for candidate_id, item in base["comparisons"].items()
                    if strategy_id in {"production", candidate_id}
                ),
                default=0,
            )
        )
        confidences[strategy_id] = calculate_confidence(
            metrics,
            comparable_candles=comparable,
            windows=windows.get(strategy_id, {}),
            operational=operational.get(strategy_id, {}),
            config=promotion,
            now=current,
        )
    reviews: dict[str, Any] = {}
    production = base["strategies"].get("production")
    if production:
        for candidate_id, decision_comparison in base["comparisons"].items():
            candidate = base["strategies"][candidate_id]
            comparison = compare_candidate(
                candidate, production, confidences[candidate_id],
                confidences["production"],
            )
            op = operational.get(candidate_id, {})
            op.setdefault(
                "same_candles",
                decision_comparison["production_only_decisions"] == 0
                and decision_comparison["candidate_only_decisions"] == 0,
            )
            op.setdefault("compatible_config", True)
            reviews[candidate_id] = {
                **recommendation(
                    candidate, production, confidences[candidate_id],
                    comparison,
                    comparable_candles=decision_comparison["comparable_candles"],
                    operational=op,
                    config=promotion,
                ),
                "comparison": comparison,
            }
    if strategy_filter:
        if strategy_filter not in base["strategies"]:
            raise ValueError(f"unknown or disabled strategy: {strategy_filter}")
        base["strategies"] = {
            strategy_filter: base["strategies"][strategy_filter]
        }
        windows = {strategy_filter: windows[strategy_filter]}
        confidences = {strategy_filter: confidences[strategy_filter]}
        reviews = (
            {strategy_filter: reviews[strategy_filter]}
            if strategy_filter in reviews else {}
        )
    base["rolling_metrics"] = windows
    base["confidence"] = confidences
    base["promotion_reviews"] = reviews
    base["operational"] = operational
    base["automatic_promotion"] = False
    return base


def _default_operational(
    laboratory: LaboratoryConfig, now: datetime
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    latest_by_strategy: dict[str, int] = {}
    candles_by_strategy: dict[str, set[int]] = {}
    for spec in laboratory.strategies:
        if not spec.enabled:
            continue
        summary: dict[str, Any] = {}
        warnings: list[str] = []
        if spec.runtime_summary and spec.runtime_summary.exists():
            try:
                loaded = json.loads(
                    spec.runtime_summary.read_text(encoding="utf-8")
                )
                if isinstance(loaded, dict):
                    summary = loaded
            except (OSError, json.JSONDecodeError):
                warnings.append("runtime summary is invalid")
        try:
            rows, _ = (
                read_jsonl_safely(spec.decisions)
                if spec.decisions.exists() else ([], False)
            )
            timestamps = [
                int(row["candle_timestamp"]) for row in rows
                if isinstance(row, dict) and row.get("candle_timestamp") is not None
            ]
            latest = max(timestamps) if timestamps else None
        except (OSError, ValueError, TypeError):
            latest = None
            warnings.append("decision journal is invalid")
        if latest is not None:
            latest_by_strategy[spec.strategy_id] = latest
            candles_by_strategy[spec.strategy_id] = set(timestamps)
            timing = candle_timing_diagnostics(
                latest, timeframe_minutes=60, now=now
            )
            if timing["stale_state"]:
                warnings.append(str(timing["warning_reason"]))
        else:
            timing = {}
            warnings.append("latest decision timestamp is unavailable")
        modified = (
            datetime.fromtimestamp(
                spec.runtime_summary.stat().st_mtime, timezone.utc
            ).isoformat()
            if spec.runtime_summary and spec.runtime_summary.exists()
            else None
        )
        result[spec.strategy_id] = {
            "timer_status": "UNKNOWN (read-only CLI)",
            "timer_active": None,
            "last_successful_cycle": modified,
            "cycles_running": None,
            "candle_close_age_seconds": timing.get(
                "candle_close_age_seconds"
            ),
            "market_lag_candles": timing.get("market_lag_candles"),
            "stale_data": timing.get("stale_state", True),
            "active_halt": summary.get(
                "active_halt", summary.get("active_halt_reason")
            ),
            "state_complete": spec.state.exists(),
            "warnings": warnings,
        }
    production_latest = latest_by_strategy.get("production")
    for spec in laboratory.strategies:
        if spec.kind == "candidate" and spec.strategy_id in result:
            candidate_latest = latest_by_strategy.get(spec.strategy_id)
            result[spec.strategy_id]["same_candles"] = (
                production_latest is not None and candidate_latest is not None
                and candles_by_strategy.get(spec.strategy_id, set()).issubset(
                    candles_by_strategy.get("production", set())
                )
            )
            result[spec.strategy_id]["compatible_config"] = True
    return result


def render_promotion_review(
    report: dict[str, Any], *, explain: bool = False
) -> str:
    lines = ["Strategy Confidence & Promotion Review", ""]
    for strategy_id, metrics in report["strategies"].items():
        confidence = report["confidence"][strategy_id]
        lines.extend(
            [
                f"{metrics['display_name']} [{strategy_id}]",
                f"Equity: {metrics['equity']}",
                f"Return: {metrics['return_percent']}%",
                f"Drawdown: {metrics['max_drawdown_percent']}%",
                f"PF: {metrics['profit_factor']}",
                f"Closed trades: {metrics['closed_trades_count']}",
                f"Observation days: {confidence['observation_days']}",
                f"Confidence: {confidence['confidence_score']}/100 — "
                f"{confidence['confidence_level']}",
                f"Stability: {confidence['stability']['status']}",
            ]
        )
        review = report["promotion_reviews"].get(strategy_id)
        if review:
            lines.append(f"Recommendation: {review['recommendation']}")
            comparison = review["comparison"]
            lines.extend(
                [
                    "Vs production:",
                    f"  return delta: {comparison['delta_return']}",
                    f"  drawdown delta: {comparison['delta_drawdown']}",
                    f"  PF delta: {comparison['delta_profit_factor']}",
                    f"  stability delta: {comparison['delta_stability']}",
                    f"  confidence delta: {comparison['delta_confidence']}",
                ]
            )
            if explain:
                lines.append("Positive factors:")
                lines.extend(f"  - {item}" for item in review["positive_factors"])
                lines.append("Limitations:")
                lines.extend(
                    f"  - {item}" for item in review["limiting_factors"]
                )
                lines.append("Blocking conditions:")
                lines.extend(
                    f"  - {item}" for item in review["blocking_conditions"]
                )
            operational = report.get("operational", {}).get(strategy_id, {})
            lines.extend(
                [
                    "Operational:",
                    f"  timer status: {operational.get('timer_status', 'N/A')}",
                    f"  last successful cycle: "
                    f"{operational.get('last_successful_cycle', 'N/A')}",
                    f"  candle close age: "
                    f"{operational.get('candle_close_age_seconds', 'N/A')}",
                    f"  market lag candles: "
                    f"{operational.get('market_lag_candles', 'N/A')}",
                    f"  active halt: {operational.get('active_halt') or 'none'}",
                    f"  warnings: {operational.get('warnings', [])}",
                ]
            )
        lines.append("")
    lines.append("Automatic promotion: disabled")
    return "\n".join(lines) + "\n"
