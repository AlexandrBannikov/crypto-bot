from enum import Enum


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class TradeAction(str, Enum):
    HOLD = "hold"
    OPEN_LONG = "open_long"
    CLOSE_LONG = "close_long"
    OPEN_SHORT = "open_short"
    CLOSE_SHORT = "close_short"
