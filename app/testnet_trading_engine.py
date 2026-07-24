from dataclasses import dataclass
from pathlib import Path

from app.bybit_account import (
    BybitAccountClient,
    BybitPosition,
)
from app.engine import Strategy
from app.market_data import MarketDataFeed
from app.order_executor import (
    DirectOrderExecutor,
    OrderRequest,
    OrderResult,
)
from app.order_planner import OrderPlanner
from app.paper_session import PaperPosition
from app.paper_state import (
    PaperSessionState,
    PaperStateStore,
)
from app.risk import RiskConfig
from app.trading_types import ExitReason


@dataclass(frozen=True, slots=True)
class BybitTestnetTradingConfig:
    symbol: str
    state_file: Path = Path(
        "state/bybit_testnet_state.json"
    )
    account_type: str = "UNIFIED"
    category: str = "linear"
    settle_coin: str = "USDT"
    risk_config: RiskConfig | None = None

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        object.__setattr__(
            self,
            "symbol",
            normalized_symbol,
        )

        if not self.account_type.strip():
            raise ValueError(
                "account_type must not be empty"
            )

        if not self.category.strip():
            raise ValueError(
                "category must not be empty"
            )

        normalized_settle_coin = (
            self.settle_coin.strip().upper()
        )

        if not normalized_settle_coin:
            raise ValueError(
                "settle_coin must not be empty"
            )

        object.__setattr__(
            self,
            "settle_coin",
            normalized_settle_coin,
        )


@dataclass(frozen=True, slots=True)
class BybitTestnetTradingResult:
    received_candles: int
    processed_candles: int
    planned_order: OrderRequest | None
    order_result: OrderResult | None
    signal_timestamp: int | None
    last_candle_timestamp: int | None
    available_balance: float
    has_open_position: bool


class BybitTestnetTradingEngine:
    def __init__(
        self,
        *,
        feed: MarketDataFeed,
        strategy: Strategy,
        account_client: BybitAccountClient,
        order_executor: DirectOrderExecutor,
        config: BybitTestnetTradingConfig,
    ) -> None:
        self.feed = feed
        self.strategy = strategy
        self.account_client = account_client
        self.order_executor = order_executor
        self.config = config

    def run_once(self) -> BybitTestnetTradingResult:
        candles = tuple(self.feed.get_candles())

        if not candles:
            raise ValueError(
                "market data feed returned no candles"
            )

        state_store = PaperStateStore(
            self.config.state_file
        )
        state = state_store.load()

        previous_timestamp = (
            state.last_candle_timestamp
        )

        new_candles = tuple(
            candle
            for candle in candles
            if (
                previous_timestamp is None
                or candle.timestamp > previous_timestamp
            )
        )

        wallet = self.account_client.get_wallet_balance(
            account_type=self.config.account_type,
            coin=self.config.settle_coin,
        )
        available_balance = (
            wallet.total_available_balance
            if wallet.total_available_balance is not None
            else wallet.total_wallet_balance
        )

        if available_balance is None:
            raise ValueError(
                "Bybit wallet has no available balance"
            )

        bybit_position = self._find_position()
        planner_position = (
            None
            if bybit_position is None
            else _position_to_planner_position(
                bybit_position
            )
        )

        if not new_candles:
            return BybitTestnetTradingResult(
                received_candles=len(candles),
                processed_candles=0,
                planned_order=None,
                order_result=None,
                signal_timestamp=None,
                last_candle_timestamp=previous_timestamp,
                available_balance=available_balance,
                has_open_position=(
                    planner_position is not None
                ),
            )

        candle = new_candles[-1]
        index = candles.index(candle)
        signal = self.strategy.generate_signal(
            candles,
            index,
        )

        planned_order = OrderPlanner(
            symbol=self.config.symbol,
            risk_config=self.config.risk_config,
        ).plan(
            signal=signal,
            balance=available_balance,
            reference_price=candle.close,
            current_position=planner_position,
        )

        order_result = (
            None
            if planned_order is None
            else self.order_executor.submit_order(
                planned_order
            )
        )

        state_store.save(
            PaperSessionState(
                last_candle_timestamp=(
                    candle.timestamp
                ),
                virtual_balance=available_balance,
            )
        )

        return BybitTestnetTradingResult(
            received_candles=len(candles),
            processed_candles=len(new_candles),
            planned_order=planned_order,
            order_result=order_result,
            signal_timestamp=candle.timestamp,
            last_candle_timestamp=candle.timestamp,
            available_balance=available_balance,
            has_open_position=(
                planner_position is not None
            ),
        )

    def _find_position(
        self,
    ) -> BybitPosition | None:
        positions = self.account_client.get_positions(
            category=self.config.category,
            settle_coin=self.config.settle_coin,
        )

        matching = tuple(
            position
            for position in positions
            if position.symbol == self.config.symbol
        )

        if len(matching) > 1:
            raise ValueError(
                "multiple positions for symbol"
            )

        return matching[0] if matching else None


def _position_to_planner_position(
    position: BybitPosition,
) -> PaperPosition:
    entry_price = (
        position.average_price
        if position.average_price is not None
        else 1.0
    )

    if entry_price <= 0:
        entry_price = 1.0

    entry_cost = position.size * entry_price

    return PaperPosition(
        side=position.side,
        entry_timestamp=0,
        entry_price=entry_price,
        quantity=position.size,
        entry_fee=0,
        entry_cost=entry_cost,
    )


TestnetTradingConfig = BybitTestnetTradingConfig
TestnetTradingResult = BybitTestnetTradingResult
TestnetTradingEngine = BybitTestnetTradingEngine
