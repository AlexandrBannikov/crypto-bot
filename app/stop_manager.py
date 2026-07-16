from app.candle import Candle
from app.trading_types import PositionSide


def stop_was_hit(
    *,
    side: PositionSide,
    candle: Candle,
    stop_loss: float,
) -> bool:
    if stop_loss <= 0:
        raise ValueError(
            "stop_loss must be greater than zero"
        )

    if side == PositionSide.LONG:
        return candle.low <= stop_loss

    return candle.high >= stop_loss


def stop_exit_price(
    *,
    side: PositionSide,
    candle: Candle,
    stop_loss: float,
) -> float:
    if stop_loss <= 0:
        raise ValueError(
            "stop_loss must be greater than zero"
        )

    if side == PositionSide.LONG:
        if candle.open <= stop_loss:
            return candle.open

        return stop_loss

    if candle.open >= stop_loss:
        return candle.open

    return stop_loss


def trail_stop(
    *,
    side: PositionSide,
    current_stop: float,
    close_price: float,
    trailing_stop_percent: float,
) -> float:
    if current_stop <= 0:
        raise ValueError(
            "current_stop must be greater than zero"
        )

    if close_price <= 0:
        raise ValueError(
            "close_price must be greater than zero"
        )

    if not 0 < trailing_stop_percent < 1:
        raise ValueError(
            "trailing_stop_percent must be greater "
            "than zero and less than one"
        )

    if side == PositionSide.LONG:
        candidate_stop = (
            close_price
            * (1 - trailing_stop_percent)
        )

        return max(
            current_stop,
            candidate_stop,
        )

    candidate_stop = (
        close_price
        * (1 + trailing_stop_percent)
    )

    return min(
        current_stop,
        candidate_stop,
    )
