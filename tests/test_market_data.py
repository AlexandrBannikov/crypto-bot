from pathlib import Path

import pandas as pd
import pytest

from app.engine import Candle
from app.market_data import (
    CsvMarketDataFeed,
    MarketDataFeed,
)


def write_market_csv(
    tmp_path: Path,
    *,
    rows: int = 4,
) -> Path:
    frame = pd.DataFrame(
        {
            "datetime": pd.date_range(
                start="2026-01-01",
                periods=rows,
                freq="h",
                tz="UTC",
            ),
            "open": [
                100.0 + index
                for index in range(rows)
            ],
            "high": [
                102.0 + index
                for index in range(rows)
            ],
            "low": [
                99.0 + index
                for index in range(rows)
            ],
            "close": [
                101.0 + index
                for index in range(rows)
            ],
            "volume": [
                10.0 + index
                for index in range(rows)
            ],
        }
    )

    file_path = tmp_path / "market.csv"
    frame.to_csv(file_path, index=False)

    return file_path


def test_csv_feed_implements_market_data_protocol(
    tmp_path: Path,
) -> None:
    feed: MarketDataFeed = CsvMarketDataFeed(
        write_market_csv(tmp_path)
    )

    candles = feed.get_candles()

    assert len(candles) == 4


def test_csv_feed_returns_candles(
    tmp_path: Path,
) -> None:
    feed = CsvMarketDataFeed(
        write_market_csv(tmp_path)
    )

    candles = feed.get_candles()

    assert isinstance(candles, tuple)
    assert isinstance(candles[0], Candle)
    assert candles[0].open == pytest.approx(100)
    assert candles[-1].close == pytest.approx(104)


def test_csv_feed_preserves_chronological_order(
    tmp_path: Path,
) -> None:
    frame = pd.DataFrame(
        {
            "datetime": [
                "2026-01-01 02:00:00+00:00",
                "2026-01-01 00:00:00+00:00",
                "2026-01-01 01:00:00+00:00",
            ],
            "open": [102, 100, 101],
            "high": [103, 101, 102],
            "low": [101, 99, 100],
            "close": [102, 100, 101],
            "volume": [1, 1, 1],
        }
    )

    file_path = tmp_path / "unsorted.csv"
    frame.to_csv(file_path, index=False)

    candles = CsvMarketDataFeed(
        file_path
    ).get_candles()

    assert [
        candle.open
        for candle in candles
    ] == [100, 101, 102]


def test_csv_feed_limit_returns_latest_candles(
    tmp_path: Path,
) -> None:
    feed = CsvMarketDataFeed(
        write_market_csv(tmp_path, rows=5),
        limit=2,
    )

    candles = feed.get_candles()

    assert len(candles) == 2
    assert candles[0].open == pytest.approx(103)
    assert candles[1].open == pytest.approx(104)


def test_csv_feed_returns_latest_candle(
    tmp_path: Path,
) -> None:
    feed = CsvMarketDataFeed(
        write_market_csv(tmp_path)
    )

    candle = feed.get_latest_candle()

    assert candle.open == pytest.approx(103)
    assert candle.close == pytest.approx(104)


@pytest.mark.parametrize(
    "limit",
    [0, -1],
)
def test_csv_feed_rejects_invalid_limit(
    tmp_path: Path,
    limit: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="limit",
    ):
        CsvMarketDataFeed(
            write_market_csv(tmp_path),
            limit=limit,
        )


def test_csv_feed_reuses_loader_validation(
    tmp_path: Path,
) -> None:
    frame = pd.DataFrame(
        {
            "datetime": ["2026-01-01"],
            "open": [100],
            "high": [90],
            "low": [99],
            "close": [100],
            "volume": [1],
        }
    )

    file_path = tmp_path / "invalid.csv"
    frame.to_csv(file_path, index=False)

    with pytest.raises(
        ValueError,
        match="OHLC",
    ):
        CsvMarketDataFeed(
            file_path
        ).get_candles()
