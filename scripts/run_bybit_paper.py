from pathlib import Path

from app.bybit_market_data import (
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.ema_cross_stop_strategy import (
    EMACrossStopStrategy,
)
from app.engine import BacktestEngine
from app.paper_state import (
    PaperSessionState,
    PaperStateStore,
)
from app.paper_trader import (
    PaperTrader,
    PaperTraderConfig,
)
from app.risk import RiskConfig


INITIAL_BALANCE = 1000.0
LOG_FILE = Path(
    "logs/bybit_paper_trades.csv"
)
STATE_FILE = Path(
    "state/bybit_paper_state.json"
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

    candles = feed.get_candles()
    latest_timestamp = candles[-1].timestamp

    state_store = PaperStateStore(
        STATE_FILE
    )
    previous_state = state_store.load(
        default_balance=INITIAL_BALANCE,
    )

    strategy = EMACrossStopStrategy(
        short_period=20,
        long_period=50,
        stop_loss_percent=2.0,
    )

    engine = BacktestEngine(
        initial_balance=INITIAL_BALANCE,
        commission_rate=0.001,
        risk_config=RiskConfig(
            risk_per_trade=0.01,
            max_position_fraction=1.0,
            leverage=1.0,
        ),
    )

    trader = PaperTrader(
        PaperTraderConfig(
            log_file=LOG_FILE,
        )
    )

    result = engine.run(
        candles,
        strategy,
    )

    new_trades = trader.record_trades(
        result.trades
    )

    total_recorded = (
        trader.count_recorded_trades()
    )

    state_store.save(
        PaperSessionState(
            last_candle_timestamp=latest_timestamp,
            virtual_balance=result.final_balance,
            recorded_trades=total_recorded,
        )
    )

    print("Свечей получено:", len(candles))
    print("Последняя свеча:", latest_timestamp)
    print("Сделок в расчёте:", len(result.trades))
    print("Новых записей:", new_trades)
    print(
        "Конечный баланс:",
        round(result.final_balance, 2),
    )
    print(
        "Доходность:",
        round(result.total_return_percent, 2),
        "%",
    )
    print(
        "Максимальная просадка:",
        round(result.max_drawdown_percent, 2),
        "%",
    )

    if (
        previous_state.last_candle_timestamp
        == latest_timestamp
    ):
        print(
            "Новой закрытой свечи с прошлого "
            "запуска нет."
        )


if __name__ == "__main__":
    main()
