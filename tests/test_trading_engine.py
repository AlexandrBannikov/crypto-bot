from pathlib import Path

import pytest

from app.engine import Candle
from app.paper_state import (
    PaperSessionState,
    PaperStateStore,
)
from app.trading_engine import (
    TradingEngine,
    TradingEngineConfig,
)
from app.trading_types import TradeAction


class StaticFeed:
    def __init__(
        self,
        candles: tuple[Candle, ...],
    ) -> None:
        self.candles = candles

    def get_candles(self) -> tuple[Candle, ...]:
        return self.candles


class BuyThenSellStrategy:
    def generate_signal(self, candles, index):
        if index == 0:
            return TradeAction.OPEN_LONG

        if index == 1:
            return TradeAction.CLOSE_LONG

        return TradeAction.HOLD


def make_candles() -> tuple[Candle, ...]:
    return (
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 110, 111, 109, 110, 1),
        Candle(3, 120, 121, 119, 120, 1),
    )


def make_config(
    tmp_path: Path,
) -> TradingEngineConfig:
    return TradingEngineConfig(
        state_file=tmp_path / "state.json",
        log_file=tmp_path / "trades.csv",
        initial_balance=1000,
        commission_rate=0,
    )


def test_trading_engine_runs_cycle_and_saves_state(
    tmp_path: Path,
) -> None:
    engine = TradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=BuyThenSellStrategy(),
        config=make_config(tmp_path),
    )

    result = engine.run_once()

    assert result.received_candles == 3
    assert result.processed_candles == 3
    assert result.new_trades == 1
    assert result.total_recorded_trades == 1
    assert result.last_candle_timestamp == 3
    assert result.has_open_position is False
    assert result.virtual_balance == pytest.approx(
        1090.909090909091
    )

    saved = PaperStateStore(
        tmp_path / "state.json"
    ).load()

    assert (
        saved.session_snapshot.last_candle_timestamp
        == 3
    )
    assert saved.session_snapshot.position is None


def test_trading_engine_ignores_duplicate_cycle(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    engine = TradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=BuyThenSellStrategy(),
        config=config,
    )

    first = engine.run_once()
    second = engine.run_once()

    assert first.new_trades == 1
    assert second.processed_candles == 0
    assert second.new_trades == 0
    assert second.total_recorded_trades == 1


def test_trading_engine_rejects_empty_feed(
    tmp_path: Path,
) -> None:
    engine = TradingEngine(
        feed=StaticFeed(()),
        strategy=BuyThenSellStrategy(),
        config=make_config(tmp_path),
    )

    with pytest.raises(
        ValueError,
        match="market data feed returned no candles",
    ):
        engine.run_once()


def test_trading_engine_uses_existing_state(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)

    PaperStateStore(config.state_file).save(
        PaperSessionState(
            last_candle_timestamp=2,
            virtual_balance=1000,
        )
    )

    engine = TradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=BuyThenSellStrategy(),
        config=config,
    )

    result = engine.run_once()

    assert result.processed_candles == 1
    assert result.last_candle_timestamp == 3
