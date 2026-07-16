import pytest

from app.engine import Candle
from app.risk import RiskConfig
from app.paper_session import (
    PaperPosition,
    PaperSessionSnapshot,
    PaperTradingSession,
)
from app.trading_types import (
    ExitReason,
    PositionSide,
    TradeAction,
)


def make_candle(
    timestamp: int,
) -> Candle:
    return Candle(
        timestamp=timestamp,
        open=100,
        high=110,
        low=90,
        close=105,
        volume=1,
    )


def test_default_session_snapshot() -> None:
    session = PaperTradingSession()

    assert session.snapshot.balance == pytest.approx(
        1000
    )
    assert session.snapshot.position is None
    assert (
        session.snapshot.pending_action
        == TradeAction.HOLD
    )
    assert (
        session.snapshot.last_candle_timestamp
        is None
    )


def test_accepts_new_closed_candle() -> None:
    session = PaperTradingSession()

    assert session.accept_closed_candle(
        make_candle(100)
    ) is True

    assert (
        session.snapshot.last_candle_timestamp
        == 100
    )


def test_ignores_duplicate_candle() -> None:
    session = PaperTradingSession()

    assert session.accept_closed_candle(
        make_candle(100)
    ) is True

    assert session.accept_closed_candle(
        make_candle(100)
    ) is False


def test_ignores_older_candle() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            last_candle_timestamp=200,
        )
    )

    assert session.accept_closed_candle(
        make_candle(100)
    ) is False

    assert (
        session.snapshot.last_candle_timestamp
        == 200
    )


def test_preserves_existing_position() -> None:
    position = PaperPosition(
        side=PositionSide.LONG,
        entry_timestamp=10,
        entry_price=100,
        quantity=2,
        entry_fee=0.2,
        entry_cost=200.2,
        initial_stop_loss=95,
        active_stop_loss=95,
        stop_reason=ExitReason.STOP_LOSS,
        trailing_stop_percent=0.05,
    )

    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=799.8,
            position=position,
        )
    )

    session.accept_closed_candle(
        make_candle(100)
    )

    assert session.snapshot.position == position
    assert session.snapshot.balance == pytest.approx(
        799.8
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entry_timestamp", -1),
        ("entry_price", 0),
        ("quantity", 0),
        ("entry_fee", -1),
        ("entry_cost", 0),
    ],
)
def test_rejects_invalid_position_values(
    field: str,
    value,
) -> None:
    kwargs = {
        "side": PositionSide.LONG,
        "entry_timestamp": 1,
        "entry_price": 100,
        "quantity": 1,
        "entry_fee": 0,
        "entry_cost": 100,
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        PaperPosition(**kwargs)


def test_rejects_long_stop_above_entry() -> None:
    with pytest.raises(
        ValueError,
        match="LONG stop_loss",
    ):
        PaperPosition(
            side=PositionSide.LONG,
            entry_timestamp=1,
            entry_price=100,
            quantity=1,
            entry_fee=0,
            entry_cost=100,
            initial_stop_loss=105,
            active_stop_loss=105,
            stop_reason=ExitReason.STOP_LOSS,
        )


def test_rejects_short_stop_below_entry() -> None:
    with pytest.raises(
        ValueError,
        match="SHORT stop_loss",
    ):
        PaperPosition(
            side=PositionSide.SHORT,
            entry_timestamp=1,
            entry_price=100,
            quantity=1,
            entry_fee=0,
            entry_cost=100,
            initial_stop_loss=95,
        active_stop_loss=95,
            stop_reason=ExitReason.STOP_LOSS,
        )


def test_pending_open_requires_reference_price() -> None:
    with pytest.raises(
        ValueError,
        match="pending_reference_price",
    ):
        PaperSessionSnapshot(
            pending_action=TradeAction.OPEN_LONG,
        )


def test_pending_stop_requires_open_action() -> None:
    with pytest.raises(
        ValueError,
        match="pending stop",
    ):
        PaperSessionSnapshot(
            pending_action=TradeAction.HOLD,
            pending_stop_loss=95,
        )


def test_rejects_invalid_candle() -> None:
    session = PaperTradingSession()

    with pytest.raises(
        ValueError,
        match="prices",
    ):
        session.accept_closed_candle(
            Candle(
                timestamp=1,
                open=0,
                high=1,
                low=0,
                close=1,
                volume=1,
            )
        )


def make_long_position(
    *,
    stop_loss: float = 95,
    trailing_stop_percent: float | None = None,
) -> PaperPosition:
    return PaperPosition(
        side=PositionSide.LONG,
        entry_timestamp=1,
        entry_price=100,
        quantity=2,
        entry_fee=0,
        entry_cost=200,
        initial_stop_loss=95,
        active_stop_loss=stop_loss,
        stop_reason=ExitReason.STOP_LOSS,
        trailing_stop_percent=trailing_stop_percent,
    )


def test_session_detects_position_stop() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(),
        )
    )

    assert session.position_stop_was_hit(
        Candle(2, 100, 105, 94, 102, 1)
    )


