from dataclasses import dataclass

from app.strategies import Signal
from app.trading_types import TradeAction


@dataclass(frozen=True)
class TradeSignal:
    action: Signal | TradeAction
    stop_loss: float | None = None
    trailing_stop_percent: float | None = None
    break_even_r_multiple: float | None = None

    def __post_init__(self) -> None:
        if self.stop_loss is not None and self.stop_loss <= 0:
            raise ValueError(
                "stop_loss must be greater than zero"
            )

        if self.trailing_stop_percent is not None:
            if not 0 < self.trailing_stop_percent < 1:
                raise ValueError(
                    "trailing_stop_percent must be greater "
                    "than zero and less than one"
                )

            if self.stop_loss is None:
                raise ValueError(
                    "stop_loss is required when "
                    "trailing_stop_percent is set"
                )

        if self.break_even_r_multiple is not None:
            if self.break_even_r_multiple <= 0:
                raise ValueError(
                    "break_even_r_multiple must be "
                    "greater than zero"
                )

            if self.stop_loss is None:
                raise ValueError(
                    "stop_loss is required when "
                    "break_even_r_multiple is set"
                )
