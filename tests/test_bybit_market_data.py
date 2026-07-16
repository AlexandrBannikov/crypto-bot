import pytest

from app.bybit_market_data import (
    KLINE_PATH,
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.engine import Candle


HOUR_MS = 60 * 60 * 1000


def make_payload(
    rows: list[list[str]],
) -> dict:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "spot",
            "symbol": "ETHUSDT",
            "list": rows,
        },
    }


def make_row(
    start_ms: int,
    *,
    open_price: str = "100",
    high_price: str = "110",
    low_price: str = "90",
    close_price: str = "105",
    volume: str = "12.5",
) -> list[str]:
    return [
        str(start_ms),
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
        "1000",
    ]


def test_requests_public_bybit_kline_endpoint() -> None:
    captured = {}

    def fake_http_get(
        url,
        params,
        timeout_seconds,
    ):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout_seconds

        return make_payload(
            [make_row(0)]
        )

    feed = BybitMarketDataFeed(
        BybitMarketDataConfig(
            symbol="ethusdt",
            interval="60",
            category="spot",
            limit=100,
            timeout_seconds=5,
        ),
        http_get_json=fake_http_get,
        clock_ms=lambda: 2 * HOUR_MS,
    )

    feed.get_candles()

    assert captured["url"].endswith(
        KLINE_PATH
    )

    assert captured["params"] == {
        "category": "spot",
        "symbol": "ETHUSDT",
        "interval": "60",
        "limit": 100,
    }

    assert captured["timeout"] == 5


def test_converts_and_sorts_bybit_candles() -> None:
    payload = make_payload(
        [
            make_row(
                2 * HOUR_MS,
                open_price="120",
                high_price="130",
                low_price="115",
                close_price="125",
            ),
            make_row(
                0,
                open_price="100",
                high_price="110",
                low_price="90",
                close_price="105",
            ),
            make_row(
                HOUR_MS,
                open_price="110",
                high_price="120",
                low_price="100",
                close_price="115",
            ),
        ]
    )

    feed = BybitMarketDataFeed(
        http_get_json=lambda *_: payload,
        clock_ms=lambda: 4 * HOUR_MS,
    )

    candles = feed.get_candles()

    assert isinstance(candles, tuple)
    assert all(
        isinstance(candle, Candle)
        for candle in candles
    )

    assert [
        candle.timestamp
        for candle in candles
    ] == [
        0,
        3600,
        7200,
    ]

    assert candles[-1].close == pytest.approx(
        125
    )


def test_excludes_current_unclosed_candle() -> None:
    payload = make_payload(
        [
            make_row(2 * HOUR_MS),
            make_row(HOUR_MS),
            make_row(0),
        ]
    )

    feed = BybitMarketDataFeed(
        http_get_json=lambda *_: payload,
        clock_ms=lambda: 2 * HOUR_MS + 30_000,
    )

    candles = feed.get_candles()

    assert [
        candle.timestamp
        for candle in candles
    ] == [0, 3600]


def test_can_include_current_candle() -> None:
    payload = make_payload(
        [make_row(2 * HOUR_MS)]
    )

    feed = BybitMarketDataFeed(
        BybitMarketDataConfig(
            closed_candles_only=False,
        ),
        http_get_json=lambda *_: payload,
        clock_ms=lambda: 2 * HOUR_MS,
    )

    assert len(feed.get_candles()) == 1


def test_latest_candle_returns_newest_closed() -> None:
    payload = make_payload(
        [
            make_row(HOUR_MS),
            make_row(0),
        ]
    )

    feed = BybitMarketDataFeed(
        http_get_json=lambda *_: payload,
        clock_ms=lambda: 3 * HOUR_MS,
    )

    assert (
        feed.get_latest_candle().timestamp
        == 3600
    )


def test_rejects_bybit_api_error() -> None:
    payload = {
        "retCode": 10001,
        "retMsg": "invalid request",
        "result": {},
    }

    feed = BybitMarketDataFeed(
        http_get_json=lambda *_: payload,
    )

    with pytest.raises(
        RuntimeError,
        match="invalid request",
    ):
        feed.get_candles()


def test_rejects_invalid_kline_values() -> None:
    payload = make_payload(
        [
            make_row(
                0,
                high_price="80",
            )
        ]
    )

    feed = BybitMarketDataFeed(
        http_get_json=lambda *_: payload,
        clock_ms=lambda: 2 * HOUR_MS,
    )

    with pytest.raises(
        ValueError,
        match="high",
    ):
        feed.get_candles()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "options"),
        ("interval", "7"),
        ("limit", 0),
        ("limit", 1001),
        ("timeout_seconds", 0),
    ],
)
def test_rejects_invalid_configuration(
    field: str,
    value,
) -> None:
    kwargs = {field: value}

    with pytest.raises(ValueError):
        BybitMarketDataConfig(**kwargs)
