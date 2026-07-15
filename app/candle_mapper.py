import pandas as pd

from app.engine import Candle


REQUIRED_COLUMNS = {
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def dataframe_to_candles(
    data: pd.DataFrame,
) -> list[Candle]:
    missing_columns = REQUIRED_COLUMNS - set(data.columns)

    if missing_columns:
        raise ValueError(
            "DataFrame не содержит обязательные колонки: "
            + ", ".join(sorted(missing_columns))
        )

    if data.empty:
        return []

    candles: list[Candle] = []

    for row in data.itertuples(index=False):
        timestamp = pd.Timestamp(row.datetime)

        candles.append(
            Candle(
                timestamp=int(timestamp.timestamp()),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
        )

    return candles

