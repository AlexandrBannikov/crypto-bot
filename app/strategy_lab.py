from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from app.account_snapshot import calculate_account_snapshot
from app.candidate_runtime import CandidateStateStore
from app.runtime_health import read_jsonl_safely
from app.trade_journal import TradeJournalEntry
from app.trading_controller_store import TradingControllerStateStore


NA = "N/A"
VALID_STATUSES = {"produced", "missing", "error", "skipped"}
PERIODS = ("today", "24h", "7d", "14d", "30d", "since_start", "all")


@dataclass(frozen=True, slots=True)
class RankingThresholds:
    minimum_comparable_candles: int = 20
    minimum_closed_trades: int = 5
    minimum_calendar_days: int = 7


@dataclass(frozen=True, slots=True)
class StrategySpec:
    strategy_id: str
    display_name: str
    enabled: bool
    kind: str
    state: Path
    trades: Path
    decisions: Path
    runtime_summary: Path | None = None


@dataclass(frozen=True, slots=True)
class LaboratoryConfig:
    initial_balance: Decimal
    fee_rate: Decimal
    ranking: RankingThresholds
    strategies: tuple[StrategySpec, ...]
    scored_decisions: Path | None = None


@dataclass(frozen=True, slots=True)
class NormalizedDecision:
    candle_timestamp: int
    strategy_id: str
    signal: str
    action: str
    position_before: str
    position_after: str
    reason: str
    price: Decimal | None
    decision_status: str
    status_reason: str | None = None

    def to_dict(self, zone: ZoneInfo | None = None) -> dict[str, Any]:
        result = asdict(self)
        result["price"] = str(self.price) if self.price is not None else None
        if zone is not None:
            result["time"] = datetime.fromtimestamp(
                self.candle_timestamp, timezone.utc
            ).astimezone(zone).isoformat()
        return result


def load_config(path: Path, *, root: Path | None = None) -> LaboratoryConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    base = root or path.parent.parent
    ranking = RankingThresholds(**payload.get("ranking", {}))
    specs: list[StrategySpec] = []
    seen: set[str] = set()
    for raw in payload["strategies"]:
        strategy_id = str(raw["strategy_id"]).strip()
        if not strategy_id or strategy_id in seen:
            raise ValueError(f"invalid or duplicate strategy_id: {strategy_id!r}")
        seen.add(strategy_id)
        kind = str(raw["kind"])
        if kind not in {"production", "candidate"}:
            raise ValueError(f"unsupported strategy kind: {kind}")
        specs.append(
            StrategySpec(
                strategy_id=strategy_id,
                display_name=str(raw["display_name"]),
                enabled=bool(raw.get("enabled", True)),
                kind=kind,
                state=base / raw["state"],
                trades=base / raw["trades"],
                decisions=base / raw["decisions"],
                runtime_summary=(
                    base / raw["runtime_summary"]
                    if raw.get("runtime_summary") else None
                ),
            )
        )
    if not any(item.strategy_id == "production" for item in specs):
        raise ValueError("strategy registry must contain production")
    return LaboratoryConfig(
        initial_balance=Decimal(str(payload.get("initial_balance", "1000"))),
        fee_rate=Decimal(str(payload.get("fee_rate", "0.001"))),
        ranking=ranking,
        strategies=tuple(specs),
        scored_decisions=(base / payload["scored_candidate_observability"]["decisions"] if payload.get("scored_candidate_observability", {}).get("decisions") else None),
    )


def _position(value: Any) -> str:
    normalized = str(value or "FLAT").upper()
    if "SHORT" in normalized:
        return "SHORT"
    if normalized in {"LONG", "OPEN", "OPEN_LONG"}:
        return "LONG"
    return "FLAT"


