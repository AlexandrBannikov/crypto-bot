from pathlib import Path

import pytest

from app.bybit_account import (
    BybitPosition,
    WalletBalance,
)
from app.engine import Candle
from app.order_executor import (
    DryRunOrderExecutor,
    OrderSide,
    OrderStatus,
)
from app.paper_state import PaperStateStore
from app.testnet_trading_engine import (
    BybitTestnetTradingConfig,
    BybitTestnetTradingEngine,
)
from app.trading_types import (
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


class StaticAccountClient:
    def __init__(
        self,
        *,
        balance: WalletBalance,
        positions: tuple[BybitPosition, ...] = (),
    ) -> None:
        self.balance = balance
        self.positions = positions

    def get_wallet_balance(
        self,
        *,
        account_type: str = "UNIFIED",
        coin: str | None = None,
    ) -> WalletBalance:
        return self.balance

    def get_positions(
        self,
        *,
        category: str,
        symbol: str | None = None,
        settle_coin: str | None = None,
    ) -> tuple[BybitPosition, ...]:
        return self.positions


class BuyStrategy:
    def generate_signal(self, candles, index):
        return TradeAction.OPEN_LONG


class SellStrategy:
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


def make_balance(
    available: float | None = 1000,
) -> WalletBalance:
    return WalletBalance(
        account_type="UNIFIED",
        total_equity=available,
        total_wallet_balance=available,
        total_available_balance=available,
        coins=(),
    )


def make_config(
    tmp_path: Path,
) -> BybitTestnetTradingConfig:
    return BybitTestnetTradingConfig(
        symbol="ETHUSDT",
        state_file=tmp_path / "testnet_state.json",
    )


def make_engine(
    tmp_path: Path,
    *,
    strategy=None,
    balance: WalletBalance | None = None,
    positions: tuple[BybitPosition, ...] = (),
    executor: DryRunOrderExecutor | None = None,
) -> BybitTestnetTradingEngine:
    return BybitTestnetTradingEngine(
        feed=StaticFeed(make_candles()),
        strategy=strategy or BuyStrategy(),
        account_client=StaticAccountClient(
            balance=balance or make_balance(),
            positions=positions,
        ),
        order_executor=executor or DryRunOrderExecutor(),
        config=make_config(tmp_path),
    )


def test_testnet_engine_submits_planned_order(
    tmp_path: Path,
) -> None:
    executor = DryRunOrderExecutor()
    engine = make_engine(
        tmp_path,
        executor=executor,
    )

    result = engine.run_once()

    assert result.received_candles == 3
    assert result.processed_candles == 3
    assert result.signal_timestamp == 3
    assert result.planned_order is not None
    assert result.planned_order.side == OrderSide.BUY
    assert result.order_result is not None
    assert result.order_result.status == OrderStatus.ACCEPTED
    assert executor.orders == (result.planned_order,)

    saved = PaperStateStore(
        tmp_path / "testnet_state.json"
    ).load()

    assert saved.last_candle_timestamp == 3


def test_testnet_engine_skips_duplicate_cycle(
    tmp_path: Path,
) -> None:
    engine = make_engine(tmp_path)
    first = engine.run_once()
    second = engine.run_once()

    assert first.planned_order is not None
    assert second.processed_candles == 0
    assert second.planned_order is None
    assert second.order_result is None


def test_testnet_engine_uses_existing_position_for_close(
    tmp_path: Path,
) -> None:
    position = BybitPosition(
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        size=2,
        average_price=100,
    )
    engine = make_engine(
        tmp_path,
        strategy=SellStrategy(),
        positions=(position,),
    )

    result = engine.run_once()

    assert result.has_open_position is True
    assert result.planned_order is not None
    assert result.planned_order.side == OrderSide.SELL
    assert result.planned_order.reduce_only is True
    assert result.planned_order.quantity == pytest.approx(2)


def test_testnet_engine_returns_no_order_for_hold(
    tmp_path: Path,
) -> None:
    executor = DryRunOrderExecutor()
    engine = make_engine(
        tmp_path,
        strategy=HoldStrategy(),
        executor=executor,
    )

    result = engine.run_once()

    assert result.planned_order is None
    assert result.order_result is None
    assert executor.orders == ()


def test_testnet_engine_rejects_empty_feed(
    tmp_path: Path,
) -> None:
    engine = BybitTestnetTradingEngine(
        feed=StaticFeed(()),
        strategy=BuyStrategy(),
        account_client=StaticAccountClient(
            balance=make_balance(),
        ),
        order_executor=DryRunOrderExecutor(),
        config=make_config(tmp_path),
    )

    with pytest.raises(
        ValueError,
        match="market data feed returned no candles",
    ):
        engine.run_once()


def test_testnet_engine_rejects_missing_balance(
    tmp_path: Path,
) -> None:
    engine = make_engine(
        tmp_path,
        balance=make_balance(None),
    )

    with pytest.raises(
        ValueError,
        match="available balance",
    ):
        engine.run_once()


def test_testnet_engine_rejects_multiple_symbol_positions(
    tmp_path: Path,
) -> None:
    positions = (
        BybitPosition(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            size=1,
            average_price=100,
        ),
        BybitPosition(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            size=2,
            average_price=100,
        ),
    )
    engine = make_engine(
        tmp_path,
        positions=positions,
    )

    with pytest.raises(
        ValueError,
        match="multiple positions",
    ):
        engine.run_once()
