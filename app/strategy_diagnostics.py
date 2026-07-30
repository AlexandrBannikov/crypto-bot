from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


class Decision(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class PositionState(str, Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


class ReasonCode(str, Enum):
    INSUFFICIENT_HISTORY = "insufficient_history"
    FAST_EMA_NOT_ABOVE_SLOW = "fast_ema_not_above_slow"
    FAST_EMA_NOT_BELOW_SLOW = "fast_ema_not_below_slow"
    NO_BULLISH_EMA_CROSS = "no_bullish_ema_cross"
    NO_BEARISH_EMA_CROSS = "no_bearish_ema_cross"
    PRICE_TREND_NOT_CONFIRMED = "price_trend_not_confirmed"
    TREND_STRENGTH_TOO_LOW = "trend_strength_too_low"
    POSITION_ALREADY_OPEN = "position_already_open"
    POSITION_ABSENT = "position_absent"
    RISK_FILTER_BLOCKED = "risk_filter_blocked"
    SIGNAL_ALREADY_PROCESSED = "signal_already_processed"
    STOP_LOSS_NOT_REACHED = "stop_loss_not_reached"
    NO_ENTRY_SIGNAL = "no_entry_signal"
    NO_EXIT_SIGNAL = "no_exit_signal"
    BUY_SIGNAL = "buy_signal"
    SELL_SIGNAL = "sell_signal"


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    timestamp: int
    close_price: float
    indicators: dict[str, float | None]
    position_state: PositionState
    decision: Decision
    passed_conditions: tuple[ReasonCode, ...]
    failed_conditions: tuple[ReasonCode, ...]
    primary_reason: ReasonCode


@dataclass(frozen=True, slots=True)
class DiagnosticRecord:
    timestamp: int
    symbol: str
    timeframe: str
    strategy_name: str
    strategy_parameters: dict[str, Any]
    position_state: str
    decision: str
    primary_reason: str
    reason_codes: tuple[str, ...]
    passed_conditions: tuple[str, ...]
    indicators: dict[str, float | None]
    close_price: float
    session_id: str

    @property
    def deduplication_key(self) -> tuple[str, str, str, str, int]:
        return (
            self.session_id,
            self.symbol,
            self.timeframe,
            self.strategy_name,
            self.timestamp,
        )

    @classmethod
    def from_decision(
        cls,
        decision: StrategyDecision,
        *,
        symbol: str,
        timeframe: str,
        strategy_name: str,
        strategy_parameters: dict[str, Any],
        session_id: str,
    ) -> "DiagnosticRecord":
        return cls(
            timestamp=decision.timestamp,
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            strategy_parameters=strategy_parameters,
            position_state=decision.position_state.value,
            decision=decision.decision.value,
            primary_reason=decision.primary_reason.value,
            reason_codes=tuple(
                reason.value for reason in decision.failed_conditions
            ),
            passed_conditions=tuple(
                reason.value for reason in decision.passed_conditions
            ),
            indicators=decision.indicators,
            close_price=decision.close_price,
            session_id=session_id,
        )


class DiagnosticJournal:
    """Small append-only JSONL journal with candle-level deduplication."""

    def __init__(
        self,
        path: str | Path,
        *,
        retention_days: int = 30,
    ) -> None:
        if retention_days < 0:
            raise ValueError("retention_days must not be negative")
        self.path = Path(path)
        self.retention_days = retention_days
        self._keys = {
            record.deduplication_key for record in self.read_all()
        }

    def append(self, record: DiagnosticRecord) -> bool:
        if record.deduplication_key in self._keys:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("a", encoding="utf-8") as file:
                os.fchmod(file.fileno(), 0o640)
                json.dump(
                    asdict(record),
                    file,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                file.write("\n")
        except OSError as exc:
            raise ValueError(
                f"failed to append strategy diagnostics: {exc}"
            ) from exc
        self._keys.add(record.deduplication_key)
        return True

    def read_all(self) -> list[DiagnosticRecord]:
        if not self.path.exists():
            return []
        records: list[DiagnosticRecord] = []
        for number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                payload["reason_codes"] = tuple(payload["reason_codes"])
                payload["passed_conditions"] = tuple(
                    payload["passed_conditions"]
                )
                records.append(DiagnosticRecord(**payload))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"corrupt strategy diagnostics line {number}"
                ) from exc
        return records

    def prune(self, *, now_timestamp: int | None = None) -> int:
        if self.retention_days == 0 or not self.path.exists():
            return 0
        now = (
            int(datetime.now(timezone.utc).timestamp())
            if now_timestamp is None
            else now_timestamp
        )
        cutoff = now - self.retention_days * 86400
        records = self.read_all()
        kept = [record for record in records if record.timestamp >= cutoff]
        removed = len(records) - len(kept)
        if not removed:
            return 0
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            for record in kept:
                json.dump(
                    asdict(record),
                    file,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                file.write("\n")
        os.replace(temporary, self.path)
        self._keys = {
            record.deduplication_key for record in kept
        }
        return removed


@dataclass(frozen=True, slots=True)
class DiagnosticSummary:
    total_candles: int
    decisions: dict[str, int]
    position_openings: int
    position_closings: int
    insufficient_history: int
    reason_counts: dict[str, int]
    reason_percentages: dict[str, float]
    top_no_entry_reasons: tuple[tuple[str, int], ...]
    max_candles_without_signal: int
    max_seconds_without_signal: int
    average_seconds_between_signals: float | None
    signals_by_month: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_diagnostics(
    records: Iterable[DiagnosticRecord],
) -> DiagnosticSummary:
    ordered = sorted(records, key=lambda item: item.timestamp)
    decisions = Counter(record.decision for record in ordered)
    reasons = Counter(
        reason for record in ordered for reason in record.reason_codes
    )
    signal_indexes = [
        index
        for index, record in enumerate(ordered)
        if record.decision in {Decision.BUY.value, Decision.SELL.value}
    ]
    signal_timestamps = [
        ordered[index].timestamp for index in signal_indexes
    ]
    gaps = [
        right - left
        for left, right in zip(signal_timestamps, signal_timestamps[1:])
    ]
    index_boundaries = [-1, *signal_indexes, len(ordered)]
    candle_gaps = [
        right - left - 1
        for left, right in zip(index_boundaries, index_boundaries[1:])
    ]
    if ordered:
        edge_gaps = []
        if signal_timestamps:
            edge_gaps = [
                signal_timestamps[0] - ordered[0].timestamp,
                ordered[-1].timestamp - signal_timestamps[-1],
            ]
        else:
            edge_gaps = [ordered[-1].timestamp - ordered[0].timestamp]
        time_gaps = [*gaps, *edge_gaps]
    else:
        time_gaps = [0]
    months = Counter(
        datetime.fromtimestamp(record.timestamp, timezone.utc).strftime("%Y-%m")
        for record in ordered
        if record.decision in {Decision.BUY.value, Decision.SELL.value}
    )
    total = len(ordered)
    no_entry = Counter()
    for record in ordered:
        if record.decision != Decision.BUY.value:
            no_entry.update(record.reason_codes)
    return DiagnosticSummary(
        total_candles=total,
        decisions={
            decision.value: decisions[decision.value] for decision in Decision
        },
        position_openings=decisions[Decision.BUY.value],
        position_closings=decisions[Decision.SELL.value],
        insufficient_history=reasons[ReasonCode.INSUFFICIENT_HISTORY.value],
        reason_counts=dict(sorted(reasons.items())),
        reason_percentages={
            reason: count / total * 100 if total else 0.0
            for reason, count in sorted(reasons.items())
        },
        top_no_entry_reasons=tuple(no_entry.most_common(5)),
        max_candles_without_signal=max(candle_gaps, default=0),
        max_seconds_without_signal=max(time_gaps),
        average_seconds_between_signals=mean(gaps) if gaps else None,
        signals_by_month=dict(sorted(months.items())),
    )


def format_diagnostic_summary(summary: DiagnosticSummary) -> str:
    lines = [
        "Strategy diagnostic summary",
        f"Processed candles: {summary.total_candles}",
        "Decisions: "
        + ", ".join(
            f"{name}={count}"
            for name, count in summary.decisions.items()
        ),
        (
            "Position events: "
            f"open={summary.position_openings}, "
            f"close={summary.position_closings}"
        ),
        (
            "Maximum period without signal: "
            f"{summary.max_candles_without_signal} candles "
            f"({summary.max_seconds_without_signal} seconds)"
        ),
        "Blocking reasons:",
    ]
    lines.extend(
        f"  {reason}: {count} "
        f"({summary.reason_percentages[reason]:.2f}%)"
        for reason, count in sorted(
            summary.reason_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )
    return "\n".join(lines)
