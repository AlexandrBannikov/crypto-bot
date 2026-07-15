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
def true_range(data: pd.DataFrame) -> pd.Series:
    required_columns = {"high", "low", "close"}

    if not required_columns.issubset(data.columns):
        raise ValueError(
            "Для True Range нужны колонки high, low и close"
        )

    high = data["high"].astype(float)
    low = data["low"].astype(float)
    previous_close = data["close"].astype(float).shift(1)

    high_low = high - low
    high_previous_close = (high - previous_close).abs()
    low_previous_close = (low - previous_close).abs()

    result = pd.concat(
        [
            high_low,
            high_previous_close,
            low_previous_close,
        ],
        axis=1,
    ).max(axis=1)

    return result


def atr(
    data: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    if period <= 0:
        raise ValueError("Период ATR должен быть больше нуля")

    ranges = true_range(data)

    return ranges.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()




def adx(
    data: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    if period <= 0:
        raise ValueError("Период ADX должен быть больше нуля")

    required_columns = {
        "high",
        "low",
        "close",
    }

    if not required_columns.issubset(data.columns):
        raise ValueError(
            "Для ADX нужны колонки high, low и close"
        )

    high = data["high"].astype(float)
    low = data["low"].astype(float)
    close = data["close"].astype(float)

    upward_move = high.diff()
    downward_move = -low.diff()

    plus_dm = upward_move.where(
        (upward_move > downward_move)
        & (upward_move > 0),
        0.0,
    )

    minus_dm = downward_move.where(
        (downward_move > upward_move)
        & (downward_move > 0),
        0.0,
    )

    previous_close = close.shift(1)

    true_range_values = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    smoothed_true_range = true_range_values.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    smoothed_plus_dm = plus_dm.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    smoothed_minus_dm = minus_dm.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    plus_di = (
        100
        * smoothed_plus_dm
        / smoothed_true_range
    )

    minus_di = (
        100
        * smoothed_minus_dm
        / smoothed_true_range
    )

    denominator = (
        plus_di + minus_di
    )

    dx = (
        100
        * (plus_di - minus_di).abs()
        / denominator
    )

    dx = dx.where(
        denominator != 0,
        0.0,
    )

    return dx.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()
