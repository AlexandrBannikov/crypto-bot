from decimal import Decimal
from pathlib import Path

from app.candle import Candle
from app.causal_execution import (
    CAUSAL_POSITION_LIFECYCLE,
    LEGACY_POSITION_LIFECYCLE,
    process_candle_execution,
    queue_pending_action,
)
from app.execution_runner import ExecutionRunner
from app.paper_executor import PaperExecutor
from app.trade_journal import JsonlTradeJournal
from app.trading_controller import TradingController, TradingControllerState
from app.trading_controller_store import TradingControllerStateStore
from app.trading_runtime import TradingRuntime
from app.trading_types import TradeAction


D = Decimal


def candle(ts: int, *, open: str, high: str, low: str, close: str) -> Candle:
    return Candle(ts, float(open), float(high), float(low), float(close), 1)


def controller(tmp_path: Path, state: TradingControllerState | None = None) -> TradingController:
    return TradingController(
        TradingRuntime(ExecutionRunner(PaperExecutor())),
        state=state,
        trade_journal=JsonlTradeJournal(tmp_path / "trades.jsonl"),
    )


def test_new_entry_is_queued_and_filled_only_at_next_open(tmp_path: Path) -> None:
    item = controller(tmp_path)
    queue_pending_action(
        item, action=TradeAction.OPEN_LONG,
        signal_timestamp=3600, signal_price=D("100"),
    )
    assert not item.state.has_open_position
    result = process_candle_execution(
        item, symbol="ETHUSDT",
        candle=candle(7200, open="105", high="110", low="90", close="100"),
        entry_quantity=D("0.01"),
    )
    assert result.opened_on_candle
    assert item.state.entry_price == D("105.0")
    assert item.state.position_signal_timestamp == 3600
    assert item.state.position_fill_timestamp == 7200
    assert item.state.position_lifecycle_version == CAUSAL_POSITION_LIFECYCLE
    # The low of the already-complete fill candle cannot retroactively stop it.
    assert item.state.has_open_position


def test_new_position_stop_is_gap_aware_on_later_candle(tmp_path: Path) -> None:
    item = controller(tmp_path)
    queue_pending_action(item, action=TradeAction.OPEN_LONG,
                         signal_timestamp=0, signal_price=D("100"))
    process_candle_execution(
        item, symbol="ETHUSDT",
        candle=candle(3600, open="100", high="101", low="99", close="100"),
        entry_quantity=D("0.01"),
    )
    result = process_candle_execution(
        item, symbol="ETHUSDT",
        candle=candle(7200, open="95", high="99", low="94", close="96"),
        entry_quantity=D("0.01"),
    )
    assert result.stop_triggered
    assert result.stop_fill_price == D("95.0")
    assert not item.state.has_open_position


def test_intrabar_stop_fills_at_stop_price(tmp_path: Path) -> None:
    state = TradingControllerState(
        position_quantity=D("1"), entry_price=D("100"), stop_loss=D("98"),
        virtual_balance=D("899.9"), entry_fee=D("0.1"),
        opened_at="2026-01-01T00:00:00+00:00",
        position_signal_timestamp=0, position_fill_timestamp=3600,
        position_lifecycle_version=CAUSAL_POSITION_LIFECYCLE,
    )
    item = controller(tmp_path, state)
    result = process_candle_execution(
        item, symbol="ETHUSDT",
        candle=candle(7200, open="100", high="101", low="97", close="99"),
        entry_quantity=D("1"),
    )
    assert result.stop_fill_price == D("98")


def test_existing_position_keeps_legacy_close_only_stop(tmp_path: Path) -> None:
    state = TradingControllerState(
        position_quantity=D("1"), entry_price=D("100"), stop_loss=D("98"),
        virtual_balance=D("899.9"), entry_fee=D("0.1"),
        opened_at="2026-01-01T00:00:00+00:00",
    )
    item = controller(tmp_path, state)
    first = process_candle_execution(
        item, symbol="ETHUSDT",
        candle=candle(7200, open="100", high="101", low="90", close="99"),
        entry_quantity=D("1"),
    )
    assert not first.stop_triggered
    assert item.state.has_open_position
    second = process_candle_execution(
        item, symbol="ETHUSDT",
        candle=candle(10800, open="100", high="101", low="90", close="97"),
        entry_quantity=D("1"),
    )
    assert second.stop_fill_price == D("97.0")


def test_pending_intent_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = TradingControllerStateStore(path)
    item = TradingController(
        TradingRuntime(ExecutionRunner(PaperExecutor())), state_store=store,
    )
    queue_pending_action(item, action=TradeAction.OPEN_LONG,
                         signal_timestamp=3600, signal_price=D("100"))
    restored = store.load()
    assert restored.pending_action == TradeAction.OPEN_LONG
    assert restored.pending_signal_timestamp == 3600
