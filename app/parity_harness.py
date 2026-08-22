"""Common live-like versus replay correctness harness."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Sequence

from app.candle import Candle
from app.canonical_features import CanonicalFeatureSnapshot, market_checksum
from app.config import PaperStrategyConfig, PaperStrategyMode
from app.execution_runner import ExecutionRunner
from app.paper_executor import PaperExecutor
from app.paper_strategy_router import PaperStrategyRouter
from app.production_orchestration import SignalFunction, process_production_candles
from app.runtime_versions import version_fields
from app.trade_journal import TradeJournalEntry
from app.trading_controller import TradingController
from app.trading_runtime import TradingRuntime


D = Decimal


class _MemoryJournal:
    def __init__(self) -> None:
        self.entries: list[TradeJournalEntry] = []

    def append(self, entry: TradeJournalEntry) -> None:
        if not any(item.record_id == entry.record_id for item in self.entries):
            self.entries.append(entry)


class _ExactFeatureStore:
    def __init__(self, candles: Sequence[Candle], *, symbol: str, timeframe_seconds: int):
        versions = version_fields()
        self.snapshots = {
            candle.timestamp: CanonicalFeatureSnapshot(
                candle_timestamp=candle.timestamp,
                candle_close_timestamp=candle.timestamp + timeframe_seconds,
                symbol=symbol,
                timeframe_seconds=timeframe_seconds,
                market_checksum=market_checksum(candle),
                score_total=0.0,
                components={},
                indicators={},
                hard_blocks=(),
                entry_eligible=False,
                bearish_ema_cross=False,
                feature_version=versions["feature_version"],
                strategy_logic_version=versions["strategy_logic_version"],
            )
            for candle in candles
        }

    def exact(self, candle_timestamp: int) -> CanonicalFeatureSnapshot | None:
        return self.snapshots.get(candle_timestamp)


@dataclass(frozen=True, slots=True)
class ParityTrace:
    decisions: tuple[tuple, ...]
    fills: tuple[tuple, ...]
    trades: tuple[dict, ...]
    fees: Decimal
    cash: Decimal
    equity: Decimal
    equity_curve: tuple[tuple[int, Decimal, Decimal], ...]


@dataclass(frozen=True, slots=True)
class ParityResult:
    live_like: ParityTrace
    replay: ParityTrace

    @property
    def identical(self) -> bool:
        return self.live_like == self.replay

    def assert_identical(self) -> None:
        if not self.identical:
            raise AssertionError(
                f"live/replay parity mismatch: {self.live_like!r} != {self.replay!r}"
            )


def _normalized_trade(entry: TradeJournalEntry) -> dict:
    payload = entry.to_dict()
    for nondeterministic in ("record_id", "opened_at", "closed_at"):
        payload.pop(nondeterministic, None)
    return payload


def _run_path(
    candles: Sequence[Candle], *, live_like: bool, initial_cursor: int,
    timeframe_seconds: int, symbol: str, entry_quantity: Decimal,
    signal_function: SignalFunction,
) -> ParityTrace:
    journal = _MemoryJournal()
    controller = TradingController(
        TradingRuntime(ExecutionRunner(PaperExecutor(), allow_live=False)),
        trade_journal=journal,
        clock=lambda: datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    router = PaperStrategyRouter(PaperStrategyConfig(
        mode=PaperStrategyMode.BASELINE, shadow_diagnostics_enabled=False,
    ))
    features = _ExactFeatureStore(
        candles, symbol=symbol, timeframe_seconds=timeframe_seconds,
    )
    decisions: list[tuple] = []
    fills: list[tuple] = []
    curve: list[tuple[int, Decimal, Decimal]] = []
    cursor = initial_cursor
    targets = [item for item in candles if item.timestamp > initial_cursor]
    batches = (
        [tuple(item for item in candles if item.timestamp <= target.timestamp) for target in targets]
        if live_like else [tuple(candles)]
    )
    for batch in batches:
        cycles = process_production_candles(
            batch,
            last_processed_timestamp=cursor,
            timeframe_seconds=timeframe_seconds,
            symbol=symbol,
            controller=controller,
            router=router,
            feature_store=features,  # type: ignore[arg-type]
            entry_quantity=entry_quantity,
            signal_function=signal_function,
        )
        for cycle in cycles:
            decisions.append((
                cycle.candle.timestamp,
                cycle.strategy_signal.value,
                cycle.effective_action.value,
                cycle.score_status,
                cycle.unresolved_gap,
            ))
            for execution in cycle.open_step.executions:
                if execution.execution is not None:
                    fills.append((
                        cycle.candle.timestamp,
                        execution.action.value,
                        execution.execution.status.value,
                        str(execution.execution.executed_quantity),
                        str(execution.execution.average_price),
                    ))
            state = cycle.state_after
            cash = state.virtual_balance
            equity = cash + state.position_quantity * D(str(cycle.candle.close))
            curve.append((cycle.candle.timestamp, cash, equity))
            cursor = cycle.candle.timestamp
    state = controller.state
    final_price = D(str(targets[-1].close)) if targets else D(str(candles[-1].close))
    return ParityTrace(
        decisions=tuple(decisions),
        fills=tuple(fills),
        trades=tuple(_normalized_trade(item) for item in journal.entries),
        fees=state.total_fees,
        cash=state.virtual_balance,
        equity=state.virtual_balance + state.position_quantity * final_price,
        equity_curve=tuple(curve),
    )


def run_live_replay_parity(
    candles: Sequence[Candle], *, initial_cursor: int,
    signal_function: SignalFunction, timeframe_seconds: int = 3600,
    symbol: str = "ETHUSDT", entry_quantity: Decimal = D("0.01"),
) -> ParityResult:
    """Run identical causal inputs incrementally and as one replay batch."""
    if not candles:
        raise ValueError("candles must not be empty")
    live = _run_path(
        candles, live_like=True, initial_cursor=initial_cursor,
        timeframe_seconds=timeframe_seconds, symbol=symbol,
        entry_quantity=entry_quantity, signal_function=signal_function,
    )
    replay = _run_path(
        candles, live_like=False, initial_cursor=initial_cursor,
        timeframe_seconds=timeframe_seconds, symbol=symbol,
        entry_quantity=entry_quantity, signal_function=signal_function,
    )
    return ParityResult(live, replay)
