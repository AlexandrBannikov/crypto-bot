import pytest

from app.order_executor import (
    OrderSide,
    OrderType,
)
from app.order_planner import OrderPlanner
from app.paper_session import PaperPosition
from app.risk import RiskConfig
from app.trade_signal import TradeSignal
from app.trading_types import (
    ExitReason,
    PositionSide,
    TradeAction,
)


def make_planner(
    risk_config: RiskConfig | None = None,
) -> OrderPlanner:
    return OrderPlanner(
        symbol="ethusdt",
        risk_config=risk_config,
    )


def make_position(
    side: PositionSide = PositionSide.LONG,
) -> PaperPosition:
    return PaperPosition(
        side=side,
        entry_timestamp=1,
        entry_price=100,
        quantity=2,
        entry_fee=0,
        entry_cost=200,
        initial_stop_loss=95
        if side == PositionSide.LONG
        else 105,
        active_stop_loss=95
        if side == PositionSide.LONG
        else 105,
        stop_reason=ExitReason.STOP_LOSS,
    )


def test_plans_open_long_without_stop() -> None:
    planner = make_planner(
        RiskConfig(
            max_position_fraction=0.5,
            leverage=2,
        )
    )

    request = planner.plan(
        signal=TradeAction.OPEN_LONG,
        balance=1000,
        reference_price=100,
    )

    assert request is not None
    assert request.symbol == "ETHUSDT"
    assert request.side == OrderSide.BUY
    assert request.quantity == pytest.approx(10)
    assert request.reduce_only is False


def test_plans_open_long_with_stop_by_risk() -> None:
    planner = make_planner(
        RiskConfig(
            risk_per_trade=0.01,
            max_position_fraction=1,
            leverage=1,
        )
    )

    request = planner.plan(
        signal=TradeSignal(
            action=TradeAction.OPEN_LONG,
            stop_loss=95,
        ),
        balance=1000,
        reference_price=100,
    )

    assert request is not None
    assert request.side == OrderSide.BUY
    assert request.quantity == pytest.approx(2)
    assert request.stop_loss == 95


def test_plans_open_short_with_stop_by_risk() -> None:
    planner = make_planner(
        RiskConfig(
            risk_per_trade=0.02,
            max_position_fraction=1,
            leverage=1,
        )
    )

    request = planner.plan(
        signal=TradeSignal(
            action=TradeAction.OPEN_SHORT,
            stop_loss=105,
        ),
        balance=1000,
        reference_price=100,
    )

    assert request is not None
    assert request.side == OrderSide.SELL
    assert request.quantity == pytest.approx(4)
    assert request.stop_loss == 105
    assert request.reduce_only is False


def test_plans_close_long_for_long_position() -> None:
    planner = make_planner()

    request = planner.plan(
        signal=TradeAction.CLOSE_LONG,
        balance=0,
        reference_price=100,
        current_position=make_position(
            PositionSide.LONG
        ),
    )

    assert request is not None
    assert request.side == OrderSide.SELL
    assert request.quantity == pytest.approx(2)
    assert request.reduce_only is True


def test_plans_close_short_for_short_position() -> None:
    planner = make_planner()

    request = planner.plan(
        signal=TradeAction.CLOSE_SHORT,
        balance=0,
        reference_price=100,
        current_position=make_position(
            PositionSide.SHORT
        ),
    )

    assert request is not None
    assert request.side == OrderSide.BUY
    assert request.quantity == pytest.approx(2)
    assert request.reduce_only is True


@pytest.mark.parametrize(
    "signal",
    [
        TradeAction.HOLD,
        TradeAction.CLOSE_LONG,
        TradeAction.CLOSE_SHORT,
    ],
)
def test_returns_none_when_no_order_is_needed(
    signal: TradeAction,
) -> None:
    planner = make_planner()

    request = planner.plan(
        signal=signal,
        balance=1000,
        reference_price=100,
    )

    assert request is None


def test_ignores_duplicate_open_when_position_exists() -> None:
    planner = make_planner()

    request = planner.plan(
        signal=TradeAction.OPEN_LONG,
        balance=1000,
        reference_price=100,
        current_position=make_position(
            PositionSide.LONG
        ),
    )

    assert request is None


def test_ignores_close_for_opposite_position() -> None:
    planner = make_planner()

    request = planner.plan(
        signal=TradeAction.CLOSE_SHORT,
        balance=1000,
        reference_price=100,
        current_position=make_position(
            PositionSide.LONG
        ),
    )

    assert request is None


def test_passes_limit_order_price() -> None:
    planner = make_planner()

    request = planner.plan(
        signal=TradeAction.OPEN_LONG,
        balance=1000,
        reference_price=100,
        order_type=OrderType.LIMIT,
        price=99,
    )

    assert request is not None
    assert request.order_type == OrderType.LIMIT
    assert request.price == 99


@pytest.mark.parametrize(
    ("balance", "reference_price", "message"),
    [
        (-1, 100, "balance"),
        (1000, 0, "reference_price"),
    ],
)
def test_rejects_invalid_inputs(
    balance: float,
    reference_price: float,
    message: str,
) -> None:
    planner = make_planner()

    with pytest.raises(ValueError, match=message):
        planner.plan(
            signal=TradeAction.OPEN_LONG,
            balance=balance,
            reference_price=reference_price,
        )


def test_rejects_zero_balance_for_open_order() -> None:
    planner = make_planner()

    with pytest.raises(ValueError, match="balance"):
        planner.plan(
            signal=TradeAction.OPEN_LONG,
            balance=0,
            reference_price=100,
        )
