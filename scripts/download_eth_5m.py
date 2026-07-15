import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


BASE_URL = "https://data-api.binance.vision"
ENDPOINT = "/api/v3/klines"

SYMBOL = "ETHUSDT"
INTERVAL = "5m"
LIMIT = 1000

START_DATE = "2025-07-01 00:00:00"
OUTPUT_FILE = Path("data/eth_usdt_5m.csv")


def to_milliseconds(value: str) -> int:
    moment = datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S",
    ).replace(tzinfo=timezone.utc)

    return int(moment.timestamp() * 1000)


def format_datetime(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=timezone.utc,
    ).isoformat()


def request_klines(
    session: requests.Session,
    start_time: int,
    end_time: int,
) -> list[list]:
    response = session.get(
        BASE_URL + ENDPOINT,
        params={
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "startTime": start_time,
            "endTime": end_time,
            "limit": LIMIT,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise RuntimeError(
            f"Неожиданный ответ Binance: {data}"
        )

    return data


def main() -> None:
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    start_time = to_milliseconds(
        START_DATE
    )

    # Не загружаем ещё не закрывшуюся свечу.
    now_ms = int(
        datetime.now(
            timezone.utc
        ).timestamp() * 1000
    )

    interval_ms = 5 * 60 * 1000
    end_time = (
        now_ms // interval_ms * interval_ms
    ) - 1

    rows: list[list[str | float]] = []

    with requests.Session() as session:
        while start_time <= end_time:
            klines = request_klines(
                session=session,
                start_time=start_time,
                end_time=end_time,
            )

            if not klines:
                break

            for candle in klines:
                open_time = int(candle[0])

                rows.append(
                    [
                        format_datetime(open_time),
                        float(candle[1]),
                        float(candle[2]),
                        float(candle[3]),
                        float(candle[4]),
                        float(candle[5]),
                    ]
                )

            last_open_time = int(
                klines[-1][0]
            )

            print(
                f"\rЗагружено свечей: {len(rows):,} | "
                f"последняя: "
                f"{format_datetime(last_open_time)}",
                end="",
                flush=True,
            )

            next_start_time = (
                last_open_time + interval_ms
            )

            if next_start_time <= start_time:
                raise RuntimeError(
                    "Время загрузки не продвинулось вперёд"
                )

            start_time = next_start_time

            # Небольшая пауза, чтобы не долбить API.
            time.sleep(0.05)

    print()

    if not rows:
        raise RuntimeError(
            "Binance не вернул ни одной свечи"
        )

    # На всякий случай удаляем возможные дубли.
    unique_rows = {
        row[0]: row
        for row in rows
    }

    sorted_rows = [
        unique_rows[key]
        for key in sorted(unique_rows)
    ]

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            [
                "datetime",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

        writer.writerows(
            sorted_rows
        )

    print(
        f"Файл сохранён: {OUTPUT_FILE}"
    )
    print(
        f"Всего свечей: {len(sorted_rows):,}"
    )
    print(
        f"Начало: {sorted_rows[0][0]}"
    )
    print(
        f"Конец: {sorted_rows[-1][0]}"
    )


if __name__ == "__main__":
    main()
