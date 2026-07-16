from collections.abc import Callable
from dataclasses import dataclass
import json
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.engine import Candle


BYBIT_API_URL = "https://api.bybit.com"
KLINE_PATH = "/v5/market/kline"

SUPPORTED_CATEGORIES = {
    "spot",
    "linear",
    "inverse",
}

SUPPORTED_INTERVALS = {
    "1",
    "3",
    "5",
    "15",
    "30",
    "60",
    "120",
    "240",
    "360",
    "720",
}


JsonObject = dict[str, Any]
HttpGetJson = Callable[
    [str, dict[str, str | int], float],
    JsonObject,
]
ClockMilliseconds = Callable[[], int]


@dataclass(frozen=True, slots=True)
class BybitMarketDataConfig:
    symbol: str = "ETHUSDT"
    interval: str = "60"
    category: str = "spot"
    limit: int = 200
    timeout_seconds: float = 10.0
    closed_candles_only: bool = True
    base_url: str = BYBIT_API_URL

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        object.__setattr__(
            self,
            "symbol",
            normalized_symbol,
        )

        if self.category not in SUPPORTED_CATEGORIES:
            raise ValueError(
                "unsupported Bybit category"
            )

        if self.interval not in SUPPORTED_INTERVALS:
            raise ValueError(
                "unsupported Bybit interval"
            )

        if not 1 <= self.limit <= 1000:
            raise ValueError(
                "limit must be between 1 and 1000"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
            )

        if not self.base_url.strip():
            raise ValueError(
                "base_url must not be empty"
            )


class BybitMarketDataFeed:
    def __init__(
        self,
        config: BybitMarketDataConfig | None = None,
        *,
        http_get_json: HttpGetJson | None = None,
        clock_ms: ClockMilliseconds | None = None,
    ) -> None:
        self.config = (
            config
            or BybitMarketDataConfig()
        )

        self._http_get_json = (
            http_get_json
            or self._default_http_get_json
        )

        self._clock_ms = (
            clock_ms
            or self._default_clock_ms
        )

    def get_candles(self) -> tuple[Candle, ...]:
        payload = self._http_get_json(
            self.config.base_url + KLINE_PATH,
            {
                "category": self.config.category,
                "symbol": self.config.symbol,
                "interval": self.config.interval,
                "limit": self.config.limit,
            },
            self.config.timeout_seconds,
        )

        rows = self._extract_rows(payload)
        now_ms = self._clock_ms()
        interval_ms = (
            int(self.config.interval)
            * 60
            * 1000
        )

        candles_by_timestamp: dict[int, Candle] = {}

        for row in rows:
            candle = self._row_to_candle(row)

            start_ms = candle.timestamp * 1000

            if (
                self.config.closed_candles_only
                and start_ms + interval_ms > now_ms
            ):
                continue

            candles_by_timestamp[
                candle.timestamp
            ] = candle

        candles = tuple(
            candles_by_timestamp[timestamp]
            for timestamp in sorted(
                candles_by_timestamp
            )
        )

        if not candles:
            raise ValueError(
                "Bybit returned no closed candles"
            )

        return candles

    def get_latest_candle(self) -> Candle:
        return self.get_candles()[-1]

    @staticmethod
    def _extract_rows(
        payload: JsonObject,
    ) -> list[list[str]]:
        ret_code = payload.get("retCode")

        if ret_code != 0:
            message = payload.get(
                "retMsg",
                "unknown Bybit error",
            )

            raise RuntimeError(
                f"Bybit API error {ret_code}: {message}"
            )

        result = payload.get("result")

        if not isinstance(result, dict):
            raise ValueError(
                "Bybit response has no result object"
            )

        rows = result.get("list")

        if not isinstance(rows, list):
            raise ValueError(
                "Bybit response has no kline list"
            )

        return rows

    @staticmethod
    def _row_to_candle(
        row: list[str],
    ) -> Candle:
        if len(row) < 6:
            raise ValueError(
                "invalid Bybit kline row"
            )

        try:
            start_ms = int(row[0])
            open_price = float(row[1])
            high_price = float(row[2])
            low_price = float(row[3])
            close_price = float(row[4])
            volume = float(row[5])
        except (TypeError, ValueError) as error:
            raise ValueError(
                "invalid Bybit kline values"
            ) from error

        if min(
            open_price,
            high_price,
            low_price,
            close_price,
        ) <= 0:
            raise ValueError(
                "Bybit candle prices must be positive"
            )

        if volume < 0:
            raise ValueError(
                "Bybit candle volume must not be negative"
            )

        if high_price < max(
            open_price,
            low_price,
            close_price,
        ):
            raise ValueError(
                "invalid Bybit candle high"
            )

        if low_price > min(
            open_price,
            high_price,
            close_price,
        ):
            raise ValueError(
                "invalid Bybit candle low"
            )

        return Candle(
            timestamp=start_ms // 1000,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        )

    @staticmethod
    def _default_clock_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _default_http_get_json(
        url: str,
        params: dict[str, str | int],
        timeout_seconds: float,
    ) -> JsonObject:
        request_url = (
            url
            + "?"
            + urlencode(params)
        )

        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "crypto-bot/1.0",
            },
        )

        try:
            with urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                body = response.read()
        except OSError as error:
            raise ConnectionError(
                "failed to request Bybit market data"
            ) from error

        try:
            payload = json.loads(
                body.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise ValueError(
                "Bybit returned invalid JSON"
            ) from error

        if not isinstance(payload, dict):
            raise ValueError(
                "Bybit returned invalid response"
            )

        return payload