def test_session_returns_stop_exit_price_after_gap() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(),
        )
    )

    exit_price = session.position_stop_exit_price(
        Candle(2, 90, 94, 88, 92, 1)
    )

    assert exit_price == pytest.approx(90)


def test_session_updates_long_trailing_stop() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(
                trailing_stop_percent=0.05,
            ),
        )
    )

    changed = session.update_trailing_stop(
        close_price=110,
    )

    assert changed is True
    assert (
        session.snapshot.position.active_stop_loss
        == pytest.approx(104.5)
    )
    assert (
        session.snapshot.position.stop_reason
        == ExitReason.TRAILING_STOP
    )


def test_session_does_not_move_trailing_stop_back() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(
                stop_loss=105,
                trailing_stop_percent=0.05,
            ),
        )
    )

    changed = session.update_trailing_stop(
        close_price=100,
    )

    assert changed is False
    assert (
        session.snapshot.position.active_stop_loss
        == pytest.approx(105)
    )


def test_session_without_position_has_no_stop() -> None:
    session = PaperTradingSession()

    assert not session.position_stop_was_hit(
        make_candle(1)
    )


def test_closes_profitable_long_position() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(),
        ),
        commission_rate=0,
    )

    trade = session.close_position(
        exit_timestamp=2,
        exit_price=110,
        exit_reason=ExitReason.SIGNAL,
    )

    assert trade.side == PositionSide.LONG
    assert trade.profit == pytest.approx(20)
    assert trade.exit_fee == pytest.approx(0)
    assert trade.exit_reason == ExitReason.SIGNAL
    assert session.snapshot.balance == pytest.approx(
        1020
    )
    assert session.snapshot.position is None


def test_closes_losing_long_position() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(),
        ),
        commission_rate=0,
    )

    trade = session.close_position(
        exit_timestamp=2,
        exit_price=95,
        exit_reason=ExitReason.STOP_LOSS,
    )

    assert trade.profit == pytest.approx(-10)
    assert session.snapshot.balance == pytest.approx(
        990
    )


def test_closes_profitable_short_position() -> None:
    position = PaperPosition(
        side=PositionSide.SHORT,
        entry_timestamp=1,
        entry_price=100,
        quantity=2,
        entry_fee=0,
        entry_cost=200,
        initial_stop_loss=105,
        active_stop_loss=105,
        stop_reason=ExitReason.STOP_LOSS,
    )

    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=position,
        ),
        commission_rate=0,
    )

    trade = session.close_position(
        exit_timestamp=2,
        exit_price=90,
        exit_reason=ExitReason.SIGNAL,
    )

    assert trade.side == PositionSide.SHORT
    assert trade.profit == pytest.approx(20)
    assert session.snapshot.balance == pytest.approx(
        1020
    )


def test_close_position_accounts_for_commission() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=799.8,
            position=PaperPosition(
                side=PositionSide.LONG,
                entry_timestamp=1,
                entry_price=100,
                quantity=2,
                entry_fee=0.2,
                entry_cost=200.2,
                initial_stop_loss=95,
                active_stop_loss=95,
                stop_reason=ExitReason.STOP_LOSS,
            ),
        ),
        commission_rate=0.001,
    )

    trade = session.close_position(
        exit_timestamp=2,
        exit_price=110,
        exit_reason=ExitReason.SIGNAL,
    )

    assert trade.exit_fee == pytest.approx(0.22)
    assert trade.profit == pytest.approx(19.58)
    assert session.snapshot.balance == pytest.approx(
        1019.58
    )


def test_closes_position_at_initial_stop() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(),
        ),
        commission_rate=0,
    )

    trade = session.close_position_at_stop(
        Candle(2, 100, 104, 94, 102, 1)
    )

    assert trade.exit_price == pytest.approx(95)
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.profit == pytest.approx(-10)
    assert session.snapshot.position is None


def test_closes_position_at_trailing_stop() -> None:
    position = PaperPosition(
        side=PositionSide.LONG,
        entry_timestamp=1,
        entry_price=100,
        quantity=2,
        entry_fee=0,
        entry_cost=200,
        initial_stop_loss=95,
        active_stop_loss=104.5,
        stop_reason=ExitReason.TRAILING_STOP,
        trailing_stop_percent=0.05,
    )

    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=position,
        ),
        commission_rate=0,
    )

    trade = session.close_position_at_stop(
        Candle(2, 108, 109, 104, 105, 1)
    )

    assert trade.exit_price == pytest.approx(104.5)
    assert (
        trade.exit_reason
        == ExitReason.TRAILING_STOP
    )
    assert trade.profit == pytest.approx(9)
    assert session.snapshot.balance == pytest.approx(
        1009
    )


