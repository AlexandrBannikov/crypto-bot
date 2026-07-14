from datetime import datetime, timezone
from pathlib import Path
import time

import ccxt
import pandas as pd


SYMBOL = "ETH/USDT"
TIMEFRAME = "1h"
LIMIT = 1000

START_DATE = "2022-07-01T00:00:00Z"
OUTPUT_FILE = Path("data/eth_usdt_1h_full.csv")


def main() -> None:
    exchange = ccxt.bybit(
        {
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        }
    )

    since = exchange.parse8601(START_DATE)
    now_ms = exchange.milliseconds()

    all_candles: list[list[float]] = []

    print("=" * 60)
    print("Загрузка полной истории ETH/USDT")
    print(f"Начало: {START_DATE}")
    print("=" * 60)

    while since < now_ms:
        candles = exchange.fetch_ohlcv(
            SYMBOL,
            timeframe=TIMEFRAME,
            since=since,
            limit=LIMIT,
        )

        if not candles:
            print("Биржа больше не вернула свечей")
            break

        all_candles.extend(candles)

        last_timestamp = int(candles[-1][0])
        last_datetime = datetime.fromtimestamp(
            last_timestamp / 1000,
            tz=timezone.utc,
        )

        print(
            f"Загружено: {len(all_candles):,} свечей | "
            f"до {last_datetime}"
        )

        next_since = last_timestamp + 1

        if next_since <= since:
            print("Время не продвинулось, загрузка остановлена")
            break

        since = next_since

        # Дополнительная пауза, чтобы не долбить API.
        time.sleep(0.15)

    if not all_candles:
        raise RuntimeError("Не удалось загрузить историю")

    df = pd.DataFrame(
        all_candles,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    )

    df = df.drop_duplicates(subset=["timestamp"])
    df = df.sort_values("timestamp")

    df["datetime"] = pd.to_datetime(
        df["timestamp"],
        unit="ms",
        utc=True,
    )

    # Последняя свеча может быть ещё не закрыта.
    current_hour = pd.Timestamp.now(tz="UTC").floor("h")
    df = df[df["datetime"] < current_hour]

    df = df[
        [
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    ]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    expected_hours = int(
        (
            df.iloc[-1]["datetime"]
            - df.iloc[0]["datetime"]
        ).total_seconds()
        / 3600
    ) + 1

    missing_hours = expected_hours - len(df)

    print()
    print("=" * 60)
    print("Загрузка завершена")
    print(f"Свечей: {len(df):,}")
    print(f"Период: {df.iloc[0]['datetime']}")
    print(f"До: {df.iloc[-1]['datetime']}")
    print(f"Пропущенных часов: {missing_hours}")
    print(f"Файл: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