def _action(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "open_long": "ENTER_LONG",
        "open_short": "ENTER_SHORT",
        "enter": "ENTER_LONG",
        "enter_long": "ENTER_LONG",
        "enter_short": "ENTER_SHORT",
        "close_long": "EXIT_LONG",
        "close_short": "EXIT_SHORT",
        "exit": "EXIT_LONG",
        "exit_long": "EXIT_LONG",
        "exit_short": "EXIT_SHORT",
        "hold": "HOLD",
        "wait": "HOLD",
        "wait_pullback": "HOLD",
        "cancel_pullback": "HOLD",
    }.get(normalized, "ERROR")


def normalize_decision(
    row: dict[str, Any], spec: StrategySpec
) -> NormalizedDecision:
    try:
        timestamp = int(row["candle_timestamp"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("decision has invalid candle_timestamp")
    explicit_status = str(row.get("decision_status", "")).lower()
    status = explicit_status if explicit_status in VALID_STATUSES else "produced"
    raw_action = row.get("action")
    if raw_action is None:
        raw_action = (
            row.get("effective_action", row.get("execution_signal"))
            if spec.kind == "production"
            else row.get("decision")
        )
    action = _action(raw_action)
    if action == "ERROR":
        status = "error"
    signal = str(
        row.get(
            "signal",
            row.get("baseline_signal", row.get("decision", raw_action or "UNKNOWN")),
        )
    ).upper()
    before = _position(
        row.get("position_before", row.get("position_state_before", "FLAT"))
    )
    after = _position(
        row.get("position_after", row.get("position_state_after", before))
    )
    raw_price = row.get("price", row.get("close"))
    try:
        price = Decimal(str(raw_price)) if raw_price is not None else None
    except Exception:
        price = None
    reason = str(
        row.get("reason")
        or row.get("exit_reason")
        or row.get("blocked_reason")
        or row.get("shadow_block_reason")
        or ("valid strategy decision" if status == "produced" else "unspecified")
    )
    status_reason = row.get("status_reason")
    return NormalizedDecision(
        timestamp,
        spec.strategy_id,
        signal,
        action,
        before,
        after,
        reason,
        price,
        status,
        str(status_reason) if status_reason else None,
    )


def load_decisions(spec: StrategySpec) -> tuple[list[NormalizedDecision], list[str]]:
    if not spec.decisions.exists():
        return [], [f"{spec.strategy_id}: decision journal not found"]
    rows, ignored = read_jsonl_safely(spec.decisions)
    warnings = (
        [f"{spec.strategy_id}: incomplete final decision line ignored"]
        if ignored else []
    )
    result: list[NormalizedDecision] = []
    seen: set[int] = set()
    for index, row in enumerate(rows, 1):
        try:
            item = normalize_decision(row, spec)
            if item.candle_timestamp in seen:
                warnings.append(
                    f"{spec.strategy_id}: duplicate candle "
                    f"{item.candle_timestamp} (already processed)"
                )
                continue
            seen.add(item.candle_timestamp)
            result.append(item)
        except (TypeError, ValueError) as exc:
            warnings.append(f"{spec.strategy_id}: decision {index}: {exc}")
    return sorted(result, key=lambda item: item.candle_timestamp), warnings


def _period_bounds(
    period: str,
    now: datetime,
    zone: ZoneInfo,
    start_timestamp: int | None,
) -> tuple[int | None, int]:
    if period not in PERIODS:
        raise ValueError(f"unsupported period: {period}")
    end = int(now.timestamp()) + 1
    if period == "all":
        return None, end
    if period == "since_start":
        return start_timestamp, end
    if period == "24h":
        return int((now - timedelta(hours=24)).timestamp()), end
    if period == "7d":
        return int((now - timedelta(days=7)).timestamp()), end
    if period == "14d":
        return int((now - timedelta(days=14)).timestamp()), end
    if period == "30d":
        return int((now - timedelta(days=30)).timestamp()), end
    local = now.astimezone(zone)
    return int(local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()), end


def _trade_time(trade: TradeJournalEntry) -> int:
    return int(datetime.fromisoformat(trade.closed_at.replace("Z", "+00:00")).timestamp())


def _read_trades(path: Path) -> tuple[list[TradeJournalEntry], list[str]]:
    if not path.exists():
        return [], []
    try:
        rows, ignored = read_jsonl_safely(path, parser=TradeJournalEntry.from_dict)
    except ValueError as exc:
        return [], [f"invalid trade journal {path}: {exc}"]
    return rows, ([f"incomplete final trade line ignored: {path}"] if ignored else [])


def _load_state(spec: StrategySpec, initial: Decimal):
    if spec.kind == "production":
        return TradingControllerStateStore(spec.state).load()
    return CandidateStateStore(spec.state, initial_balance=initial).load().controller


def _equity_curve(
    initial: Decimal,
    trades: Iterable[TradeJournalEntry],
    snapshot_equity: Decimal | None,
) -> list[Decimal]:
    curve = [initial]
    curve.extend(trade.virtual_balance_after for trade in trades)
    if snapshot_equity is not None and snapshot_equity != curve[-1]:
        curve.append(snapshot_equity)
    return curve


def max_drawdown_percent(curve: Iterable[Decimal]) -> Decimal:
    peak: Decimal | None = None
    maximum = Decimal("0")
    for equity in curve:
        peak = equity if peak is None else max(peak, equity)
        if peak > 0:
            maximum = max(maximum, (peak - equity) / peak * Decimal("100"))
    return maximum


def strategy_metrics(
    spec: StrategySpec,
    *,
    initial_balance: Decimal,
    all_decisions: list[NormalizedDecision],
    period_decisions: list[NormalizedDecision],
    all_trades: list[TradeJournalEntry],
    period_trades: list[TradeJournalEntry],
    now: datetime,
) -> dict[str, Any]:
    state = _load_state(spec, initial_balance)
    price_decision = next(
        (item for item in reversed(all_decisions) if item.price is not None), None
    )
    current_price = price_decision.price if price_decision else None
    side = "LONG" if state.has_open_position else "FLAT"
    snapshot = calculate_account_snapshot(
        initial_balance=initial_balance,
        cash_balance=state.virtual_balance,
        position_side=side,
        position_quantity=state.position_quantity,
        entry_price=state.entry_price,
        current_price=current_price,
        realized_pnl=state.realized_pnl,
        opened_at=state.opened_at,
        now=now,
        stop_loss_price=state.stop_loss,
    )
    # Laboratory totals are equity-derived.  This includes the entry fee
    # already debited by the controller and avoids treating cash as equity.
    total_pnl = (
        snapshot.equity - initial_balance
        if snapshot.equity is not None else None
    )
    unrealized_pnl = (
        total_pnl - snapshot.realized_pnl
        if total_pnl is not None else None
    )
    pnl_values = [trade.net_pnl for trade in period_trades]
    daily_pnl: dict[str, Decimal] = {}
    for trade in period_trades:
        day = datetime.fromtimestamp(
            _trade_time(trade), timezone.utc
        ).date().isoformat()
        daily_pnl[day] = daily_pnl.get(day, Decimal("0")) + trade.net_pnl
    daily_returns = [
        float(value / initial_balance * Decimal("100"))
        for value in daily_pnl.values()
    ]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))
    fees = sum((trade.total_fee for trade in period_trades), Decimal("0"))
    # An open entry fee is not yet in the closed-trade journal.
    if state.has_open_position:
        fees += state.entry_fee
    closed = len(period_trades)
    pf: float | str
    if not closed:
        pf = NA
    elif gross_loss:
        pf = float(gross_profit / abs(gross_loss))
    elif gross_profit:
        pf = math.inf
    else:
        pf = NA
    curve = _equity_curve(initial_balance, period_trades, snapshot.equity)
    exposure = (
        snapshot.position_market_value / snapshot.equity * Decimal("100")
        if snapshot.position_market_value is not None
        and snapshot.equity not in {None, Decimal("0")}
        else Decimal("0")
    )
    return {
        "strategy_id": spec.strategy_id,
        "display_name": spec.display_name,
        "initial_balance": str(initial_balance),
        "cash_balance": str(snapshot.cash_balance),
        "position_side": snapshot.position_side,
        "position_quantity": str(snapshot.position_quantity),
        "entry_price": str(snapshot.entry_price) if snapshot.entry_price is not None else NA,
        "current_price": str(snapshot.current_price) if snapshot.current_price is not None else NA,
        "position_market_value": (
            str(snapshot.position_market_value)
            if snapshot.position_market_value is not None else NA
        ),
        "equity": str(snapshot.equity) if snapshot.equity is not None else NA,
        "realized_pnl": str(snapshot.realized_pnl),
        "unrealized_pnl": (
            str(unrealized_pnl)
            if unrealized_pnl is not None else NA
        ),
        "total_pnl": str(total_pnl) if total_pnl is not None else NA,
        "return_percent": (
            str(total_pnl / initial_balance * Decimal("100"))
            if total_pnl is not None and initial_balance else NA
        ),
        "fees_paid": str(fees),
        "fees": str(fees),
        "closed_trades_count": closed,
        "open_position_status": "OPEN" if snapshot.is_open else "FLAT",
        "opened_at": snapshot.opened_at,
        "trades": closed,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / closed * 100 if closed else NA,
        "gross_profit": str(gross_profit),
        "gross_loss": str(gross_loss),
        "profit_factor": pf,
        "max_drawdown_percent": str(max_drawdown_percent(curve)),
        "average_trade_pnl": (
            str(sum(pnl_values, Decimal("0")) / closed) if closed else NA
        ),
        "best_trade": str(max(pnl_values)) if closed else NA,
        "worst_trade": str(min(pnl_values)) if closed else NA,
        "current_position": snapshot.position_side,
        "exposure_percent": str(exposure),
        "number_of_decisions": sum(
            item.decision_status == "produced" for item in period_decisions
        ),
        "number_of_errors": sum(
            item.decision_status == "error" for item in period_decisions
        ),
        "number_of_missing": sum(
            item.decision_status in {"missing", "skipped"}
            for item in period_decisions
        ),
        "period_realized_pnl": str(sum(pnl_values, Decimal("0"))),
        "daily_returns": daily_returns,
        "equity_curve": [str(value) for value in curve],
        "observation_start": (
            datetime.fromtimestamp(all_decisions[0].candle_timestamp, timezone.utc).isoformat()
            if all_decisions else None
        ),
    }


