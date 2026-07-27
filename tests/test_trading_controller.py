from decimal import Decimal

import pytest

from app.execution import ExecutionMode
from app.execution_runner import ExecutionRunner
from app.paper_executor import PaperExecutor
from app.strategies import Signal
from app.trading_controller import (
    TradingController,
    TradingControllerState,
)
from app.trading_runtime import TradingRuntime
from app.trading_types import TradeAction


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
