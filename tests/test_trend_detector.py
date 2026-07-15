import pytest

from app.engine import Candle
from app.trend_detector import (
    TrendDetector,
    TrendState,
)


def make_candles(
    *prices: float,
) -> list[Candle]:
    return [
        Candle(
            timestamp=index,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1.0,
        )
        for index, price in enumerate(prices)
    ]


def test_detects_uptrend() -> None:
    detector = TrendDetector(
        fast_period=2,
        slow_period=4,
        slope_lookback=2,
        min_separation_percent=0.01,
    )

    candles = make_candles(
        100,
        101,
        102,
        103,
        104,
        105,
        106,
        107,
    )

    result = detector.detect(
        candles,
        len(candles) - 1,
    )

    assert result == TrendState.UPTREND


def test_detects_downtrend() -> None:
    detector = TrendDetector(
        fast_period=2,
        slow_period=4,
        slope_lookback=2,
        min_separation_percent=0.01,
    )

    candles = make_candles(
        107,
        106,
        105,
        104,
        103,
        102,
        101,
        100,
    )

    result = detector.detect(
        candles,
        len(candles) - 1,
    )

    assert result == TrendState.DOWNTREND


def test_detects_sideways_market() -> None:
    detector = TrendDetector(
        fast_period=2,
        slow_period=4,
        slope_lookback=2,
        min_separation_percent=0.1,
    )

    candles = make_candles(
        100,
        100,
        100,
        100,
        100,
        100,
        100,
    )

    result = detector.detect(
        candles,
        len(candles) - 1,
    )

    assert result == TrendState.SIDEWAYS


def test_returns_sideways_before_warmup() -> None:
    detector = TrendDetector(
        fast_period=2,
        slow_period=5,
        slope_lookback=2,
        min_separation_percent=0,
    )

    candles = make_candles(
        100,
        101,
        102,
        103,
    )

    result = detector.detect(
        candles,
        len(candles) - 1,
    )

    assert result == TrendState.SIDEWAYS


def test_small_ema_separation_is_sideways() -> None:
    detector = TrendDetector(
        fast_period=2,
        slow_period=4,
        slope_lookback=2,
        min_separation_percent=5.0,
    )

    candles = make_candles(
        100,
        101,
        102,
        103,
        104,
        105,
    )

    result = detector.detect(
        candles,
        len(candles) - 1,
    )

    assert result == TrendState.SIDEWAYS


def test_detector_can_be_reused_from_start() -> None:
    detector = TrendDetector(
        fast_period=2,
        slow_period=4,
        slope_lookback=2,
        min_separation_percent=0.01,
    )

    rising = make_candles(
        100,
        101,
        102,
        103,
        104,
        105,
    )

    falling = make_candles(
        105,
        104,
        103,
        102,
        101,
        100,
    )

    assert detector.detect(
        rising,
        len(rising) - 1,
    ) == TrendState.UPTREND

    assert detector.detect(
        falling,
        0,
    ) == TrendState.SIDEWAYS

    assert detector.detect(
        falling,
        len(falling) - 1,
    ) == TrendState.DOWNTREND


@pytest.mark.parametrize(
    (
        "fast_period",
        "slow_period",
        "slope_lookback",
        "min_separation_percent",
    ),
    [
        (0, 20, 5, 0.1),
        (-1, 20, 5, 0.1),
        (10, 0, 5, 0.1),
        (20, 20, 5, 0.1),
        (30, 20, 5, 0.1),
        (10, 20, 0, 0.1),
        (10, 20, 5, -0.1),
    ],
)
def test_rejects_invalid_configuration(
    fast_period,
    slow_period,
    slope_lookback,
    min_separation_percent,
) -> None:
    with pytest.raises(ValueError):
        TrendDetector(
            fast_period=fast_period,
            slow_period=slow_period,
            slope_lookback=slope_lookback,
            min_separation_percent=(
                min_separation_percent
            ),
        )


def test_rejects_invalid_index() -> None:
    detector = TrendDetector(
        fast_period=2,
        slow_period=4,
    )

    candles = make_candles(
        100,
        101,
    )

    with pytest.raises(IndexError):
        detector.detect(
            candles,
            index=5,
        )
