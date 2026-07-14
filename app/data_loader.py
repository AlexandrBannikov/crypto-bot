from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def load_market_data(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    frame = pd.read_csv(
        path,
        parse_dates=["datetime"],
    )

    missing_columns = REQUIRED_COLUMNS - set(frame.columns)

    if missing_columns:
        raise ValueError(
            "В файле отсутствуют обязательные колонки: "
            + ", ".join(sorted(missing_columns))
        )

    if frame.empty:
        raise ValueError("Файл с рыночными данными пуст")

    frame = frame.sort_values("datetime").reset_index(drop=True)

    if frame["datetime"].isna().any():
        raise ValueError("Обнаружены некорректные значения datetime")

    if frame["datetime"].duplicated().any():
        duplicate_count = int(frame["datetime"].duplicated().sum())

        raise ValueError(
            f"Обнаружены дублирующиеся свечи: {duplicate_count}"
        )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric_columns:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

    if frame[numeric_columns].isna().any().any():
        raise ValueError("Обнаружены некорректные числовые значения")

    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Цена свечи должна быть больше нуля")

    if (frame["volume"] < 0).any():
        raise ValueError("Объём не может быть отрицательным")

    invalid_high = (
        (frame["high"] < frame["open"])
        | (frame["high"] < frame["close"])
        | (frame["high"] < frame["low"])
    )

    invalid_low = (
        (frame["low"] > frame["open"])
        | (frame["low"] > frame["close"])
        | (frame["low"] > frame["high"])
    )

    if invalid_high.any() or invalid_low.any():
        raise ValueError("Обнаружены некорректные OHLC-значения")

    return frame


def find_missing_hours(frame: pd.DataFrame) -> pd.DatetimeIndex:
    if "datetime" not in frame.columns:
        raise ValueError("Нет колонки datetime")

    if frame.empty:
        return pd.DatetimeIndex([])

    start = frame["datetime"].min()
    end = frame["datetime"].max()

    expected = pd.date_range(
        start=start,
        end=end,
        freq="h",
        tz=start.tz,
    )

    actual = pd.DatetimeIndex(frame["datetime"])

    return expected.difference(actual)

