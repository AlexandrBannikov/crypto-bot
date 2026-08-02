"""Shadow-only scored candidate runtime with isolated state and journal."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
from typing import Sequence

from app.candle import Candle
from app.risk_allocation import RiskAllocationConfig, size_for_score
from app.scored_observability import (
    ScoredReportingConfig, build_score_breakdown, load_reporting_config,
)
from app.signal_scoring import SignalScoreConfig, evaluate_signal
from app.trading_types import PositionSide


STRATEGY_NAME = "scored_candidate_v1"


@dataclass(frozen=True, slots=True)
class ScoredCandidateConfig:
    score: SignalScoreConfig = SignalScoreConfig()
    allocation: RiskAllocationConfig = RiskAllocationConfig()
    initial_balance: Decimal = Decimal("1000")
    mode: str = "shadow"
    reporting: ScoredReportingConfig = ScoredReportingConfig()

    @classmethod
    def from_env(cls) -> "ScoredCandidateConfig":
        return cls(
            allocation=RiskAllocationConfig.from_env(),
            reporting=load_reporting_config(),
        )

    def __post_init__(self) -> None:
        if self.mode != "shadow":
            raise ValueError("scored candidate is shadow-only in this stage")


@dataclass(frozen=True, slots=True)
class ScoredCandidateState:
    last_candle: int | None = None
    hypothetical_position: bool = False


class ScoredCandidateStateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> ScoredCandidateState:
        if not self.path.exists():
            return ScoredCandidateState()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return ScoredCandidateState(**payload)

    def save(self, state: ScoredCandidateState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        temporary = Path(name)
        try:
            with open(descriptor, "w", encoding="utf-8", closefd=True) as handle:
                json.dump(asdict(state), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)


class ScoredDecisionJournal:
    def __init__(self, path: Path):
        self.path = path

    def keys(self) -> set[tuple[str, int]]:
        if not self.path.exists():
            return set()
        keys = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            keys.add((str(row.get("strategy_name")), int(row["candle_close_timestamp"])))
        return keys

    def append(self, record: dict) -> bool:
        key = (str(record["strategy_name"]), int(record["candle_close_timestamp"]))
        if key in self.keys():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
        return True


def evaluate_shadow_candles(candles: Sequence[Candle], *, state_store: ScoredCandidateStateStore, decision_path: Path, config: ScoredCandidateConfig = ScoredCandidateConfig(), balance: float | None = None, timeframe_minutes: int = 60, strategy_name: str = STRATEGY_NAME) -> ScoredCandidateState:
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    state = state_store.load()
    journal = ScoredDecisionJournal(decision_path)
    existing = journal.keys()
    cash = float(config.initial_balance if balance is None else balance)
    for index, candle in enumerate(ordered):
        candle_close = candle.timestamp + timeframe_minutes * 60
        if (strategy_name, candle_close) in existing:
            if state.last_candle is None or candle.timestamp > state.last_candle:
                state = ScoredCandidateState(candle.timestamp, state.hypothetical_position)
                state_store.save(state)
            continue
        if state.last_candle is not None and candle.timestamp <= state.last_candle:
            continue
        score = evaluate_signal(ordered[: index + 1], config.score)
        fraction = 0.0
        position = None
        blocks = list(score.hard_blocks)
        if score.total_score < config.allocation.minimum_entry_score:
            blocks.append("score_below_entry_threshold")
        if not blocks and not state.hypothetical_position:
            stop = candle.close * (1.0 - config.score.stop_distance_pct)
            sized = size_for_score(score=score.total_score, balance=cash, entry_price=candle.close, stop_loss=stop, side=PositionSide.LONG, base_risk_per_trade=0.01, allocation=config.allocation)
            fraction = sized.risk_fraction
            blocks.extend(sized.hard_blocks)
            action = "ENTER_LONG" if sized.position is not None else "HOLD"
            position = sized.position.position_value if sized.position else None
            if action == "ENTER_LONG":
                state = ScoredCandidateState(candle.timestamp, True)
        elif state.hypothetical_position and score.indicators.get("ema_fast") is not None and score.indicators.get("ema_slow") is not None and score.indicators["ema_fast"] < score.indicators["ema_slow"]:
            action = "EXIT_LONG"
            state = ScoredCandidateState(candle.timestamp, False)
        else:
            action = "HOLD"
            state = ScoredCandidateState(candle.timestamp, state.hypothetical_position)
        unique_blocks = list(dict.fromkeys(blocks))
        components = {
            f"{name}_score": round(getattr(score, f"{name}_score"), 6)
            for name in ("trend", "ema_alignment", "adx", "pullback", "momentum", "volatility", "cost")
        }
        stop = candle.close * (1.0 - config.score.stop_distance_pct)
        baseline = size_for_score(
            score=config.allocation.full_risk_score, balance=cash,
            entry_price=candle.close, stop_loss=stop, side=PositionSide.LONG,
            base_risk_per_trade=0.01, allocation=config.allocation,
        )
        calculated_at = datetime.now(timezone.utc).isoformat()
        breakdown = build_score_breakdown(
            score, decision=action,
            entry_threshold=config.allocation.minimum_entry_score,
            strong_entry_threshold=config.reporting.strong_entry_threshold,
            risk_fraction=fraction,
            risk_allocation_amount=(0.0 if fraction <= 0 else position),
            baseline_position_amount=(baseline.position.position_value if baseline.position else None),
            blocking_factors=unique_blocks, candle_timestamp=candle.timestamp,
            allocation_rule_id=config.allocation.version,
            calculated_at=calculated_at, reporting=config.reporting,
        )
        detail = breakdown.to_dict()
        journal.append({
            "strategy_name": strategy_name, "candle_close_timestamp": candle_close,
            "candle_timestamp": candle.timestamp, "decision": action, "action": action,
            "signal_score": round(score.total_score, 6), "score": round(score.total_score, 6),
            "risk_fraction": round(fraction, 8), "final_risk_fraction": round(fraction, 8),
            "potential_position_size": position, "components": components,
            "hard_blocks": unique_blocks, "blockers": unique_blocks,
            "reason_codes": unique_blocks or [action.lower()], "score_version": score.version,
            "risk_model_version": config.allocation.version, "mode": config.mode,
            "evaluated_at": calculated_at, "score_breakdown": detail,
            "score_total": detail["total_score"], "score_max": detail["max_score"],
            "entry_threshold": detail["entry_threshold"],
            "strong_entry_threshold": detail["strong_entry_threshold"],
            "distance_to_entry": detail["distance_to_entry"],
            "distance_to_strong_entry": detail["distance_to_strong_entry"],
            "risk_allocation_pct": detail["risk_allocation_pct"],
            "risk_allocation_amount": detail["risk_allocation_amount"],
            "baseline_position_amount": detail["baseline_position_amount"],
            "score_components": detail["score_components"],
            "main_limiters": detail["main_limiters"],
            "positive_factors": detail["positive_factors"],
            "score_consistent": detail["score_consistent"],
            "calculation_version": detail["calculation_version"],
        })
        state_store.save(state)
    return state
