from app.engine import Candle
from app.paper_engine import PaperTradingEngine
from app.paper_session import (
    PaperSessionSnapshot,
    PaperTradingSession,
)
from app.strategies import Signal
from app.trading_types import (
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
