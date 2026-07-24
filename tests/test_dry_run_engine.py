from pathlib import Path

import pytest

from app.dry_run_engine import (
    DryRunTradingConfig,
    DryRunTradingEngine,
)
from app.engine import Candle
from app.order_executor import (
    DryRunOrderExecutor,
    OrderSide,
    OrderStatus,
)
from app.paper_session import (
    PaperPosition,
    PaperSessionSnapshot,
)
from app.paper_state import (
    PaperSessionState,
    PaperStateStore,
)
from app.trading_types import (
    ExitReason,
    PositionSide,
    TradeAction,
)


class StaticFeed:
    def __init__(
        self,
        candles: tuple[Candle, ...],
    ) -> None:
        self.candles = candles

    def get_candles(self) -> tuple[Candle, ...]:
        return self.candles


class LatestBuyStrategy:
    def generate_signal(self, candles, index):
        return TradeAction.OPEN_LONG


class LatestSellStrategy:
    def generate_signal(self, candles, index):
        return TradeAction.CLOSE_LONG


class HoldStrategy:
    def generate_signal(self, candles, index):
        return TradeAction.HOLD


def make_candles() -> tuple[Candle, ...]:
    return (
        Candle(1, 100, 101, 99, 100, 1),
        Candle(2, 110, 111, 109, 110, 1),
        Candle(3, 120, 121, 119, 120, 1),
    )


def make_config(
    tmp_path: Path,
) -> DryRunTradingConfig:
    return DryRunTradingConfig(
        symbol="ETHUSDT",
        state_file=tmp_path / "state.json",
        initial_balance=1000,
    )


def save_state(
    tmp_path: Path,
    *,
    last_candle_timestamp: int | None = None,
    balance: float = 1000,
    position: PaperPosition | None = None,
) -> None:
    PaperStateStore(tmp_path / "state.json").save(
        PaperSessionState(
            last_candle_timestamp=last_candle_timestamp,
            virtual_balance=balance,
            session_snapshot=PaperSessionSnapshot(
                balance=balance,
                last_candle_timestamp=(
                    last_candle_timestamp
                ),
                position=position,
            ),
        )
    )


def make_long_position() -> PaperPosition:
    return PaperPosition(
        side=PositionSide.LONG,
        entry_timestamp=1,
        entry_price=100,
        quantity=2,
        entry_fee=0,
        entry_cost=200,
        initial_stop_loss=95,
        active_stop_loss=95,
        stop_reason=ExitReason.STOP_LOSS,
    )


def test_dry_run_plans_latest_new_order(
    tmp_path: Path,
) -> None:
    save_state(
        tmp_path,
        last_candle_timestamp=1,
    )
    executor = DryRunOrderExecutor()
    engine = DryRunTradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=LatestBuyStrategy(),
        config=make_config(tmp_path),
        executor=executor,
    )

    result = engine.run_once()

    assert result.received_candles == 3
    assert result.processed_candles == 2
    assert result.signal_timestamp == 3
    assert result.last_candle_timestamp == 3
    assert result.planned_order is not None
    assert result.planned_order.side == OrderSide.BUY
    assert result.order_result is not None
    assert result.order_result.status == OrderStatus.ACCEPTED
    assert executor.orders == (result.planned_order,)


def test_dry_run_does_not_save_state(
    tmp_path: Path,
) -> None:
    save_state(
        tmp_path,
        last_candle_timestamp=1,
    )
    engine = DryRunTradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=LatestBuyStrategy(),
        config=make_config(tmp_path),
    )

    engine.run_once()

    saved = PaperStateStore(
        tmp_path / "state.json"
    ).load()

    assert saved.last_candle_timestamp == 1
    assert (
        saved.session_snapshot.last_candle_timestamp
        == 1
    )


def test_dry_run_returns_no_order_for_hold(
    tmp_path: Path,
) -> None:
    save_state(tmp_path)
    executor = DryRunOrderExecutor()
    engine = DryRunTradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=HoldStrategy(),
        config=make_config(tmp_path),
        executor=executor,
    )

    result = engine.run_once()

    assert result.planned_order is None
    assert result.order_result is None
    assert executor.orders == ()


def test_dry_run_uses_existing_position_for_close(
    tmp_path: Path,
) -> None:
    save_state(
        tmp_path,
        last_candle_timestamp=2,
        balance=800,
        position=make_long_position(),
    )
    engine = DryRunTradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=LatestSellStrategy(),
        config=make_config(tmp_path),
    )

    result = engine.run_once()

    assert result.virtual_balance == 800
    assert result.has_open_position is True
    assert result.planned_order is not None
    assert result.planned_order.side == OrderSide.SELL
    assert result.planned_order.reduce_only is True
    assert result.planned_order.quantity == pytest.approx(2)


def test_dry_run_returns_no_order_when_no_new_candles(
    tmp_path: Path,
) -> None:
    save_state(
        tmp_path,
        last_candle_timestamp=3,
    )
    engine = DryRunTradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=LatestBuyStrategy(),
        config=make_config(tmp_path),
    )

    result = engine.run_once()

    assert result.processed_candles == 0
    assert result.planned_order is None
    assert result.order_result is None
    assert result.last_candle_timestamp == 3


def test_dry_run_rejects_empty_feed(
    tmp_path: Path,
) -> None:
    engine = DryRunTradingEngine(
        feed=StaticFeed(()),
        strategy=LatestBuyStrategy(),
        config=make_config(tmp_path),
    )

    with pytest.raises(
        ValueError,
        match="market data feed returned no candles",
    ):
        engine.run_once()


def test_dry_run_config_normalizes_symbol(
    tmp_path: Path,
) -> None:
    config = DryRunTradingConfig(
        symbol=" ethusdt ",
        state_file=tmp_path / "state.json",
    )

    assert config.symbol == "ETHUSDT"
