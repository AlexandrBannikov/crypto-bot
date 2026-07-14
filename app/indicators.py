import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    if period <= 0:
        raise ValueError("Период SMA должен быть больше нуля")

    return series.astype(float).rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    if period <= 0:
        raise ValueError("Период EMA должен быть больше нуля")

    return series.astype(float).ewm(
        span=period,
        adjust=False,
        min_periods=period,
    ).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    if period <= 0:
        raise ValueError("Период RSI должен быть больше нуля")

    prices = series.astype(float)
    delta = prices.diff()

    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    average_gain = gains.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    average_loss = losses.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    relative_strength = average_gain / average_loss
    result = 100 - (100 / (1 + relative_strength))

    # Если цена только растёт, средний убыток равен нулю.
    result = result.mask(
        (average_loss == 0) & (average_gain > 0),
        100.0,
    )

    # Если цена вообще не меняется.
    result = result.mask(
        (average_loss == 0) & (average_gain == 0),
        50.0,
    )

    return result

