from decimal import Decimal
from datetime import datetime, timezone

import pytest

from app.execution import (
    ExecutionMode,
    ExecutionResult,
    ExecutionStatus,
)
from app.execution_runner import ExecutionRunner
from app.paper_executor import PaperExecutor
from app.strategies import Signal
from app.trading_controller import (
    TradingController,
    TradingControllerState,
)
from app.trading_runtime import TradingRuntime
from app.trading_types import PositionSide, TradeAction
from app.trade_journal import TradeJournalEntry


def build_controller(
    state: TradingControllerState | None = None,
) -> TradingController:
    runtime = TradingRuntime(
        ExecutionRunner(
            PaperExecutor(),
        )
    )

    return TradingController(
        runtime,
        state=state,
    )


def test_opens_long_position() -> None:
    controller = build_controller()

    result = controller.process_signal(
        symbol="ethusdt",
        signal=Signal.BUY,
        entry_quantity=Decimal("0.05"),
        price=Decimal("2500"),
    )

    assert result.execution is not None
    assert result.execution.mode == ExecutionMode.PAPER
    assert result.state.position_quantity == Decimal("0.05")
    assert result.state.has_open_position is True


def test_does_not_open_second_long_position() -> None:
    controller = build_controller(
        TradingControllerState(
            position_quantity=Decimal("0.05"),
        )
    )

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=TradeAction.OPEN_LONG,
        entry_quantity=Decimal("0.10"),
        price=Decimal("2500"),
    )

    assert result.execution is None
    assert result.skipped_reason == (
        "long position already open"
    )
    assert result.state.position_quantity == Decimal("0.05")


def test_closes_entire_long_position() -> None:
    controller = build_controller(
        TradingControllerState(
            position_quantity=Decimal("0.05"),
        )
    )

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("0.10"),
        price=Decimal("2600"),
    )

    assert result.execution is not None
    assert (
        result.execution.requested_quantity
        == Decimal("0.05")
    )
    assert result.state.position_quantity == Decimal("0")
    assert result.state.has_open_position is False


def test_does_not_close_missing_position() -> None:
    controller = build_controller()

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=TradeAction.CLOSE_LONG,
        entry_quantity=Decimal("0.05"),
        price=Decimal("2600"),
    )

    assert result.execution is None
    assert result.skipped_reason == (
        "no long position to close"
    )


def test_hold_does_not_execute_order() -> None:
    controller = build_controller()

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.HOLD,
        entry_quantity=Decimal("0.05"),
        price=Decimal("2500"),
    )

    assert result.execution is None
    assert result.skipped_reason == "hold signal"
    assert result.state.position_quantity == Decimal("0")
    assert result.accounting is None


@pytest.mark.parametrize(
    ("entry_quantity", "price", "message"),
    [
        (
            Decimal("0"),
            Decimal("2500"),
            "entry_quantity must be greater than zero",
        ),
        (
            Decimal("-0.01"),
            Decimal("2500"),
            "entry_quantity must be greater than zero",
        ),
        (
            Decimal("0.05"),
            Decimal("0"),
            "price must be greater than zero",
        ),
    ],
)
def test_rejects_invalid_request(
    entry_quantity: Decimal,
    price: Decimal,
    message: str,
) -> None:
    controller = build_controller()

    with pytest.raises(ValueError, match=message):
        controller.process_signal(
            symbol="ETHUSDT",
            signal=Signal.BUY,
            entry_quantity=entry_quantity,
            price=price,
        )


def test_rejects_negative_state_quantity() -> None:
    with pytest.raises(
        ValueError,
        match="position_quantity must not be negative",
    ):
        TradingControllerState(
            position_quantity=Decimal("-0.01"),
        )


def test_rejects_negative_fee_rate() -> None:
    with pytest.raises(
        ValueError,
        match="fee_rate must not be negative",
    ):
        TradingController(
            TradingRuntime(ExecutionRunner(PaperExecutor())),
            fee_rate=Decimal("-0.001"),
        )


class FakeStateStore:
    def __init__(
        self,
        state: TradingControllerState,
    ) -> None:
        self.loaded_state = state
        self.saved_states: list[
            TradingControllerState
        ] = []

    def load(self) -> TradingControllerState:
        return self.loaded_state

    def save(
        self,
        state: TradingControllerState,
    ) -> None:
        self.saved_states.append(state)


def test_loads_state_from_store() -> None:
    store = FakeStateStore(
        TradingControllerState(
            position_quantity=Decimal("0.07"),
        )
    )

    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    controller = TradingController(
        runtime,
        state_store=store,
    )

    assert (
        controller.state.position_quantity
        == Decimal("0.07")
    )


def test_saves_state_after_opening_position() -> None:
    store = FakeStateStore(
        TradingControllerState()
    )

    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    controller = TradingController(
        runtime,
        state_store=store,
    )

    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.BUY,
        entry_quantity=Decimal("0.05"),
        price=Decimal("2500"),
    )

    assert len(store.saved_states) == 1
    assert (
        store.saved_states[0].position_quantity
        == Decimal("0.05")
    )


