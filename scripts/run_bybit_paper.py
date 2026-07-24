from dataclasses import dataclass
from pathlib import Path

from app.bybit_market_data import (
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.ema_cross_stop_strategy import (
    EMACrossStopStrategy,
)
from app.engine import Strategy
from app.market_data import MarketDataFeed
from app.trading_engine import (
    TradingEngine,
    TradingEngineConfig,
)
from app.risk import RiskConfig


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
) -> PaperRunResult:
    result = TradingEngine(
        feed=feed,
        strategy=strategy,
        config=TradingEngineConfig(
            state_file=Path(state_file),
            log_file=Path(log_file),
            initial_balance=initial_balance,
            commission_rate=commission_rate,
            risk_config=risk_config,
        ),
    ).run_once()

    return PaperRunResult(
        received_candles=result.received_candles,
        processed_candles=result.processed_candles,
        new_trades=result.new_trades,
        total_recorded_trades=(
            result.total_recorded_trades
        ),
        last_candle_timestamp=(
            result.last_candle_timestamp
        ),
        virtual_balance=result.virtual_balance,
        has_open_position=result.has_open_position,
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