def compare_decisions(
    production: list[NormalizedDecision],
    candidate: list[NormalizedDecision],
    *,
    zone: ZoneInfo,
) -> dict[str, Any]:
    prod = {item.candle_timestamp: item for item in production}
    cand = {item.candle_timestamp: item for item in candidate}
    timestamps = sorted(prod.keys() | cand.keys())
    categories: Counter[str] = Counter()
    comparable = agreement = 0
    production_only = candidate_only = missing = errors = 0
    differences: list[dict[str, Any]] = []
    for timestamp in timestamps:
        left, right = prod.get(timestamp), cand.get(timestamp)
        if left is None:
            candidate_only += 1
            missing += 1
            category = "candidate_only"
        elif right is None:
            production_only += 1
            missing += 1
            category = "production_only"
        elif "error" in {left.decision_status, right.decision_status}:
            errors += 1
            category = "error"
        elif left.decision_status != "produced" or right.decision_status != "produced":
            missing += 1
            category = f"{left.decision_status}/{right.decision_status}"
        else:
            comparable += 1
            if left.action == right.action:
                agreement += 1
                category = {
                    "ENTER_LONG": "same_enter",
                    "ENTER_SHORT": "same_enter",
                    "EXIT_LONG": "same_exit",
                    "EXIT_SHORT": "same_exit",
                    "HOLD": "same_hold",
                }.get(left.action, "same_action")
            elif left.action.startswith("ENTER") and right.action == "HOLD":
                category = "production_enter_candidate_hold"
            elif right.action.startswith("ENTER") and left.action == "HOLD":
                category = "candidate_enter_production_hold"
            elif left.action.startswith("EXIT") and right.action == "HOLD":
                category = "production_exit_candidate_hold"
            elif right.action.startswith("EXIT") and left.action == "HOLD":
                category = "candidate_exit_production_hold"
            elif left.action.startswith("EXIT") and right.action.startswith("EXIT"):
                category = "different_exit"
            elif {left.action, right.action} == {"ENTER_LONG", "ENTER_SHORT"}:
                category = "opposite_directions"
            else:
                category = "different_action"
        categories[category] += 1
        if category not in {"same_enter", "same_exit", "same_hold", "same_action"}:
            differences.append(
                {
                    "candle_timestamp": timestamp,
                    "timestamp": datetime.fromtimestamp(
                        timestamp, timezone.utc
                    ).astimezone(zone).isoformat(),
                    "production_action": left.action if left else "MISSING",
                    "candidate_action": right.action if right else "MISSING",
                    "production_reason": left.reason if left else "strategy not started or data absent",
                    "candidate_reason": right.reason if right else "strategy not started or data absent",
                    "production_status": left.decision_status if left else "missing",
                    "candidate_status": right.decision_status if right else "missing",
                    "category": category,
                }
            )
    return {
        "matched_candles": len(set(prod) & set(cand)),
        "comparable_candles": comparable,
        "agreement_count": agreement,
        "agreement_percent": agreement / comparable * 100 if comparable else NA,
        "action_differences": comparable - agreement,
        "production_only_decisions": production_only,
        "candidate_only_decisions": candidate_only,
        "missing_count": missing,
        "error_count": errors,
        "categories": dict(sorted(categories.items())),
        "recent_differences": differences[-20:],
    }


