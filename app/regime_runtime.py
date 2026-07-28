from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.config import RuntimeSafetyConfig
from app.trading_types import TradeAction


BLOCK_REASONS = (
    "range",
    "high_volatility",
    "downtrend",
    "low_confidence",
    "unknown",
)


@dataclass(slots=True)
class RegimeRuntimeCounters:
    signals_total: int = 0
    entry_signals_total: int = 0
    exits_total: int = 0
    entries_allowed: int = 0
    entries_blocked: int = 0
    shadow_would_block: int = 0
    blocked_range: int = 0
    blocked_high_volatility: int = 0
    blocked_downtrend: int = 0
    blocked_low_confidence: int = 0
    blocked_unknown: int = 0
    stale_data_rejections: int = 0
    api_error_halts: int = 0
    risk_limit_halts: int = 0

    def validate(self) -> None:
        values = asdict(self)
        if any(not isinstance(value, int) or value < 0 for value in values.values()):
            raise ValueError("runtime counters must be non-negative integers")
        reason_total = sum(
            getattr(self, f"blocked_{reason}") for reason in BLOCK_REASONS
        )
        if self.entries_blocked != reason_total:
            raise ValueError(
                "entries_blocked must equal the sum of blocked reason counters"
            )

    def record_block(self, reason: str, *, shadow: bool) -> None:
        normalized = reason if reason in BLOCK_REASONS else "unknown"
        if shadow:
            self.shadow_would_block += 1
            return
        self.entries_blocked += 1
        setattr(
            self,
            f"blocked_{normalized}",
            getattr(self, f"blocked_{normalized}") + 1,
        )
        self.validate()


@dataclass(slots=True)
class RegimeRuntimeState:
    version: int = 1
    peak_balance: str = "1000"
    current_drawdown_percent: str = "0"
    maximum_drawdown_percent: str = "0"
    daily_starting_balance: str = "1000"
    daily_loss_percent: str = "0"
    daily_utc_date: str = ""
    active_halt_reason: str | None = None
    drawdown_halt_latched: bool = False
    last_processed_closed_candle: int | None = None
    last_journal_sequence: int = 0
    rebaseline_at: str | None = None
    rebaseline_note: str | None = None
    counters: RegimeRuntimeCounters = field(
        default_factory=RegimeRuntimeCounters
    )

    def __post_init__(self) -> None:
        self.counters.validate()

    def update_risk(
        self,
        balance: Decimal,
        config: RuntimeSafetyConfig,
        *,
        now: datetime | None = None,
    ) -> None:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        today = current.date().isoformat()
        if not self.daily_utc_date:
            self.daily_utc_date = today
            self.daily_starting_balance = str(balance)
        elif self.daily_utc_date != today:
            self.daily_utc_date = today
            self.daily_starting_balance = str(balance)
            self.daily_loss_percent = "0"
            if self.active_halt_reason == "daily_loss":
                self.active_halt_reason = None

        peak = max(Decimal(self.peak_balance), balance)
        self.peak_balance = str(peak)
        drawdown = (
            (peak - balance) / peak * Decimal("100")
            if peak > 0
            else Decimal("0")
        )
        daily_start = Decimal(self.daily_starting_balance)
        daily_loss = (
            max(Decimal("0"), daily_start - balance)
            / daily_start
            * Decimal("100")
            if daily_start > 0
            else Decimal("0")
        )
        self.current_drawdown_percent = str(drawdown)
        self.maximum_drawdown_percent = str(
            max(Decimal(self.maximum_drawdown_percent), drawdown)
        )
        self.daily_loss_percent = str(daily_loss)
        if drawdown >= Decimal(str(config.max_drawdown_percent)):
            if not self.drawdown_halt_latched:
                self.counters.risk_limit_halts += 1
            self.drawdown_halt_latched = True
            self.active_halt_reason = "maximum_drawdown"
        elif daily_loss >= Decimal(str(config.max_daily_loss_percent)):
            if self.active_halt_reason != "daily_loss":
                self.counters.risk_limit_halts += 1
            self.active_halt_reason = "daily_loss"

    def reset_drawdown_halt(self, balance: Decimal | None = None) -> None:
        self.drawdown_halt_latched = False
        if balance is not None:
            self.peak_balance = str(balance)
            self.current_drawdown_percent = "0"
        if self.active_halt_reason == "maximum_drawdown":
            self.active_halt_reason = None

    def permits_entry(self) -> bool:
        return self.active_halt_reason is None


class RegimeRuntimeStateStore:
    """Backward-compatible, atomic operational-state persistence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> RegimeRuntimeState:
        if not self.path.exists():
            return RegimeRuntimeState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            counters = RegimeRuntimeCounters(**payload.pop("counters", {}))
            return RegimeRuntimeState(counters=counters, **payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"failed to load runtime state: {exc}") from exc

    def save(self, state: RegimeRuntimeState) -> None:
        state.counters.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(asdict(state), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


def is_entry(action: TradeAction) -> bool:
    return action in {TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT}


def is_exit(action: TradeAction) -> bool:
    return action in {TradeAction.CLOSE_LONG, TradeAction.CLOSE_SHORT}
