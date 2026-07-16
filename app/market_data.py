from pathlib import Path
from typing import Protocol, Sequence

from app.candle_mapper import dataframe_to_candles
from app.data_loader import load_market_data
from app.engine import Candle


class MarketDataFeed(Protocol):
    def get_candles(self) -> Sequence[Candle]:
        ...


class CsvMarketDataFeed:
    def __init__(
        self,
        file_path: str | Path,
        *,
        limit: int | None = None,
    ) -> None:
        self.file_path = Path(file_path)
        self.limit = limit

        if self.limit is not None and self.limit <= 0:
            raise ValueError(
                "limit must be greater than zero"
            )

    def get_candles(self) -> tuple[Candle, ...]:
        frame = load_market_data(self.file_path)

        if self.limit is not None:
            frame = frame.tail(self.limit)

        candles = dataframe_to_candles(frame)

        return tuple(candles)

    def get_latest_candle(self) -> Candle:
        candles = self.get_candles()

        if not candles:
            raise ValueError("market data contains no candles")

        return candles[-1]