def _decimal_metric(metrics: dict[str, Any], key: str) -> Decimal | None:
    value = metrics.get(key)
    if value in {None, NA}:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def rank_strategies(
    metrics: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
    thresholds: RankingThresholds,
    now: datetime,
) -> dict[str, Any]:
    reasons: list[str] = []
    for strategy_id, item in metrics.items():
        if item["closed_trades_count"] < thresholds.minimum_closed_trades:
            reasons.append(
                f"{strategy_id}: {item['closed_trades_count']}/"
                f"{thresholds.minimum_closed_trades} closed trades"
            )
        start = item.get("observation_start")
        days = (
            max(0, (now - datetime.fromisoformat(start)).days)
            if start else 0
        )
        if days < thresholds.minimum_calendar_days:
            reasons.append(
                f"{strategy_id}: {days}/{thresholds.minimum_calendar_days} calendar days"
            )
    for candidate_id, comparison in comparisons.items():
        if comparison["comparable_candles"] < thresholds.minimum_comparable_candles:
            reasons.append(
                f"{candidate_id}: {comparison['comparable_candles']}/"
                f"{thresholds.minimum_comparable_candles} comparable candles"
            )
    if reasons:
        return {
            "available": False,
            "message": "Недостаточно данных для рейтинга",
            "leader": None,
            "reason": "; ".join(reasons),
            "confidence": "low",
        }
    scored: list[tuple[Decimal, str, dict[str, Any]]] = []
    for strategy_id, item in metrics.items():
        ret = _decimal_metric(item, "return_percent") or Decimal("0")
        drawdown = _decimal_metric(item, "max_drawdown_percent") or Decimal("0")
        pf_value = item["profit_factor"]
        pf = Decimal("3") if pf_value == math.inf else (
            Decimal(str(pf_value)) if pf_value != NA else Decimal("0")
        )
        trades = Decimal(item["closed_trades_count"])
        errors = Decimal(item["number_of_errors"])
        stability = Decimal("1") / (Decimal("1") + drawdown)
        score = ret - drawdown + min(pf, Decimal("3")) + min(
            trades / Decimal("10"), Decimal("2")
        ) + stability - errors
        scored.append((score, strategy_id, item))
    scored.sort(reverse=True)
    leader_score, leader, _ = scored[0]
    runner_score = scored[1][0] if len(scored) > 1 else leader_score
    gap = leader_score - runner_score
    confidence = "high" if gap >= 2 else "medium" if gap >= Decimal("0.5") else "low"
    return {
        "available": True,
        "message": "Рекомендательный рейтинг; автоматическое продвижение отключено",
        "leader": leader,
        "reason": f"risk-adjusted laboratory score {leader_score:.4f}",
        "confidence": confidence,
        "scores": {strategy_id: str(score) for score, strategy_id, _ in scored},
    }


