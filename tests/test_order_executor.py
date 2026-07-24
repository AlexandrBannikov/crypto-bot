import pytest

from app.engine import Candle
from app.order_executor import (
    DryRunOrderExecutor,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrderExecutor,
)
from app.paper_session import PaperTradingSession
from app.trade_signal import TradeSignal
from app.trading_types import (
    PositionSide,
    TradeAction,
)


def test_order_request_normalizes_symbol() -> None:
    request = OrderRequest(
        symbol=" ethusdt ",
        side=OrderSide.BUY,
        quantity=1,
    )

    assert request.symbol == "ETHUSDT"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "symbol": "",
                "side": OrderSide.BUY,
                "quantity": 1,
            },
            "symbol",
        ),
        (
            {
                "symbol": "ETHUSDT",
                "side": OrderSide.BUY,
                "quantity": 0,
            },
            "quantity",
        ),
        (
            {
                "symbol": "ETHUSDT",
                "side": OrderSide.BUY,
                "quantity": 1,
                "order_type": OrderType.LIMIT,
            },
            "price is required",
        ),
        (
            {
                "symbol": "ETHUSDT",
                "side": OrderSide.BUY,
                "quantity": 1,
                "price": 0,
            },
            "price",
        ),
        (
            {
                "symbol": "ETHUSDT",
                "side": OrderSide.BUY,
                "quantity": 1,
                "stop_loss": 0,
            },
            "stop_loss",
        ),
    ],
)
def test_order_request_rejects_invalid_values(
    kwargs,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        OrderRequest(**kwargs)


@pytest.mark.parametrize(
    ("action", "side", "reduce_only"),
    [
        (
            TradeAction.OPEN_LONG,
            OrderSide.BUY,
            False,
        ),
        (
            TradeAction.CLOSE_LONG,
            OrderSide.SELL,
            True,
        ),
        (
            TradeAction.OPEN_SHORT,
            OrderSide.SELL,
            False,
        ),
        (
            TradeAction.CLOSE_SHORT,
            OrderSide.BUY,
            True,
        ),
    ],
)
def test_order_request_from_trade_action(
    action: TradeAction,
    side: OrderSide,
    reduce_only: bool,
) -> None:
    request = OrderRequest.from_trade_action(
        symbol="ETHUSDT",
        action=action,
        quantity=0.5,
        stop_loss=95,
    )

    assert request.side == side
    assert request.reduce_only is reduce_only
    assert request.quantity == 0.5
    assert request.stop_loss == 95


def test_order_request_rejects_hold_action() -> None:
    with pytest.raises(ValueError, match="HOLD"):
        OrderRequest.from_trade_action(
            symbol="ETHUSDT",
            action=TradeAction.HOLD,
            quantity=1,
        )


def test_order_result_requires_order_id_for_accept() -> None:
    request = OrderRequest(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        quantity=1,
    )

    with pytest.raises(ValueError, match="order_id"):
        OrderResult(
            request=request,
            status=OrderStatus.ACCEPTED,
        )


def test_order_result_requires_message_for_reject() -> None:
    request = OrderRequest(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        quantity=1,
    )

    with pytest.raises(ValueError, match="message"):
        OrderResult(
            request=request,
            status=OrderStatus.REJECTED,
        )


def test_dry_run_executor_records_order() -> None:
    executor = DryRunOrderExecutor()
    request = OrderRequest.from_trade_action(
        symbol="ETHUSDT",
        action=TradeAction.OPEN_LONG,
        quantity=0.5,
    )

    result = executor.submit_order(request)

    assert result.status == OrderStatus.ACCEPTED
    assert result.order_id == "dry-run-1"
    assert "not sent" in result.message
    assert executor.orders == (request,)
    assert executor.results == (result,)


def test_dry_run_executor_generates_stable_order_ids() -> None:
    executor = DryRunOrderExecutor()
    first = OrderRequest(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        quantity=1,
    )
    second = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        quantity=2,
    )

    first_result = executor.submit_order(first)
    second_result = executor.submit_order(second)

    assert first_result.order_id == "dry-run-1"
    assert second_result.order_id == "dry-run-2"


def test_paper_executor_queues_signal() -> None:
    session = PaperTradingSession(
        commission_rate=0,
    )
    executor = PaperOrderExecutor(session)

    executor.queue_signal(
        signal=TradeSignal(
            action=TradeAction.OPEN_LONG,
        ),
        reference_price=100,
    )

    assert (
        session.snapshot.pending_action
        == TradeAction.OPEN_LONG
    )
    assert (
        session.snapshot.pending_reference_price
        == 100
    )


def test_paper_executor_executes_pending_open() -> None:
    session = PaperTradingSession(
        commission_rate=0,
    )
    executor = PaperOrderExecutor(session)

    executor.queue_signal(
        signal=TradeSignal(
            action=TradeAction.OPEN_LONG,
        ),
        reference_price=100,
    )

    trade = executor.execute_pending_action(
        Candle(2, 110, 111, 109, 110, 1)
    )

    position = session.snapshot.position

    assert trade is None
    assert position is not None
    assert position.side == PositionSide.LONG
    assert position.entry_timestamp == 2
    assert position.entry_price == 110


def test_paper_executor_processes_stop() -> None:
    session = PaperTradingSession(
        commission_rate=0,
    )
    executor = PaperOrderExecutor(session)

    session.open_position(
        side=PositionSide.LONG,
        candle=Candle(1, 100, 101, 99, 100, 1),
        stop_loss=95,
        risk_reference_price=100,
    )

    trade = executor.process_closed_candle(
        Candle(2, 100, 105, 94, 102, 1)
    )

    assert trade is not None
    assert trade.exit_price == 95
    assert session.snapshot.position is None
