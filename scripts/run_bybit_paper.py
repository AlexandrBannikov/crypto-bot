from pathlib import Path

from app.bybit_market_data import (
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.ema_cross_stop_strategy import (
    EMACrossStopStrategy,
)
from app.engine import BacktestEngine
from app.paper_trader import (
    PaperTrader,
    PaperTraderConfig,
)
from app.risk import RiskConfig


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

    strategy = EMACrossStopStrategy(
        short_period=20,
        long_period=50,
        stop_loss_percent=2.0,
    )

    engine = BacktestEngine(
        initial_balance=1_000,
        commission_rate=0.001,
        risk_config=RiskConfig(
            risk_per_trade=0.01,
            max_position_fraction=1.0,
            leverage=1.0,
        ),
    )

    trader = PaperTrader(
        PaperTraderConfig(
            log_file=Path(
                "logs/bybit_paper_trades.csv"
            ),
        )
    )

    result = trader.run_session(
        feed=feed,
        strategy=strategy,
        engine=engine,
    )

    print("Свечей получено:", len(candles))
    print("Сделок:", len(result.trades))
    print("Начальный баланс:", result.initial_balance)
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

    if result.trades:
        last_trade = result.trades[-1]

        print(
            "Последняя сделка:",
            last_trade.side.value,
            round(last_trade.entry_price, 2),
            "→",
            round(last_trade.exit_price, 2),
        )
        print(
            "Причина выхода:",
            last_trade.exit_reason.value,
        )


if __name__ == "__main__":
    main()