def _delta(candidate: dict[str, Any], production: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key in (
        "equity", "total_pnl", "return_percent", "fees_paid",
        "max_drawdown_percent", "closed_trades_count",
    ):
        left, right = _decimal_metric(candidate, key), _decimal_metric(production, key)
        result[key] = str(left - right) if left is not None and right is not None else NA
    return result


def build_report(
    config: LaboratoryConfig,
    *,
    period: str = "24h",
    strategy_filter: str | None = None,
    now: datetime | None = None,
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    zone = ZoneInfo(timezone_name)
    specs = [item for item in config.strategies if item.enabled]
    if strategy_filter:
        specs = [item for item in specs if item.strategy_id == strategy_filter]
        if not specs:
            raise ValueError(f"unknown or disabled strategy: {strategy_filter}")
    warnings: list[str] = []
    all_decisions: dict[str, list[NormalizedDecision]] = {}
    all_trades: dict[str, list[TradeJournalEntry]] = {}
    for spec in specs:
        decisions, decision_warnings = load_decisions(spec)
        trades, trade_warnings = _read_trades(spec.trades)
        all_decisions[spec.strategy_id] = decisions
        all_trades[spec.strategy_id] = trades
        warnings.extend(decision_warnings + trade_warnings)
    starts = [
        rows[0].candle_timestamp for rows in all_decisions.values() if rows
    ]
    start, end = _period_bounds(period, current, zone, min(starts) if starts else None)
    period_decisions = {
        key: [item for item in rows if (start is None or item.candle_timestamp >= start) and item.candle_timestamp < end]
        for key, rows in all_decisions.items()
    }
    period_trades = {
        key: [item for item in rows if (start is None or _trade_time(item) >= start) and _trade_time(item) < end]
        for key, rows in all_trades.items()
    }
    metrics: dict[str, dict[str, Any]] = {}
    for spec in specs:
        try:
            metrics[spec.strategy_id] = strategy_metrics(
                spec,
                initial_balance=config.initial_balance,
                all_decisions=all_decisions[spec.strategy_id],
                period_decisions=period_decisions[spec.strategy_id],
                all_trades=all_trades[spec.strategy_id],
                period_trades=period_trades[spec.strategy_id],
                now=current,
            )
        except (OSError, ValueError) as exc:
            warnings.append(f"{spec.strategy_id}: state unavailable: {exc}")
    comparisons: dict[str, dict[str, Any]] = {}
    production = period_decisions.get("production")
    if production is not None:
        for spec in specs:
            if spec.kind == "candidate":
                comparison = compare_decisions(
                    production, period_decisions[spec.strategy_id], zone=zone
                )
                comparison["deltas"] = _delta(
                    metrics[spec.strategy_id], metrics["production"]
                )
                comparisons[spec.strategy_id] = comparison
    ranking = rank_strategies(metrics, comparisons, config.ranking, current)
    from app.scored_observability import aggregate as aggregate_entry_scores
    diagnostic_hours = {"today": 24, "24h": 24, "7d": 168, "14d": 336, "30d": 720}.get(period)
    entry_diagnostics = (
        aggregate_entry_scores(config.scored_decisions, hours=diagnostic_hours)
        if config.scored_decisions is not None else None
    )
    return {
        "schema_version": 2,
        "generated_at": current.isoformat(),
        "period": {
            "name": period,
            "start": (
                datetime.fromtimestamp(start, timezone.utc).astimezone(zone).isoformat()
                if start is not None else None
            ),
            "end": datetime.fromtimestamp(end - 1, timezone.utc).astimezone(zone).isoformat(),
            "timezone": timezone_name,
        },
        "status": "WARNING" if warnings else "OK",
        "health": {
            "timer": "see runtime check",
            "api": "not queried by read-only laboratory",
            "active_halt": None,
            "errors": sum(item["number_of_errors"] for item in metrics.values()),
        },
        "strategies": metrics,
        "comparisons": comparisons,
        "ranking": ranking,
        "entry_score_diagnostics": entry_diagnostics,
        "entry_score_note": "Entry Score diagnoses one setup; Strategy Confidence measures historical maturity. Entry Score is not used directly for promotion review.",
        "warnings": warnings,
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "Strategy Laboratory v2",
        f"Period: {report['period']['name']} "
        f"({report['period']['start'] or 'all'} — {report['period']['end']})",
        f"Status: {report['status']}",
        "",
    ]
    for strategy_id, item in report["strategies"].items():
        lines.extend(
            [
                f"{item['display_name']} [{strategy_id}]",
                f"  cash: {item['cash_balance']} USDT",
                f"  position market value: {item['position_market_value']} USDT",
                f"  equity: {item['equity']} USDT",
                f"  realized / unrealized / total PnL: "
                f"{item['realized_pnl']} / {item['unrealized_pnl']} / {item['total_pnl']} USDT",
                f"  return: {item['return_percent']}%",
                f"  position: {item['open_position_status']} "
                f"{item['position_side']} {item['position_quantity']}",
                f"  fees: {item['fees_paid']} USDT; closed trades: "
                f"{item['closed_trades_count']}",
                f"  drawdown: {item['max_drawdown_percent']}%; "
                f"PF: {item['profit_factor']}",
                "",
            ]
        )
    for candidate_id, comparison in report["comparisons"].items():
        lines.extend(
            [
                f"Comparison production vs {candidate_id}",
                f"  comparable candles: {comparison['comparable_candles']}",
                f"  agreement: {comparison['agreement_percent']}%",
                f"  missing: {comparison['missing_count']}; errors: {comparison['error_count']}",
                f"  delta equity / PnL / return: "
                f"{comparison['deltas']['equity']} / "
                f"{comparison['deltas']['total_pnl']} / "
                f"{comparison['deltas']['return_percent']}",
            ]
        )
        for item in comparison["recent_differences"][-5:]:
            lines.append(
                f"  {item['timestamp']}: {item['production_action']} / "
                f"{item['candidate_action']} "
                f"({item['production_status']}/{item['candidate_status']}) — "
                f"{item['production_reason']} | {item['candidate_reason']}"
            )
        lines.append("")
    ranking = report["ranking"]
    diagnostics = report.get("entry_score_diagnostics")
    if diagnostics is not None:
        lines.extend([
            "Entry Score diagnostics (scored candidate; diagnostic only)",
            "  Entry Score describes one potential entry; it is distinct from Strategy Confidence.",
            "  Entry Score is not a promotion-review input.",
            f"  decisions: {diagnostics['decisions_total']}; average score: {diagnostics['score']['average']}",
            f"  frequent limiters: {diagnostics['frequent_limiters']}", "",
        ])
    lines.extend(
        [
            "Ranking",
            (
                f"  leader: {ranking['leader']}; {ranking['reason']}; "
                f"confidence: {ranking['confidence']}"
                if ranking["available"]
                else f"  {ranking['message']}: {ranking['reason']}"
            ),
        ]
    )
    return "\n".join(lines) + "\n"
