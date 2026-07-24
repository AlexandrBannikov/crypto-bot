import os
from pathlib import Path

from app.bybit_account import (
    BybitAccountClient,
    BybitAccountConfig,
)
from app.bybit_market_data import (
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.bybit_order_executor import (
    BybitOrderExecutor,
    BybitOrderExecutorConfig,
)
from app.ema_cross_stop_strategy import (
    EMACrossStopStrategy,
)
from app.risk import RiskConfig
from app.testnet_trading_engine import (
    BybitTestnetTradingConfig,
    BybitTestnetTradingEngine,
)


API_KEY_ENV = "BYBIT_TESTNET_API_KEY"
API_SECRET_ENV = "BYBIT_TESTNET_API_SECRET"
ENABLE_TRADING_ENV = "BYBIT_TESTNET_ENABLE_TRADING"

SYMBOL = "ETHUSDT"
INTERVAL = "60"
CATEGORY = "linear"
SETTLE_COIN = "USDT"
LIMIT = 500

STATE_FILE = Path(
    "state/bybit_testnet_state.json"
)


def main() -> None:
    api_key = os.environ.get(API_KEY_ENV, "")
    api_secret = os.environ.get(API_SECRET_ENV, "")

    if not api_key or not api_secret:
        raise SystemExit(
            "Set BYBIT_TESTNET_API_KEY and "
            "BYBIT_TESTNET_API_SECRET first"
        )

    enable_trading = (
        os.environ.get(
            ENABLE_TRADING_ENV,
            "",
        )
        == "1"
    )

    account_config = BybitAccountConfig(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,
    )

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

    risk_config = RiskConfig(
        risk_per_trade=0.01,
        max_position_fraction=1.0,
        leverage=1.0,
    )

    engine = BybitTestnetTradingEngine(
        feed=feed,
        strategy=strategy,
        account_client=BybitAccountClient(
            account_config
        ),
        order_executor=BybitOrderExecutor(
            BybitOrderExecutorConfig(
                account=account_config,
                category=CATEGORY,
                enable_trading=enable_trading,
            )
        ),
        config=BybitTestnetTradingConfig(
            symbol=SYMBOL,
            state_file=STATE_FILE,
            category=CATEGORY,
            settle_coin=SETTLE_COIN,
            risk_config=risk_config,
        ),
    )

    result = engine.run_once()

    print("Bybit testnet trading cycle")
    print("Trading enabled:", enable_trading)
    print("Свечей получено:", result.received_candles)
    print(
        "Новых свечей обработано:",
        result.processed_candles,
    )
    print("Свеча сигнала:", result.signal_timestamp)
    print(
        "Последняя свеча:",
        result.last_candle_timestamp,
    )
    print(
        "Доступный баланс:",
        round(result.available_balance, 8),
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
        print("Результат:")
        print("  status:", result.order_result.status.value)
        print("  order_id:", result.order_result.order_id)
        print("  message:", result.order_result.message)


if __name__ == "__main__":
    main()
