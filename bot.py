import sys

import ccxt


def get_eth_price() -> float:
    exchange = ccxt.bybit(
        {
            "enableRateLimit": True,
        }
    )

    ticker = exchange.fetch_ticker("ETH/USDT")
    price = ticker.get("last")

    if price is None:
        raise RuntimeError("Bybit не вернул цену ETH")

    return float(price)


def main() -> None:
    print("=" * 50)
    print("Crypto Bot")
    print("Exchange: Bybit")
    print("=" * 50)

    try:
        price = get_eth_price()
        print(f"ETH/USDT: {price:,.2f} USDT")
        print("Подключение к Bybit работает")
    except Exception as error:
        print(f"Ошибка: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()

