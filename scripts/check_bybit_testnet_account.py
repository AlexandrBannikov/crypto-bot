import os

from app.bybit_account import (
    BybitAccountClient,
    BybitAccountConfig,
)


API_KEY_ENV = "BYBIT_TESTNET_API_KEY"
API_SECRET_ENV = "BYBIT_TESTNET_API_SECRET"


def main() -> None:
    api_key = os.environ.get(API_KEY_ENV, "")
    api_secret = os.environ.get(API_SECRET_ENV, "")

    if not api_key or not api_secret:
        raise SystemExit(
            "Set BYBIT_TESTNET_API_KEY and "
            "BYBIT_TESTNET_API_SECRET first"
        )

    client = BybitAccountClient(
        BybitAccountConfig(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,
        )
    )

    balance = client.get_wallet_balance(
        account_type="UNIFIED",
        coin="USDT",
    )

    positions = client.get_positions(
        category="linear",
        settle_coin="USDT",
    )

    print("Bybit testnet account")
    print("Account type:", balance.account_type)
    print("Total equity:", balance.total_equity)
    print(
        "Total wallet balance:",
        balance.total_wallet_balance,
    )
    print(
        "Total available balance:",
        balance.total_available_balance,
    )

    if balance.coins:
        print("Coins:")

        for coin in balance.coins:
            print(
                " ",
                coin.coin,
                "wallet=",
                coin.wallet_balance,
                "usd=",
                coin.usd_value,
            )

    print("Open positions:", len(positions))

    for position in positions:
        print(
            " ",
            position.symbol,
            position.side.value,
            "size=",
            position.size,
            "avg=",
            position.average_price,
            "upl=",
            position.unrealised_pnl,
        )


if __name__ == "__main__":
    main()
