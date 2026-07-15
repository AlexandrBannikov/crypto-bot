from app.trading_types import (
    PositionSide,
    TradeAction,
)


def test_position_side_values() -> None:
    assert PositionSide.LONG.value == "long"
    assert PositionSide.SHORT.value == "short"


def test_trade_action_values() -> None:
    assert TradeAction.HOLD.value == "hold"
    assert TradeAction.OPEN_LONG.value == "open_long"
    assert TradeAction.CLOSE_LONG.value == "close_long"
    assert TradeAction.OPEN_SHORT.value == "open_short"
    assert TradeAction.CLOSE_SHORT.value == "close_short"


def test_enum_values_can_be_serialized() -> None:
    assert str(PositionSide.LONG.value) == "long"
    assert str(TradeAction.OPEN_SHORT.value) == "open_short"
