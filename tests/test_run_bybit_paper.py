from pathlib import Path

from app.engine import Candle
from app.paper_session import PaperSessionSnapshot
from app.paper_state import (
    PaperSessionState,
    PaperStateStore,
)
from app.trading_types import TradeAction
from scripts.run_bybit_paper import run_once


class StaticFeed:
    def __init__(
        self,
        candles: tuple[Candle, ...],
    ) -> None:
        self.candles = candles

    def get_candles(self) -> tuple[Candle, ...]:
        return self.candles


class BuyThenHoldStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeAction.OPEN_LONG

        return TradeAction.HOLD


def test_run_once_processes_new_candles_and_saves_state(
    tmp_path: Path,
) -> None:
    state_file = tmp_path / "state.json"
    log_file = tmp_path / "trades.csv"

    PaperStateStore(state_file).save(
        PaperSessionState(
            last_candle_timestamp=1,
            virtual_balance=1000,
            recorded_trades=0,
            session_snapshot=PaperSessionSnapshot(
                balance=1000,
                last_candle_timestamp=1,
            ),
        )
    )

    result = run_once(
        feed=StaticFeed(
            (
                Candle(1, 100, 101, 99, 100, 1),
                Candle(2, 110, 111, 109, 110, 1),
                Candle(3, 120, 121, 119, 120, 1),
            )
        ),
        strategy=BuyThenHoldStrategy(),
        state_file=state_file,
        log_file=log_file,
        initial_balance=1000,
        commission_rate=0,
    )

    assert result.processed_candles == 2
    assert result.new_trades == 0
    assert result.last_candle_timestamp == 3

    saved = PaperStateStore(state_file).load()

    assert (
        saved.session_snapshot.last_candle_timestamp
        == 3
    )


def test_run_once_executes_saved_pending_open(
    tmp_path: Path,
) -> None:
    state_file = tmp_path / "state.json"
    log_file = tmp_path / "trades.csv"

    PaperStateStore(state_file).save(
        PaperSessionState(
            last_candle_timestamp=1,
            virtual_balance=1000,
            recorded_trades=0,
            session_snapshot=PaperSessionSnapshot(
                balance=1000,
                last_candle_timestamp=1,
                pending_action=TradeAction.OPEN_LONG,
                pending_reference_price=100,
            ),
        )
    )

    result = run_once(
        feed=StaticFeed(
            (
                Candle(1, 100, 101, 99, 100, 1),
                Candle(2, 110, 111, 109, 110, 1),
            )
        ),
        strategy=BuyThenHoldStrategy(),
        state_file=state_file,
        log_file=log_file,
        initial_balance=1000,
        commission_rate=0,
    )

    saved = PaperStateStore(state_file).load()
    position = saved.session_snapshot.position

    assert result.processed_candles == 1
    assert result.has_open_position is True
    assert position is not None
    assert position.entry_timestamp == 2
    assert position.entry_price == 110
    assert (
        saved.session_snapshot.pending_action
        == TradeAction.HOLD
    )