def test_saves_state_after_closing_position() -> None:
    store = FakeStateStore(
        TradingControllerState(
            position_quantity=Decimal("0.05"),
        )
    )

    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    controller = TradingController(
        runtime,
        state_store=store,
    )

    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("0.10"),
        price=Decimal("2600"),
    )

    assert len(store.saved_states) == 1
    assert (
        store.saved_states[0].position_quantity
        == Decimal("0")
    )


def test_does_not_save_state_for_hold() -> None:
    store = FakeStateStore(
        TradingControllerState()
    )

    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    controller = TradingController(
        runtime,
        state_store=store,
    )

    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.HOLD,
        entry_quantity=Decimal("0.05"),
        price=Decimal("2500"),
    )

    assert store.saved_states == []


def test_rejects_state_and_store_together() -> None:
    store = FakeStateStore(
        TradingControllerState()
    )

    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    with pytest.raises(
        ValueError,
        match=(
            "state and state_store must not "
            "be provided together"
        ),
    ):
        TradingController(
            runtime,
            state=TradingControllerState(),
            state_store=store,
        )


def test_open_position_saves_entry_price() -> None:
    controller = build_controller()

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.BUY,
        entry_quantity=Decimal("0.01"),
        price=Decimal("1950"),
    )

    assert result.state.entry_price == Decimal("1950")
    assert result.state.stop_loss is None


def test_open_position_saves_stop_loss() -> None:
    from app.trade_signal import TradeSignal

    controller = build_controller()

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=TradeSignal(
            action=Signal.BUY,
            stop_loss=1911.0,
        ),
        entry_quantity=Decimal("0.01"),
        price=Decimal("1950"),
    )

    assert result.state.position_quantity == Decimal("0.01")
    assert result.state.entry_price == Decimal("1950")
    assert result.state.stop_loss == Decimal("1911.0")


def test_close_position_clears_entry_data() -> None:
    controller = build_controller(
        TradingControllerState(
            position_quantity=Decimal("0.01"),
            entry_price=Decimal("1950"),
            stop_loss=Decimal("1911"),
        )
    )

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("0.01"),
        price=Decimal("2000"),
    )

    assert result.state.position_quantity == Decimal("0")
    assert result.state.entry_price is None
    assert result.state.stop_loss is None


def test_profitable_close_updates_accounting() -> None:
    controller = build_controller()

    opened = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.BUY,
        entry_quantity=Decimal("2"),
        price=Decimal("100"),
    )
    assert opened.state.virtual_balance == Decimal("799.800")

    closed = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("2"),
        price=Decimal("120"),
    )

    assert closed.accounting is not None
    assert closed.accounting.net_pnl == Decimal("39.560")
    assert closed.state.virtual_balance == Decimal("1039.560")
    assert closed.state.realized_pnl == Decimal("39.560")
    assert closed.state.total_fees == Decimal("0.440")
    assert closed.state.closed_trades == 1
    assert closed.state.entry_fee == 0


def test_losing_close_updates_accounting() -> None:
    controller = build_controller()
    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.BUY,
        entry_quantity=Decimal("2"),
        price=Decimal("100"),
    )

    closed = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("2"),
        price=Decimal("90"),
    )

    assert closed.accounting is not None
    assert closed.accounting.net_pnl == Decimal("-20.380")
    assert closed.state.virtual_balance == Decimal("979.620")
    assert closed.state.realized_pnl == Decimal("-20.380")


def test_does_not_open_with_insufficient_balance() -> None:
    controller = build_controller()

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.BUY,
        entry_quantity=Decimal("10"),
        price=Decimal("100"),
    )

    assert result.execution is None
    assert result.skipped_reason == (
        "insufficient virtual balance"
    )
    assert result.state == TradingControllerState()


class FixedRuntime:
    def __init__(self, result: ExecutionResult) -> None:
        self.result = result

    def process_signal(self, request):
        return self.result


class MemoryJournal:
    def __init__(self) -> None:
        self.entries: list[TradeJournalEntry] = []

    def append(self, entry: TradeJournalEntry) -> None:
        self.entries.append(entry)


def test_partial_close_keeps_position_and_entry_fee() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("2"),
        entry_price=Decimal("100"),
        virtual_balance=Decimal("799.800"),
        entry_fee=Decimal("0.200"),
    )
    execution = ExecutionResult(
        mode=ExecutionMode.PAPER,
        status=ExecutionStatus.PARTIALLY_FILLED,
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        requested_quantity=Decimal("2"),
        requested_price=Decimal("120"),
        executed_quantity=Decimal("0.5"),
        average_price=Decimal("120"),
    )
    controller = TradingController(
        FixedRuntime(execution),
        state=state,
    )

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("2"),
        price=Decimal("120"),
    )

    assert result.accounting is not None
    assert result.accounting.net_pnl == Decimal("9.8900")
    assert result.state.position_quantity == Decimal("1.5")
    assert result.state.entry_fee == Decimal("0.1500")
    assert result.state.virtual_balance == Decimal("859.7400")
    assert result.state.closed_trades == 1


