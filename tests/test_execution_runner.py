from decimal import Decimal

import pytest

from app.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
)
from app.execution_runner import (
    ExecutionCommand,
    ExecutionRunner,
    ExecutionRunnerError,
)
from app.paper_executor import PaperExecutor
from app.trading_types import (
    PositionSide,
    TradeAction,
)


class FakeLiveExecutor:
    def __init__(self) -> None:
        self.open_calls = 0
        self.close_calls = 0

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.LIVE

    def open_position(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        self.open_calls += 1
        raise AssertionError(
            "live executor must not be called"
        )

    def close_position(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        self.close_calls += 1
        raise AssertionError(
            "live executor must not be called"
        )

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> ExecutionResult:
        raise NotImplementedError

    def get_order_status(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> ExecutionResult:
        raise NotImplementedError


def build_command(
    action: TradeAction,
) -> ExecutionCommand:
    return ExecutionCommand(
        symbol="ethusdt",
        action=action,
        quantity=Decimal("0.05"),
        price=Decimal("2500"),
        client_order_id="runner-test-1",
    )


def test_execution_command_normalizes_symbol() -> None:
    command = build_command(
        TradeAction.OPEN_LONG
    )

    assert command.symbol == "ETHUSDT"


def test_runner_returns_none_for_hold() -> None:
    runner = ExecutionRunner(PaperExecutor())

    result = runner.execute(
        build_command(TradeAction.HOLD)
    )

    assert result is None


def test_runner_opens_long_position() -> None:
    runner = ExecutionRunner(PaperExecutor())

    result = runner.execute(
        build_command(TradeAction.OPEN_LONG)
    )

    assert result is not None
    assert result.mode == ExecutionMode.PAPER
    assert result.side == PositionSide.LONG
    assert result.executed_quantity == Decimal("0.05")
    assert result.average_price == Decimal("2500")


def test_runner_closes_long_position() -> None:
    runner = ExecutionRunner(PaperExecutor())

    result = runner.execute(
        build_command(TradeAction.CLOSE_LONG)
    )

    assert result is not None
    assert result.mode == ExecutionMode.PAPER
    assert result.side == PositionSide.LONG
    assert result.executed_quantity == Decimal("0.05")


@pytest.mark.parametrize(
    "action",
    [
        TradeAction.OPEN_SHORT,
        TradeAction.CLOSE_SHORT,
    ],
)
def test_runner_rejects_short_actions(
    action: TradeAction,
) -> None:
    runner = ExecutionRunner(PaperExecutor())

    with pytest.raises(
        ExecutionRunnerError,
        match="SHORT execution is not supported",
    ):
        runner.execute(build_command(action))


def test_runner_blocks_live_execution_by_default() -> None:
    executor = FakeLiveExecutor()
    runner = ExecutionRunner(executor)

    with pytest.raises(
        ExecutionRunnerError,
        match="LIVE execution is blocked",
    ):
        runner.execute(
            build_command(TradeAction.OPEN_LONG)
        )

    assert executor.open_calls == 0
    assert executor.close_calls == 0


@pytest.mark.parametrize(
    ("quantity", "price"),
    [
        (Decimal("0"), Decimal("2500")),
        (Decimal("-1"), Decimal("2500")),
        (Decimal("0.05"), Decimal("0")),
        (Decimal("0.05"), Decimal("-2500")),
    ],
)
def test_execution_command_rejects_invalid_values(
    quantity: Decimal,
    price: Decimal,
) -> None:
    with pytest.raises(ValueError):
        ExecutionCommand(
            symbol="ETHUSDT",
            action=TradeAction.OPEN_LONG,
            quantity=quantity,
            price=price,
        )
