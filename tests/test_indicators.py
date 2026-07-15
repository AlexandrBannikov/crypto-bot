import pandas as pd
import pytest

from app.indicators import atr, ema, rsi, sma, true_range

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

def test_true_range_without_price_gap() -> None:
    data = pd.DataFrame(
        {
            "high": [110.0, 112.0, 115.0],
            "low": [100.0, 102.0, 105.0],
            "close": [105.0, 108.0, 110.0],
        }
    )

    result = true_range(data)

    assert result.iloc[0] == pytest.approx(10.0)
    assert result.iloc[1] == pytest.approx(10.0)
    assert result.iloc[2] == pytest.approx(10.0)


def test_true_range_accounts_for_upward_gap() -> None:
    data = pd.DataFrame(
        {
            "high": [105.0, 125.0],
            "low": [95.0, 118.0],
            "close": [100.0, 122.0],
        }
    )

    result = true_range(data)

    assert result.iloc[0] == pytest.approx(10.0)
    assert result.iloc[1] == pytest.approx(25.0)


def test_true_range_accounts_for_downward_gap() -> None:
    data = pd.DataFrame(
        {
            "high": [105.0, 82.0],
            "low": [95.0, 75.0],
            "close": [100.0, 80.0],
        }
    )

    result = true_range(data)

    assert result.iloc[0] == pytest.approx(10.0)
    assert result.iloc[1] == pytest.approx(25.0)


def test_atr_for_constant_ranges() -> None:
    data = pd.DataFrame(
        {
            "high": [110.0] * 20,
            "low": [100.0] * 20,
            "close": [105.0] * 20,
        }
    )

    result = atr(data, period=14)

    assert result.iloc[:13].isna().all()
    assert result.iloc[-1] == pytest.approx(10.0)


def test_atr_reacts_to_larger_range() -> None:
    data = pd.DataFrame(
        {
            "high": [110.0] * 14 + [130.0],
            "low": [100.0] * 14 + [90.0],
            "close": [105.0] * 14 + [110.0],
        }
    )

    result = atr(data, period=14)

    assert result.iloc[-1] > result.iloc[-2]


def test_true_range_requires_ohlc_columns() -> None:
    data = pd.DataFrame(
        {
            "high": [110.0],
            "close": [105.0],
        }
    )

    with pytest.raises(
        ValueError,
        match="high, low и close",
    ):
        true_range(data)


def test_atr_period_must_be_positive() -> None:
    data = pd.DataFrame(
        {
            "high": [110.0],
            "low": [100.0],
            "close": [105.0],
        }
    )

    with pytest.raises(ValueError):
        atr(data, period=0)

