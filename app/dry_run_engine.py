from dataclasses import dataclass
from pathlib import Path

from app.engine import Strategy
from app.market_data import MarketDataFeed
from app.order_executor import (
    DirectOrderExecutor,
    DryRunOrderExecutor,
    OrderRequest,
    OrderResult,
)
from app.order_planner import OrderPlanner
from app.paper_state import PaperStateStore
from app.risk import RiskConfig


@dataclass(frozen=True, slots=True)
class DryRunTradingConfig:
    symbol: str
    state_file: Path = Path(
        "state/paper_state.json"
    )
    initial_balance: float = 1000.0
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

        if self.initial_balance <= 0:
            raise ValueError(
                "initial_balance must be greater than zero"
            )


@dataclass(frozen=True, slots=True)
class DryRunTradingResult:
    received_candles: int
    processed_candles: int
    planned_order: OrderRequest | None
    order_result: OrderResult | None
    signal_timestamp: int | None
    last_candle_timestamp: int | None
    virtual_balance: float
    has_open_position: bool


class DryRunTradingEngine:
    def __init__(
        self,
        *,
        feed: MarketDataFeed,
        strategy: Strategy,
        config: DryRunTradingConfig,
        executor: DirectOrderExecutor | None = None,
    ) -> None:
        self.feed = feed
        self.strategy = strategy
        self.config = config
        self.executor = (
            executor
            or DryRunOrderExecutor()
        )

    def run_once(self) -> DryRunTradingResult:
        candles = tuple(self.feed.get_candles())

        if not candles:
            raise ValueError(
                "market data feed returned no candles"
            )

        state = PaperStateStore(
            self.config.state_file
        ).load(
            default_balance=(
                self.config.initial_balance
            ),
        )

        snapshot = state.session_snapshot

        if snapshot is None:
            raise ValueError(
                "paper state has no session snapshot"
            )

        previous_timestamp = (
            snapshot.last_candle_timestamp
        )

        new_candles = tuple(
            candle
            for candle in candles
            if (
                previous_timestamp is None
                or candle.timestamp > previous_timestamp
            )
        )

        if not new_candles:
            return DryRunTradingResult(
                received_candles=len(candles),
                processed_candles=0,
                planned_order=None,
                order_result=None,
                signal_timestamp=None,
                last_candle_timestamp=previous_timestamp,
                virtual_balance=snapshot.balance,
                has_open_position=(
                    snapshot.position is not None
                ),
            )

        candle = new_candles[-1]
        index = candles.index(candle)
        signal = self.strategy.generate_signal(
            candles,
            index,
        )

        planner = OrderPlanner(
            symbol=self.config.symbol,
            risk_config=self.config.risk_config,
        )

        planned_order = planner.plan(
            signal=signal,
            balance=snapshot.balance,
            reference_price=candle.close,
            current_position=snapshot.position,
        )

        order_result = (
            None
            if planned_order is None
            else self.executor.submit_order(
                planned_order
            )
        )

        return DryRunTradingResult(
            received_candles=len(candles),
            processed_candles=len(new_candles),
            planned_order=planned_order,
            order_result=order_result,
            signal_timestamp=candle.timestamp,
            last_candle_timestamp=candle.timestamp,
            virtual_balance=snapshot.balance,
            has_open_position=(
                snapshot.position is not None
            ),
        )
