from pathlib import Path

import pandas as pd
import pytest

from app.data_loader import (
    find_missing_hours,
    load_market_data,
)


def make_valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.date_range(
                start="2026-01-01",
                periods=4,
                freq="h",
                tz="UTC",
            ),
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [101.0, 102.0, 103.0, 104.0],
            "volume": [10.0, 11.0, 12.0, 13.0],
        }
    )


def write_csv(
    tmp_path: Path,
    frame: pd.DataFrame,
    filename: str = "market.csv",
) -> Path:
    file_path = tmp_path / filename
    frame.to_csv(file_path, index=False)
    return file_path


def test_load_valid_market_data(tmp_path: Path) -> None:
    file_path = write_csv(tmp_path, make_valid_frame())

    result = load_market_data(file_path)

    assert len(result) == 4
    assert list(result.columns) == [
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


def test_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_market_data("missing.csv")


def test_missing_required_column(tmp_path: Path) -> None:
    frame = make_valid_frame().drop(columns=["volume"])
    file_path = write_csv(tmp_path, frame)

    with pytest.raises(ValueError):
        load_market_data(file_path)


def test_duplicate_datetime(tmp_path: Path) -> None:
    frame = make_valid_frame()
    frame.loc[1, "datetime"] = frame.loc[0, "datetime"]

    file_path = write_csv(tmp_path, frame)

    with pytest.raises(ValueError):
        load_market_data(file_path)


def test_invalid_ohlc(tmp_path: Path) -> None:
    frame = make_valid_frame()
    frame.loc[0, "high"] = 90.0

    file_path = write_csv(tmp_path, frame)

    with pytest.raises(ValueError):
        load_market_data(file_path)


def test_find_missing_hour() -> None:
    frame = make_valid_frame().drop(index=[2]).reset_index(drop=True)

    missing = find_missing_hours(frame)

    assert len(missing) == 1
    assert missing[0] == pd.Timestamp(
        "2026-01-01 02:00:00",
        tz="UTC",
    )


def test_no_missing_hours() -> None:
    frame = make_valid_frame()

    missing = find_missing_hours(frame)

    assert len(missing) == 0

