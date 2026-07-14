import pandas as pd
import pytest

from app.indicators import ema, rsi, sma


def test_sma() -> None:
    prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    result = sma(prices, period=3)

    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_ema_returns_values() -> None:
    prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    result = ema(prices, period=3)

    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[-1] > result.iloc[-2]


def test_rsi_for_rising_prices() -> None:
    prices = pd.Series(
        [float(value) for value in range(1, 30)]
    )

    result = rsi(prices, period=14)

    assert result.iloc[-1] == pytest.approx(100.0)


def test_rsi_for_flat_prices() -> None:
    prices = pd.Series([100.0] * 30)

    result = rsi(prices, period=14)

    assert result.iloc[-1] == pytest.approx(50.0)


@pytest.mark.parametrize(
    "function",
    [sma, ema, rsi],
)
def test_period_must_be_positive(function) -> None:
    prices = pd.Series([1.0, 2.0, 3.0])

    with pytest.raises(ValueError):
        function(prices, period=0)

