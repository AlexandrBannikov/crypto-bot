from decimal import Decimal

from app.execution import ExecutionMode
from app.execution_runner import ExecutionRunner
from app.paper_executor import PaperExecutor
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_runtime import (
    RuntimeRequest,
    TradingRuntime,
)
from app.trading_types import TradeAction


def build_request(
    signal: Signal | TradeSignal | TradeAction,
) -> RuntimeRequest:
    return RuntimeRequest(
        symbol="ethusdt",
        signal=signal,
        quantity=Decimal("0.05"),
        price=Decimal("2500"),
        client_order_id="runtime-test-1",
    )


def test_runtime_executes_buy_signal() -> None:
    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    result = runtime.process_signal(
        build_request(Signal.BUY)
    )

    assert result is not None
    assert result.mode == ExecutionMode.PAPER
    assert result.executed_quantity == Decimal("0.05")
    assert result.average_price == Decimal("2500")


def test_runtime_executes_sell_signal() -> None:
    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    result = runtime.process_signal(
        build_request(Signal.SELL)
    )

    assert result is not None
    assert result.mode == ExecutionMode.PAPER
    assert result.executed_quantity == Decimal("0.05")


def test_runtime_returns_none_for_hold_signal() -> None:
    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    result = runtime.process_signal(
        build_request(Signal.HOLD)
    )

    assert result is None


def test_runtime_accepts_trade_action() -> None:
    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    result = runtime.process_signal(
        build_request(TradeAction.OPEN_LONG)
    )

    assert result is not None
    assert result.mode == ExecutionMode.PAPER


def test_runtime_accepts_trade_signal() -> None:
    runtime = TradingRuntime(
        ExecutionRunner(PaperExecutor())
    )

    result = runtime.process_signal(
        build_request(
            TradeSignal(
                action=TradeAction.OPEN_LONG,
                stop_loss=2400,
            )
        )
    )

    assert result is not None
    assert result.mode == ExecutionMode.PAPER