def test_close_position_rejects_missing_position() -> None:
    session = PaperTradingSession()

    with pytest.raises(
        ValueError,
        match="no open position",
    ):
        session.close_position(
            exit_timestamp=2,
            exit_price=100,
            exit_reason=ExitReason.SIGNAL,
        )


def test_close_at_stop_rejects_unhit_stop() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(),
        )
    )

    with pytest.raises(
        ValueError,
        match="was not hit",
    ):
        session.close_position_at_stop(
            Candle(2, 100, 105, 96, 102, 1)
        )


@pytest.mark.parametrize(
    "commission_rate",
    [-0.1, 1, 1.1],
)
def test_session_rejects_invalid_commission(
    commission_rate: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="commission_rate",
    ):
        PaperTradingSession(
            commission_rate=commission_rate,
        )


def test_process_closed_candle_ignores_duplicate() -> None:
    session = PaperTradingSession()

    assert session.process_closed_candle(
        make_candle(100)
    ) is None

    assert session.process_closed_candle(
        make_candle(100)
    ) is None

    assert (
        session.snapshot.last_candle_timestamp
        == 100
    )


def test_process_closed_candle_closes_position_at_stop() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(),
        ),
        commission_rate=0,
    )

    trade = session.process_closed_candle(
        Candle(2, 100, 104, 94, 102, 1)
    )

    assert trade is not None
    assert trade.exit_price == pytest.approx(95)
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.profit == pytest.approx(-10)
    assert session.snapshot.position is None
    assert (
        session.snapshot.last_candle_timestamp
        == 2
    )


def test_process_closed_candle_updates_trailing_stop() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(
                trailing_stop_percent=0.05,
            ),
        ),
        commission_rate=0,
    )

    trade = session.process_closed_candle(
        Candle(2, 105, 111, 104, 110, 1)
    )

    assert trade is None
    assert session.snapshot.position is not None
    assert (
        session.snapshot.position.active_stop_loss
        == pytest.approx(104.5)
    )
    assert (
        session.snapshot.position.stop_reason
        == ExitReason.TRAILING_STOP
    )


def test_process_closed_candle_checks_stop_before_trailing() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(
                trailing_stop_percent=0.05,
            ),
        ),
        commission_rate=0,
    )

    trade = session.process_closed_candle(
        Candle(2, 100, 120, 94, 110, 1)
    )

    assert trade is not None
    assert trade.exit_price == pytest.approx(95)
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert session.snapshot.position is None


def test_process_closed_candle_without_position() -> None:
    session = PaperTradingSession()

    trade = session.process_closed_candle(
        make_candle(100)
    )

    assert trade is None
    assert (
        session.snapshot.last_candle_timestamp
        == 100
    )


def test_opens_long_position_without_stop() -> None:
    session = PaperTradingSession(
        commission_rate=0.001,
    )

    position = session.open_position(
        side=PositionSide.LONG,
        candle=Candle(
            timestamp=2,
            open=100,
            high=105,
            low=99,
            close=104,
            volume=1,
        ),
    )

    assert position.side == PositionSide.LONG
    assert position.entry_timestamp == 2
    assert position.entry_price == pytest.approx(100)
    assert position.quantity == pytest.approx(9.99)
    assert position.entry_fee == pytest.approx(1)
    assert position.entry_cost == pytest.approx(1000)
    assert position.active_stop_loss is None
    assert session.snapshot.balance == pytest.approx(0)
    assert session.snapshot.position == position


def test_opens_position_using_risk_manager() -> None:
    session = PaperTradingSession(
        commission_rate=0.001,
        risk_config=RiskConfig(
            risk_per_trade=0.01,
            max_position_fraction=1,
            leverage=2,
        ),
    )

    position = session.open_position(
        side=PositionSide.LONG,
        candle=Candle(
            timestamp=2,
            open=100,
            high=105,
            low=99,
            close=104,
            volume=1,
        ),
        stop_loss=95,
        risk_reference_price=100,
        trailing_stop_percent=0.05,
    )

    assert position.quantity == pytest.approx(2)
    assert position.entry_fee == pytest.approx(0.2)
    assert position.entry_cost == pytest.approx(100.2)
    assert position.initial_stop_loss == pytest.approx(95)
    assert position.active_stop_loss == pytest.approx(95)
    assert position.stop_reason == ExitReason.STOP_LOSS
    assert (
        position.trailing_stop_percent
        == pytest.approx(0.05)
    )
    assert session.snapshot.balance == pytest.approx(
        899.8
    )


def test_rejects_opening_second_position() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            position=make_long_position(),
        )
    )

    with pytest.raises(
        ValueError,
        match="already has an open position",
    ):
        session.open_position(
            side=PositionSide.SHORT,
            candle=make_candle(2),
        )
