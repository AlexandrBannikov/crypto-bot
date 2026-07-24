from dataclasses import dataclass
from pathlib import Path

from app.engine import Strategy
from app.market_data import MarketDataFeed
from app.paper_engine import PaperTradingEngine
from app.paper_session import PaperTradingSession
from app.paper_state import (
    PaperSessionState,
    PaperStateStore,
)
from app.paper_trader import (
    PaperTrader,
    PaperTraderConfig,
)
from app.risk import RiskConfig


@dataclass(frozen=True, slots=True)
class TradingEngineConfig:
    state_file: Path = Path(
        "state/paper_state.json"
    )
    log_file: Path = Path(
        "logs/paper_trades.csv"
    )
    initial_balance: float = 1000.0
    commission_rate: float = 0.001
    risk_config: RiskConfig | None = None

    def __post_init__(self) -> None:
        if self.initial_balance <= 0:
            raise ValueError(
                "initial_balance must be greater than zero"
            )

        if not 0 <= self.commission_rate < 1:
            raise ValueError(
                "commission_rate must be greater than or equal "
                "to zero and less than one"
            )


@dataclass(frozen=True, slots=True)
class TradingRunResult:
    received_candles: int
    processed_candles: int
    new_trades: int
    total_recorded_trades: int
    last_candle_timestamp: int | None
    virtual_balance: float
    has_open_position: bool


class TradingEngine:
    def __init__(
        self,
        *,
        feed: MarketDataFeed,
        strategy: Strategy,
        config: TradingEngineConfig | None = None,
    ) -> None:
        self.feed = feed
        self.strategy = strategy
        self.config = config or TradingEngineConfig()

    def run_once(self) -> TradingRunResult:
        candles = tuple(self.feed.get_candles())

        if not candles:
            raise ValueError(
                "market data feed returned no candles"
            )

        state_store = PaperStateStore(
            self.config.state_file
        )
        previous_state = state_store.load(
            default_balance=(
                self.config.initial_balance
            ),
        )

        snapshot = previous_state.session_snapshot

        if snapshot is None:
            raise ValueError(
                "paper state has no session snapshot"
            )

        previous_timestamp = (
            snapshot.last_candle_timestamp
        )

        processed_candles = sum(
            1
            for candle in candles
            if (
                previous_timestamp is None
                or candle.timestamp > previous_timestamp
            )
        )

        session = PaperTradingSession(
            snapshot=snapshot,
            commission_rate=(
                self.config.commission_rate
            ),
            risk_config=self.config.risk_config,
        )

        paper_engine = PaperTradingEngine(
            session=session,
            strategy=self.strategy,
        )

        trades = paper_engine.run_iteration(candles)

        trader = PaperTrader(
            PaperTraderConfig(
                log_file=self.config.log_file,
            )
        )

        new_trades = trader.record_trades(trades)
        total_recorded = trader.count_recorded_trades()

        updated_snapshot = session.snapshot

        state_store.save(
            PaperSessionState(
                last_candle_timestamp=(
                    updated_snapshot
                    .last_candle_timestamp
                ),
                virtual_balance=(
                    updated_snapshot.balance
                ),
                recorded_trades=total_recorded,
                session_snapshot=updated_snapshot,
            )
        )

        return TradingRunResult(
            received_candles=len(candles),
            processed_candles=processed_candles,
            new_trades=new_trades,
            total_recorded_trades=total_recorded,
            last_candle_timestamp=(
                updated_snapshot.last_candle_timestamp
            ),
            virtual_balance=updated_snapshot.balance,
            has_open_position=(
                updated_snapshot.position is not None
            ),
        )
