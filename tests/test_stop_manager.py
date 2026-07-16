import pytest

from app.candle import Candle
from app.stop_manager import (
    stop_exit_price,
    stop_was_hit,
    trail_stop,
)
from app.trading_types import PositionSide


def make_candle(
    *,
    open_price: float = 100,
    high: float = 110,
    low: float = 90,
    close: float = 105,
) -> Candle:
    return Candle(
        timestamp=1,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1,
    )


def test_long_stop_is_hit() -> None:
    assert stop_was_hit(
        side=PositionSide.LONG,
        candle=make_candle(low=94),
        stop_loss=95,
    )


def test_long_stop_is_not_hit() -> None:
    assert not stop_was_hit(
        side=PositionSide.LONG,
        candle=make_candle(low=96),
        stop_loss=95,
    )


def test_short_stop_is_hit() -> None:
    assert stop_was_hit(
        side=PositionSide.SHORT,
        candle=make_candle(high=106),
        stop_loss=105,
    )


def test_short_stop_is_not_hit() -> None:
    assert not stop_was_hit(
        side=PositionSide.SHORT,
        candle=make_candle(high=104),
        stop_loss=105,
    )


def test_long_stop_exit_uses_stop_price() -> None:
    assert stop_exit_price(
        side=PositionSide.LONG,
        candle=make_candle(open_price=100),
        stop_loss=95,
    ) == pytest.approx(95)


def test_long_gap_uses_open_price() -> None:
    assert stop_exit_price(
        side=PositionSide.LONG,
        candle=make_candle(
            open_price=90,
            high=94,
            low=88,
            close=92,
        ),
        stop_loss=95,
    ) == pytest.approx(90)


def test_short_stop_exit_uses_stop_price() -> None:
    assert stop_exit_price(
        side=PositionSide.SHORT,
        candle=make_candle(open_price=100),
        stop_loss=105,
    ) == pytest.approx(105)


def test_short_gap_uses_open_price() -> None:
    assert stop_exit_price(
        side=PositionSide.SHORT,
        candle=make_candle(
            open_price=110,
            high=112,
            low=108,
            close=109,
        ),
        stop_loss=105,
    ) == pytest.approx(110)


def test_long_trailing_stop_moves_up() -> None:
    assert trail_stop(
        side=PositionSide.LONG,
        current_stop=95,
        close_price=110,
        trailing_stop_percent=0.05,
    ) == pytest.approx(104.5)


def test_long_trailing_stop_never_moves_down() -> None:
    assert trail_stop(
        side=PositionSide.LONG,
        current_stop=105,
        close_price=100,
        trailing_stop_percent=0.05,
    ) == pytest.approx(105)


def test_short_trailing_stop_moves_down() -> None:
    assert trail_stop(
        side=PositionSide.SHORT,
        current_stop=105,
        close_price=90,
        trailing_stop_percent=0.05,
    ) == pytest.approx(94.5)


def test_short_trailing_stop_never_moves_up() -> None:
    assert trail_stop(
        side=PositionSide.SHORT,
        current_stop=95,
        close_price=100,
        trailing_stop_percent=0.05,
    ) == pytest.approx(95)


@pytest.mark.parametrize(
    "trailing_stop_percent",
    [0, -0.1, 1, 1.1],
)
def test_rejects_invalid_trailing_percent(
    trailing_stop_percent: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="trailing_stop_percent",
    ):
        trail_stop(
            side=PositionSide.LONG,
            current_stop=95,
            close_price=100,
            trailing_stop_percent=trailing_stop_percent,
        )
