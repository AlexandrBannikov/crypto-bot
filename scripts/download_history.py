from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd


SYMBOL = "ETH/USDT"
TIMEFRAME = "1h"
LIMIT = 1000
OUTPUT_FILE = Path("data/eth_usdt_1h.csv")


def fetch_history() -> pd.DataFrame:
    exchange = ccxt.bybit(
        {
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        }
    )

    candles = exchange.fetch_ohlcv(
        SYMBOL,
        timeframe=TIMEFRAME,
        limit=LIMIT,
    )

    if not candles:
        raise RuntimeError("Bybit не вернул свечи")

    frame = pd.DataFrame(
        candles,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    )

    frame["datetime"] = pd.to_datetime(
        frame["timestamp"],
        unit="ms",
        utc=True,
    )

    return frame[
        [
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    ]


def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    frame = fetch_history()
    frame.to_csv(OUTPUT_FILE, index=False)

    print("=" * 50)
    print("История ETH загружена")
    print(f"Свечей: {len(frame)}")
    print(f"Период: {frame.iloc[0]['datetime']}")
    print(f"До: {frame.iloc[-1]['datetime']}")
    print(f"Последняя цена: {frame.iloc[-1]['close']:.2f} USDT")
    print(f"Файл: {OUTPUT_FILE}")
    print("=" * 50)


if __name__ == "__main__":
    main()

