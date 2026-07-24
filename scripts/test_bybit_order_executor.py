import os

from app.bybit_account import BybitAccountConfig
from app.bybit_order_executor import (
    BybitOrderExecutor,
    BybitOrderExecutorConfig,
)
from app.order_executor import (
    OrderRequest,
    OrderSide,
)


API_KEY_ENV = "BYBIT_TESTNET_API_KEY"
API_SECRET_ENV = "BYBIT_TESTNET_API_SECRET"
ENABLE_TRADING_ENV = "BYBIT_TESTNET_ENABLE_TRADING"


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

    executor = BybitOrderExecutor(
        BybitOrderExecutorConfig(
            account=BybitAccountConfig(
                api_key=api_key,
                api_secret=api_secret,
                testnet=True,
            ),
            category="linear",
            enable_trading=enable_trading,
        )
    )

    request = OrderRequest(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        quantity=0.001,
    )

    result = executor.submit_order(request)

    print("Bybit testnet order executor check")
    print("Trading enabled:", enable_trading)
    print("Request:", request)
    print("Status:", result.status.value)
    print("Order id:", result.order_id)
    print("Message:", result.message)


if __name__ == "__main__":
    main()
