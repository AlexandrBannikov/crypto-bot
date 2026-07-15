import pandas as pd
import pytest

from app.candle_mapper import dataframe_to_candles


def make_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                [
                    "2026-01-01 00:00:00+00:00",
                    "2026-01-01 01:00:00+00:00",
                ]
            ),
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [95.0, 96.0],
            "close": [102.0, 103.0],
            "volume": [10.0, 11.0],
        }
    )


def test_dataframe_to_candles() -> None:
    candles = dataframe_to_candles(make_data())

    assert len(candles) == 2

    first = candles[0]

    assert first.open == pytest.approx(100.0)
    assert first.high == pytest.approx(105.0)
    assert first.low == pytest.approx(95.0)
    assert first.close == pytest.approx(102.0)
    assert first.volume == pytest.approx(10.0)

    assert first.timestamp == int(
        pd.Timestamp(
            "2026-01-01 00:00:00+00:00"
        ).timestamp()
    )


def test_empty_dataframe_returns_empty_list() -> None:
    data = make_data().iloc[0:0]

    assert dataframe_to_candles(data) == []


def test_missing_columns_raise_error() -> None:
    data = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                ["2026-01-01 00:00:00+00:00"]
            ),
            "close": [100.0],
        }
    )

    with pytest.raises(
        ValueError,
        match="обязательные колонки",
    ):
        dataframe_to_candles(data)


def test_accepts_string_datetime() -> None:
    data = make_data()
    data["datetime"] = data["datetime"].astype(str)

    candles = dataframe_to_candles(data)

    assert len(candles) == 2
    assert candles[0].timestamp > 0
