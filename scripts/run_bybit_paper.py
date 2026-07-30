from dataclasses import dataclass
from pathlib import Path

from app.bybit_market_data import (
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.config import PaperDiagnosticsConfig
from app.ema_cross_stop_strategy import (
    EMACrossStopStrategy,
)
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
from app.strategy_diagnostics import DiagnosticJournal


INITIAL_BALANCE = 1000.0
COMMISSION_RATE = 0.001

LOG_FILE = Path(
    "logs/bybit_paper_trades.csv"
)
STATE_FILE = Path(
    "state/bybit_paper_state.json"
)


@dataclass(frozen=True, slots=True)
class PaperRunResult:
    received_candles: int
    processed_candles: int
    new_trades: int
    total_recorded_trades: int
    last_candle_timestamp: int | None
    virtual_balance: float
    has_open_position: bool


def run_once(
    *,
    feed: MarketDataFeed,
    strategy: Strategy,
    state_file: str | Path = STATE_FILE,
    log_file: str | Path = LOG_FILE,
    initial_balance: float = INITIAL_BALANCE,
    commission_rate: float = COMMISSION_RATE,
    risk_config: RiskConfig | None = None,
    diagnostics_config: PaperDiagnosticsConfig | None = None,
) -> PaperRunResult:
    candles = tuple(feed.get_candles())

    if not candles:
        raise ValueError(
            "market data feed returned no candles"
        )

    state_store = PaperStateStore(state_file)
    previous_state = state_store.load(
        default_balance=initial_balance,
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
        commission_rate=commission_rate,
        risk_config=risk_config,
    )

    diagnostics = diagnostics_config or PaperDiagnosticsConfig()
    journal = (
        DiagnosticJournal(
            diagnostics.path,
            retention_days=diagnostics.retention_days,
        )
        if diagnostics.enabled
        else None
    )
    if journal is not None:
        journal.prune()

    engine = PaperTradingEngine(
        session=session,
        strategy=strategy,
        diagnostic_journal=journal,
        diagnostic_symbol=diagnostics.symbol,
        diagnostic_timeframe=diagnostics.timeframe,
        diagnostic_session_id=diagnostics.session_id,
        save_all_diagnostics=diagnostics.save_all_candles,
    )

    trades = engine.run_iteration(candles)

    trader = PaperTrader(
        PaperTraderConfig(
            log_file=Path(log_file),
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
            virtual_balance=updated_snapshot.balance,
            recorded_trades=total_recorded,
            session_snapshot=updated_snapshot,
        )
    )

    return PaperRunResult(
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


def main() -> None:
    feed = BybitMarketDataFeed(
        BybitMarketDataConfig(
            symbol="ETHUSDT",
            interval="60",
            category="spot",
            limit=500,
        )
    )

    strategy = EMACrossStopStrategy(
        short_period=20,
        long_period=50,
        stop_loss_percent=2.0,
    )

    result = run_once(
        feed=feed,
        strategy=strategy,
        state_file=STATE_FILE,
        log_file=LOG_FILE,
        initial_balance=INITIAL_BALANCE,
        commission_rate=COMMISSION_RATE,
        risk_config=RiskConfig(
            risk_per_trade=0.01,
            max_position_fraction=1.0,
            leverage=1.0,
        ),
        diagnostics_config=PaperDiagnosticsConfig.from_env(),
    )

    print(
        "Свечей получено:",
        result.received_candles,
    )
    print(
        "Новых свечей обработано:",
        result.processed_candles,
    )
    print(
        "Новых сделок записано:",
        result.new_trades,
    )
    print(
        "Всего сделок в журнале:",
        result.total_recorded_trades,
    )
    print(
        "Последняя свеча:",
        result.last_candle_timestamp,
    )
    print(
        "Свободный виртуальный баланс:",
        round(result.virtual_balance, 2),
    )
    print(
        "Открытая позиция:",
        "да" if result.has_open_position else "нет",
    )

    if result.processed_candles == 0:
        print(
            "Новой закрытой свечи с прошлого "
            "запуска нет."
        )


if __name__ == "__main__":
    main()
