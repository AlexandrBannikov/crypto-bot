from dataclasses import dataclass

from app.engine import Candle, Trade
from app.stop_manager import (
    stop_exit_price,
    stop_was_hit,
    trail_stop,
)
from app.trading_types import (
    ExitReason,
    PositionSide,
    TradeAction,
)


@dataclass(frozen=True, slots=True)
class PaperPosition:
    side: PositionSide
    entry_timestamp: int
    entry_price: float
    quantity: float
    entry_fee: float
    entry_cost: float
    initial_stop_loss: float | None = None
    active_stop_loss: float | None = None
    stop_reason: ExitReason | None = None
    trailing_stop_percent: float | None = None

    def __post_init__(self) -> None:
        if self.entry_timestamp < 0:
            raise ValueError(
                "entry_timestamp must not be negative"
            )

        if self.entry_price <= 0:
            raise ValueError(
                "entry_price must be greater than zero"
            )

        if self.quantity <= 0:
            raise ValueError(
                "quantity must be greater than zero"
            )

        if self.entry_fee < 0:
            raise ValueError(
                "entry_fee must not be negative"
            )

        if self.entry_cost <= 0:
            raise ValueError(
                "entry_cost must be greater than zero"
            )

        if self.entry_fee > self.entry_cost:
            raise ValueError(
                "entry_fee must not exceed entry_cost"
            )

        if self.initial_stop_loss is not None:
            if self.initial_stop_loss <= 0:
                raise ValueError(
                    "stop_loss must be greater than zero"
                )

            if self.side == PositionSide.LONG:
                if self.initial_stop_loss >= self.entry_price:
                    raise ValueError(
                        "LONG stop_loss must be below "
                        "entry_price"
                    )

            elif self.initial_stop_loss <= self.entry_price:
                raise ValueError(
                    "SHORT stop_loss must be above "
                    "entry_price"
                )

            if self.stop_reason is None:
                raise ValueError(
                    "stop_reason is required when "
                    "stop_loss is set"
                )

        elif self.stop_reason is not None:
            raise ValueError(
                "initial_stop_loss is required when "
                "stop_reason is set"
            )

        if self.active_stop_loss is not None:
            if self.active_stop_loss <= 0:
                raise ValueError(
                    "active_stop_loss must be greater than zero"
                )

            if self.initial_stop_loss is None:
                raise ValueError(
                    "initial_stop_loss is required when "
                    "active_stop_loss is set"
                )

        if self.trailing_stop_percent is not None:
            if not 0 < self.trailing_stop_percent < 1:
                raise ValueError(
                    "trailing_stop_percent must be "
                    "greater than zero and less than one"
                )

            if self.active_stop_loss is None:
                raise ValueError(
                    "stop_loss is required for trailing stop"
                )


@dataclass(frozen=True, slots=True)
class PaperSessionSnapshot:
    balance: float = 1000.0
    last_candle_timestamp: int | None = None
    pending_action: TradeAction = TradeAction.HOLD
    pending_stop_loss: float | None = None
    pending_reference_price: float | None = None
    pending_trailing_stop_percent: float | None = None
    position: PaperPosition | None = None

    def __post_init__(self) -> None:
        if self.balance < 0:
            raise ValueError(
                "balance must not be negative"
            )

        if (
            self.last_candle_timestamp is not None
            and self.last_candle_timestamp < 0
        ):
            raise ValueError(
                "last_candle_timestamp must not be negative"
            )

        pending_open = self.pending_action in {
            TradeAction.OPEN_LONG,
            TradeAction.OPEN_SHORT,
        }

        if pending_open:
            if self.pending_reference_price is None:
                raise ValueError(
                    "pending_reference_price is required "
                    "for pending open action"
                )

            if self.pending_reference_price <= 0:
                raise ValueError(
                    "pending_reference_price must be "
                    "greater than zero"
                )

        else:
            if self.pending_stop_loss is not None:
                raise ValueError(
                    "pending stop is only valid "
                    "for pending open action"
                )

            if self.pending_reference_price is not None:
                raise ValueError(
                    "pending reference price is only valid "
                    "for pending open action"
                )

            if (
                self.pending_trailing_stop_percent
                is not None
            ):
                raise ValueError(
                    "pending trailing stop is only valid "
                    "for pending open action"
                )

        if self.pending_stop_loss is not None:
            if self.pending_stop_loss <= 0:
                raise ValueError(
                    "pending_stop_loss must be "
                    "greater than zero"
                )

        if (
            self.pending_trailing_stop_percent
            is not None
        ):
            if not (
                0
                < self.pending_trailing_stop_percent
                < 1
            ):
                raise ValueError(
                    "pending_trailing_stop_percent must be "
                    "greater than zero and less than one"
                )

            if self.pending_stop_loss is None:
                raise ValueError(
                    "pending_stop_loss is required "
                    "for pending trailing stop"
                )