def test_profitable_close_is_written_to_journal() -> None:
    journal = MemoryJournal()
    timestamps = iter(
        [
            datetime(2026, 7, 27, 10, tzinfo=timezone.utc),
            datetime(2026, 7, 27, 11, tzinfo=timezone.utc),
        ]
    )
    controller = TradingController(
        TradingRuntime(ExecutionRunner(PaperExecutor())),
        trade_journal=journal,
        clock=lambda: next(timestamps),
    )
    controller.process_signal(
        symbol="ethusdt",
        signal=Signal.BUY,
        entry_quantity=Decimal("2"),
        price=Decimal("100"),
    )

    result = controller.process_signal(
        symbol="ethusdt",
        signal=Signal.SELL,
        entry_quantity=Decimal("2"),
        price=Decimal("120"),
        exit_reason="take_profit",
    )

    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert result.journal_entry is entry
    assert entry.symbol == "ETHUSDT"
    assert entry.opened_at == "2026-07-27T10:00:00+00:00"
    assert entry.closed_at == "2026-07-27T11:00:00+00:00"
    assert entry.net_pnl == Decimal("39.560")
    assert entry.exit_reason == "take_profit"
    assert entry.remaining_position_quantity == 0
    assert entry.closed_trades_after == 1


def test_losing_close_is_written_to_journal() -> None:
    journal = MemoryJournal()
    controller = TradingController(
        TradingRuntime(ExecutionRunner(PaperExecutor())),
        trade_journal=journal,
    )
    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.BUY,
        entry_quantity=Decimal("2"),
        price=Decimal("100"),
    )
    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("2"),
        price=Decimal("90"),
    )

    assert journal.entries[0].net_pnl == Decimal("-20.380")


def test_partial_close_writes_remaining_quantity() -> None:
    journal = MemoryJournal()
    state = TradingControllerState(
        position_quantity=Decimal("2"),
        entry_price=Decimal("100"),
        virtual_balance=Decimal("799.800"),
        entry_fee=Decimal("0.200"),
        opened_at="2026-07-27T10:00:00+00:00",
    )
    execution = ExecutionResult(
        mode=ExecutionMode.PAPER,
        status=ExecutionStatus.PARTIALLY_FILLED,
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        requested_quantity=Decimal("2"),
        requested_price=Decimal("120"),
        executed_quantity=Decimal("0.5"),
        average_price=Decimal("120"),
    )
    controller = TradingController(
        FixedRuntime(execution),
        state=state,
        trade_journal=journal,
    )

    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("2"),
        price=Decimal("120"),
    )

    assert len(journal.entries) == 1
    assert (
        journal.entries[0].remaining_position_quantity
        == Decimal("1.5")
    )
    assert journal.entries[0].closed_trades_after == 1


def test_hold_does_not_write_journal() -> None:
    journal = MemoryJournal()
    controller = TradingController(
        TradingRuntime(ExecutionRunner(PaperExecutor())),
        trade_journal=journal,
    )

    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.HOLD,
        entry_quantity=Decimal("1"),
        price=Decimal("100"),
    )

    assert journal.entries == []


def test_rejected_close_does_not_write_journal() -> None:
    journal = MemoryJournal()
    state = TradingControllerState(
        position_quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_fee=Decimal("0.1"),
    )
    execution = ExecutionResult(
        mode=ExecutionMode.PAPER,
        status=ExecutionStatus.REJECTED,
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        requested_quantity=Decimal("1"),
        requested_price=Decimal("90"),
    )
    controller = TradingController(
        FixedRuntime(execution),
        state=state,
        trade_journal=journal,
    )

    controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.SELL,
        entry_quantity=Decimal("1"),
        price=Decimal("90"),
    )

    assert journal.entries == []


def test_rejected_execution_does_not_change_state() -> None:
    state = TradingControllerState()
    execution = ExecutionResult(
        mode=ExecutionMode.PAPER,
        status=ExecutionStatus.REJECTED,
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        requested_quantity=Decimal("1"),
        requested_price=Decimal("100"),
    )
    controller = TradingController(
        FixedRuntime(execution),
        state=state,
    )

    result = controller.process_signal(
        symbol="ETHUSDT",
        signal=Signal.BUY,
        entry_quantity=Decimal("1"),
        price=Decimal("100"),
    )

    assert result.execution is execution
    assert result.accounting is None
    assert result.state == state


def test_rejects_long_stop_above_entry_price() -> None:
    from app.trade_signal import TradeSignal

    controller = build_controller()

    with pytest.raises(
        ValueError,
        match="LONG stop_loss must be below entry price",
    ):
        controller.process_signal(
            symbol="ETHUSDT",
            signal=TradeSignal(
                action=Signal.BUY,
                stop_loss=2000.0,
            ),
            entry_quantity=Decimal("0.01"),
            price=Decimal("1950"),
        )
