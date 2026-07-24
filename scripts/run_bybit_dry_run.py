from pathlib import Path

from app.bybit_market_data import (
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.dry_run_engine import (
    DryRunTradingConfig,
    DryRunTradingEngine,
)
from app.ema_cross_stop_strategy import (
    EMACrossStopStrategy,
)
from app.risk import RiskConfig


SYMBOL = "ETHUSDT"
INTERVAL = "60"
CATEGORY = "spot"
LIMIT = 500

INITIAL_BALANCE = 1000.0
STATE_FILE = Path(
    "state/bybit_paper_state.json"
)


def main() -> None:
    feed = BybitMarketDataFeed(
        BybitMarketDataConfig(
            symbol=SYMBOL,
            interval=INTERVAL,
            category=CATEGORY,
            limit=LIMIT,
        )
    )

    strategy = EMACrossStopStrategy(
        short_period=20,
        long_period=50,
        stop_loss_percent=2.0,
    )

    engine = DryRunTradingEngine(
        feed=feed,
        strategy=strategy,
        config=DryRunTradingConfig(
            symbol=SYMBOL,
            state_file=STATE_FILE,
            initial_balance=INITIAL_BALANCE,
            risk_config=RiskConfig(
                risk_per_trade=0.01,
                max_position_fraction=1.0,
                leverage=1.0,
            ),
        ),
    )

    result = engine.run_once()

    print("DRY RUN — ордер не отправляется на биржу")
    print("Свечей получено:", result.received_candles)
    print(
        "Новых свечей найдено:",
        result.processed_candles,
    )
    print(
        "Свеча сигнала:",
        result.signal_timestamp,
    )
    print(
        "Свободный виртуальный баланс:",
        round(result.virtual_balance, 2),
    )
    print(
        "Открытая позиция:",
        "да" if result.has_open_position else "нет",
    )

    if result.planned_order is None:
        print("Планируемая заявка: нет")
        return

    order = result.planned_order
    print("Планируемая заявка:")
    print("  symbol:", order.symbol)
    print("  side:", order.side.value)
    print("  quantity:", order.quantity)
    print("  type:", order.order_type.value)
    print("  reduce_only:", order.reduce_only)
    print("  stop_loss:", order.stop_loss)

    if result.order_result is not None:
        print("Dry-run result:")
        print("  status:", result.order_result.status.value)
        print("  order_id:", result.order_result.order_id)
        print("  message:", result.order_result.message)


if __name__ == "__main__":
    main()