class PaperTradingSession:
    def __init__(
        self,
        snapshot: PaperSessionSnapshot | None = None,
        *,
        commission_rate: float = 0.001,
    ) -> None:
        if not 0 <= commission_rate < 1:
            raise ValueError(
                "commission_rate must be greater than or equal "
                "to zero and less than one"
            )

        self.commission_rate = commission_rate
        self._snapshot = (
            snapshot
            or PaperSessionSnapshot()
        )

    @property
    def snapshot(self) -> PaperSessionSnapshot:
        return self._snapshot

    def accept_closed_candle(
        self,
        candle: Candle,
    ) -> bool:
        self._validate_candle(candle)

        previous_timestamp = (
            self._snapshot.last_candle_timestamp
        )

        if (
            previous_timestamp is not None
            and candle.timestamp <= previous_timestamp
        ):
            return False

        self._snapshot = PaperSessionSnapshot(
            balance=self._snapshot.balance,
            last_candle_timestamp=candle.timestamp,
            pending_action=self._snapshot.pending_action,
            pending_stop_loss=(
                self._snapshot.pending_stop_loss
            ),
            pending_reference_price=(
                self._snapshot.pending_reference_price
            ),
            pending_trailing_stop_percent=(
                self._snapshot
                .pending_trailing_stop_percent
            ),
            position=self._snapshot.position,
        )

        return True

    def process_closed_candle(
        self,
        candle: Candle,
    ) -> Trade | None:
        if not self.accept_closed_candle(candle):
            return None

        if self.position_stop_was_hit(candle):
            return self.close_position_at_stop(candle)

        self.update_trailing_stop(
            close_price=candle.close,
        )

        return None
    def close_position(
        self,
        *,
        exit_timestamp: int,
        exit_price: float,
        exit_reason: ExitReason,
    ) -> Trade:
        position = self._snapshot.position

        if position is None:
            raise ValueError(
                "session has no open position"
            )

        if exit_timestamp < position.entry_timestamp:
            raise ValueError(
                "exit_timestamp must not be earlier "
                "than entry_timestamp"
            )

        if exit_price <= 0:
            raise ValueError(
                "exit_price must be greater than zero"
            )

        exit_notional = (
            position.quantity * exit_price
        )

        exit_fee = (
            exit_notional
            * self.commission_rate
        )

        entry_margin = (
            position.entry_cost
            - position.entry_fee
        )

        if position.side == PositionSide.LONG:
            gross_profit = (
                position.quantity
                * (
                    exit_price
                    - position.entry_price
                )
            )
        else:
            gross_profit = (
                position.quantity
                * (
                    position.entry_price
                    - exit_price
                )
            )

        released_capital = (
            entry_margin
            + gross_profit
            - exit_fee
        )

        profit = (
            released_capital
            - position.entry_cost
        )

        profit_percent = (
            profit
            / position.entry_cost
            * 100
        )

        trade = Trade(
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=exit_timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            entry_fee=position.entry_fee,
            exit_fee=exit_fee,
            profit=profit,
            profit_percent=profit_percent,
            side=position.side,
            exit_reason=exit_reason,
        )

        self._snapshot = PaperSessionSnapshot(
            balance=(
                self._snapshot.balance
                + released_capital
            ),
            last_candle_timestamp=(
                self._snapshot.last_candle_timestamp
            ),
            pending_action=TradeAction.HOLD,
            pending_stop_loss=None,
            pending_reference_price=None,
            pending_trailing_stop_percent=None,
            position=None,
        )

        return trade

    def close_position_at_stop(
        self,
        candle: Candle,
    ) -> Trade:
        position = self._snapshot.position

        if position is None:
            raise ValueError(
                "session has no open position"
            )

        if position.active_stop_loss is None:
            raise ValueError(
                "position has no active stop"
            )

        if not self.position_stop_was_hit(candle):
            raise ValueError(
                "position stop was not hit"
            )

        exit_price = self.position_stop_exit_price(
            candle
        )

        exit_reason = (
            position.stop_reason
            or ExitReason.STOP_LOSS
        )

        return self.close_position(
            exit_timestamp=candle.timestamp,
            exit_price=exit_price,
            exit_reason=exit_reason,
        )

    def position_stop_was_hit(
        self,
        candle: Candle,
    ) -> bool:
        position = self._snapshot.position

        if (
            position is None
            or position.active_stop_loss is None
        ):
            return False

        return stop_was_hit(
            side=position.side,
            candle=candle,
            stop_loss=position.active_stop_loss,
        )

    def position_stop_exit_price(
        self,
        candle: Candle,
    ) -> float:
        position = self._snapshot.position

        if position is None:
            raise ValueError(
                "session has no open position"
            )

        if position.active_stop_loss is None:
            raise ValueError(
                "position has no stop_loss"
            )

        return stop_exit_price(
            side=position.side,
            candle=candle,
            stop_loss=position.active_stop_loss,
        )

    def update_trailing_stop(
        self,
        close_price: float,
    ) -> bool:
        position = self._snapshot.position

        if (
            position is None
            or position.active_stop_loss is None
            or position.trailing_stop_percent is None
        ):
            return False

        updated_stop = trail_stop(
            side=position.side,
            current_stop=position.active_stop_loss,
            close_price=close_price,
            trailing_stop_percent=(
                position.trailing_stop_percent
            ),
        )

        if updated_stop == position.active_stop_loss:
            return False

        updated_position = PaperPosition(
            side=position.side,
            entry_timestamp=position.entry_timestamp,
            entry_price=position.entry_price,
            quantity=position.quantity,
            entry_fee=position.entry_fee,
            entry_cost=position.entry_cost,
            initial_stop_loss=position.initial_stop_loss,
            active_stop_loss=updated_stop,
            stop_reason=ExitReason.TRAILING_STOP,
            trailing_stop_percent=(
                position.trailing_stop_percent
            ),
        )

        self._snapshot = PaperSessionSnapshot(
            balance=self._snapshot.balance,
            last_candle_timestamp=(
                self._snapshot.last_candle_timestamp
            ),
            pending_action=self._snapshot.pending_action,
            pending_stop_loss=(
                self._snapshot.pending_stop_loss
            ),
            pending_reference_price=(
                self._snapshot.pending_reference_price
            ),
            pending_trailing_stop_percent=(
                self._snapshot
                .pending_trailing_stop_percent
            ),
            position=updated_position,
        )

        return True

    @staticmethod
    def _validate_candle(
        candle: Candle,
    ) -> None:
        if candle.timestamp < 0:
            raise ValueError(
                "candle timestamp must not be negative"
            )

        if min(
            candle.open,
            candle.high,
            candle.low,
            candle.close,
        ) <= 0:
            raise ValueError(
                "candle prices must be greater than zero"
            )

        if candle.volume < 0:
            raise ValueError(
                "candle volume must not be negative"
            )

        if candle.high < max(
            candle.open,
            candle.low,
            candle.close,
        ):
            raise ValueError(
                "invalid candle high"
            )

        if candle.low > min(
            candle.open,
            candle.high,
            candle.close,
        ):
            raise ValueError(
                "invalid candle low"
            )
