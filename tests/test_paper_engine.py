from app.engine import Candle
from app.paper_engine import PaperTradingEngine
from app.paper_session import (
    PaperPosition,
    PaperSessionSnapshot,
    PaperTradingSession,
)
from app.strategies import Signal
from app.trading_types import (
    ExitReason,
    PositionSide,
    TradeAction,
)


class BuyThenSellStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return Signal.BUY

        if index == 1:
            return Signal.SELL

        return Signal.HOLD


class HoldStrategy:
    def generate_signal(self, candles, index):
        return Signal.HOLD


def make_candles() -> tuple[Candle, ...]:
    return (
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 110, 111, 109, 110, 1),
        Candle(3, 120, 121, 119, 120, 1),
    )


def test_processes_only_new_candles() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            last_candle_timestamp=1,
        ),
        commission_rate=0,
    )

    engine = PaperTradingEngine(
        session=session,
        strategy=HoldStrategy(),
    )

    trades = engine.run_iteration(
        make_candles()
    )

    assert trades == ()
    assert (
        session.snapshot.last_candle_timestamp
        == 3
    )


def test_executes_signal_on_next_candle_open() -> None:
    session = PaperTradingSession(
        commission_rate=0,
    )

    engine = PaperTradingEngine(
        session=session,
        strategy=BuyThenSellStrategy(),
    )

    trades = engine.run_iteration(
        make_candles()
    )

    assert len(trades) == 1

    trade = trades[0]

    assert trade.side == PositionSide.LONG
    assert trade.entry_timestamp == 2
    assert trade.entry_price == 110
    assert trade.exit_timestamp == 3
    assert trade.exit_price == 120
    assert session.snapshot.position is None


def test_keeps_pending_signal_after_last_candle() -> None:
    session = PaperTradingSession(
        commission_rate=0,
    )

    engine = PaperTradingEngine(
        session=session,
        strategy=BuyThenSellStrategy(),
    )

    engine.run_iteration(
        make_candles()[:1]
    )

    assert (
        session.snapshot.pending_action
        == TradeAction.OPEN_LONG
    )
    assert (
        session.snapshot.last_candle_timestamp
        == 1
    )


def test_ignores_duplicate_iteration() -> None:
    session = PaperTradingSession(
        commission_rate=0,
    )

    engine = PaperTradingEngine(
        session=session,
        strategy=HoldStrategy(),
    )

    first = engine.run_iteration(
        make_candles()
    )
    second = engine.run_iteration(
        make_candles()
    )

    assert first == ()
    assert second == ()
    assert (
        session.snapshot.last_candle_timestamp
        == 3
    )



def make_long_position(
    *,
    active_stop_loss: float = 95,
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
        active_stop_loss=active_stop_loss,
        stop_reason=ExitReason.STOP_LOSS,
        trailing_stop_percent=trailing_stop_percent,
    )


def test_closes_position_when_stop_is_hit() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            last_candle_timestamp=1,
            position=make_long_position(),
        ),
        commission_rate=0,
    )

    engine = PaperTradingEngine(
        session=session,
        strategy=HoldStrategy(),
    )

    trades = engine.run_iteration(
        (
            Candle(1, 100, 101, 99, 100, 1),
            Candle(2, 100, 105, 94, 102, 1),
        )
    )

    assert len(trades) == 1

    trade = trades[0]

    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.exit_price == 95
    assert session.snapshot.position is None
    assert session.snapshot.balance == 990
    assert (
        session.snapshot.last_candle_timestamp
        == 2
    )


def test_updates_trailing_stop_during_iteration() -> None:
    session = PaperTradingSession(
        PaperSessionSnapshot(
            balance=800,
            last_candle_timestamp=1,
            position=make_long_position(
                trailing_stop_percent=0.05,
            ),
        ),
        commission_rate=0,
    )

    engine = PaperTradingEngine(
        session=session,
        strategy=HoldStrategy(),
    )

    trades = engine.run_iteration(
        (
            Candle(1, 100, 101, 99, 100, 1),
            Candle(2, 100, 111, 99, 110, 1),
        )
    )

    assert trades == ()

    position = session.snapshot.position

    assert position is not None
    assert position.active_stop_loss == 104.5
    assert (
        position.stop_reason
        == ExitReason.TRAILING_STOP
    )
    assert (
        session.snapshot.last_candle_timestamp
        == 2
    )
