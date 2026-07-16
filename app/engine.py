from dataclasses import dataclass
from typing import Protocol, Sequence

from app.risk import RiskConfig, RiskManager
from app.strategies import Signal
from app.trading_types import (
    ExitReason,
    PositionSide,
    TradeAction,
)


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


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Trade:
    entry_timestamp: int
    exit_timestamp: int
    entry_price: float
    exit_price: float
    quantity: float
    entry_fee: float
    exit_fee: float
    profit: float
    profit_percent: float
    side: PositionSide = PositionSide.LONG
    exit_reason: ExitReason = ExitReason.SIGNAL


@dataclass(frozen=True)
class BacktestResult:
    initial_balance: float
    final_balance: float
    total_profit: float
    total_return_percent: float
    trades: tuple[Trade, ...]
    winning_trades: int
    losing_trades: int
    win_rate_percent: float
    max_drawdown_percent: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    average_winning_trade_percent: float
    average_losing_trade_percent: float
    payoff_ratio: float
    expectancy_percent: float


class Strategy(Protocol):
    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> Signal | TradeSignal | TradeAction:
        ...


class BacktestEngine:
    def __init__(
        self,
        initial_balance: float = 10_000.0,
        commission_rate: float = 0.001,
        risk_config: RiskConfig | None = None,
    ) -> None:
        if initial_balance <= 0:
            raise ValueError(
                "initial_balance must be greater than zero"
            )

        if not 0 <= commission_rate < 1:
            raise ValueError(
                "commission_rate must be greater than or equal "
                "to zero and less than one"
            )

        self.initial_balance = initial_balance
        self.commission_rate = commission_rate
        self.risk_manager = RiskManager(risk_config)

    def run(
        self,
        candles: Sequence[Candle],
        strategy: Strategy,
    ) -> BacktestResult:
        if not candles:
            raise ValueError("candles must not be empty")

        balance = self.initial_balance

        position_side: PositionSide | None = None
        quantity = 0.0

        entry_timestamp: int | None = None
        entry_price: float | None = None
        entry_fee = 0.0
        entry_cost = 0.0

        pending_action = TradeAction.HOLD
        pending_stop_loss: float | None = None
        pending_reference_price: float | None = None
        pending_trailing_stop_percent: float | None = None

        active_stop_loss: float | None = None
        active_stop_reason: ExitReason | None = None
        active_trailing_stop_percent: float | None = None

        trades: list[Trade] = []
        equity_curve: list[float] = [
            self.initial_balance
        ]

        for index, candle in enumerate(candles):
            self._validate_candle(candle)

            if (
                pending_action == TradeAction.OPEN_LONG
                and position_side is None
            ):
                (
                    position_side,
                    quantity,
                    entry_timestamp,
                    entry_price,
                    entry_fee,
                    entry_cost,
                    balance,
                ) = self._open_position(
                    side=PositionSide.LONG,
                    balance=balance,
                    candle=candle,
                    stop_loss=pending_stop_loss,
                    risk_reference_price=pending_reference_price,
                )

                active_stop_loss = pending_stop_loss
                active_stop_reason = (
                    ExitReason.STOP_LOSS
                    if pending_stop_loss is not None
                    else None
                )
                active_trailing_stop_percent = (
                    pending_trailing_stop_percent
                )

                pending_stop_loss = None
                pending_reference_price = None
                pending_trailing_stop_percent = None

            elif (
                pending_action == TradeAction.OPEN_SHORT
                and position_side is None
            ):
                (
                    position_side,
                    quantity,
                    entry_timestamp,
                    entry_price,
                    entry_fee,
                    entry_cost,
                    balance,
                ) = self._open_position(
                    side=PositionSide.SHORT,
                    balance=balance,
                    candle=candle,
                    stop_loss=pending_stop_loss,
                    risk_reference_price=pending_reference_price,
                )

                active_stop_loss = pending_stop_loss
                active_stop_reason = (
                    ExitReason.STOP_LOSS
                    if pending_stop_loss is not None
                    else None
                )
                active_trailing_stop_percent = (
                    pending_trailing_stop_percent
                )

                pending_stop_loss = None
                pending_reference_price = None
                pending_trailing_stop_percent = None

            stop_was_hit = (
                position_side is not None
                and active_stop_loss is not None
                and self._stop_was_hit(
                    side=position_side,
                    candle=candle,
                    stop_loss=active_stop_loss,
                )
            )

            close_requested = (
                (
                    pending_action == TradeAction.CLOSE_LONG
                    and position_side == PositionSide.LONG
                )
                or (
                    pending_action == TradeAction.CLOSE_SHORT
                    and position_side == PositionSide.SHORT
                )
            )

            if stop_was_hit or close_requested:
                assert position_side is not None
                assert entry_timestamp is not None
                assert entry_price is not None

                if stop_was_hit:
                    assert active_stop_loss is not None
                    assert active_stop_reason is not None

                    exit_price = self._stop_exit_price(
                        side=position_side,
                        candle=candle,
                        stop_loss=active_stop_loss,
                    )
                    exit_reason = active_stop_reason
                else:
                    exit_price = candle.open
                    exit_reason = ExitReason.SIGNAL

                released_capital, trade = self._close_position(
                    side=position_side,
                    quantity=quantity,
                    exit_timestamp=candle.timestamp,
                    exit_price=exit_price,
                    entry_timestamp=entry_timestamp,
                    entry_price=entry_price,
                    entry_fee=entry_fee,
                    entry_cost=entry_cost,
                    exit_reason=exit_reason,
                )

                balance += released_capital
                trades.append(trade)

                (
                    position_side,
                    quantity,
                    entry_timestamp,
                    entry_price,
                    entry_fee,
                    entry_cost,
                ) = self._empty_position()

                active_stop_loss = None
                active_stop_reason = None
                active_trailing_stop_percent = None

            raw_signal = strategy.generate_signal(
                candles,
                index,
            )

            signal = self._normalize_signal(
                raw_signal
            )

            pending_action = self._resolve_pending_action(
                requested_action=signal.action,
                position_side=position_side,
            )

            if pending_action in {
                TradeAction.OPEN_LONG,
                TradeAction.OPEN_SHORT,
            }:
                requested_side = (
                    PositionSide.LONG
                    if pending_action == TradeAction.OPEN_LONG
                    else PositionSide.SHORT
                )

                self._validate_stop_loss(
                    side=requested_side,
                    entry_price=candle.close,
                    stop_loss=signal.stop_loss,
                )

                pending_stop_loss = signal.stop_loss
                pending_reference_price = candle.close
                pending_trailing_stop_percent = (
                    signal.trailing_stop_percent
                )
            else:
                pending_stop_loss = None
                pending_reference_price = None
                pending_trailing_stop_percent = None

            if (
                position_side is not None
                and active_stop_loss is not None
                and active_trailing_stop_percent is not None
            ):
                trailed_stop = self._trail_stop(
                    side=position_side,
                    current_stop=active_stop_loss,
                    close_price=candle.close,
                    trailing_stop_percent=(
                        active_trailing_stop_percent
                    ),
                )

                if trailed_stop != active_stop_loss:
                    active_stop_reason = (
                        ExitReason.TRAILING_STOP
                    )

                active_stop_loss = trailed_stop

            equity = self._calculate_equity(
                balance=balance,
                position_side=position_side,
                quantity=quantity,
                entry_price=entry_price,
                entry_fee=entry_fee,
                entry_cost=entry_cost,
                current_price=candle.close,
            )

            equity_curve.append(equity)

        if position_side is not None:
            last_candle = candles[-1]

            assert entry_timestamp is not None
            assert entry_price is not None

            released_capital, trade = self._close_position(
                side=position_side,
                quantity=quantity,
                exit_timestamp=last_candle.timestamp,
                exit_price=last_candle.close,
                entry_timestamp=entry_timestamp,
                entry_price=entry_price,
                entry_fee=entry_fee,
                entry_cost=entry_cost,
                exit_reason=ExitReason.END_OF_DATA,
            )

            balance += released_capital
            trades.append(trade)
            equity_curve.append(balance)

        return self._build_result(
            final_balance=balance,
            trades=trades,
            equity_curve=equity_curve,
        )

    def _open_position(
        self,
        *,
        side: PositionSide,
        balance: float,
        candle: Candle,
        stop_loss: float | None,
        risk_reference_price: float | None,
    ) -> tuple[
        PositionSide,
        float,
        int,
        float,
        float,
        float,
        float,
    ]:
        entry_price = candle.open

        if stop_loss is None:
            # Сохраняем прежнее поведение для стратегий без стопа:
            # весь баланс участвует в позиции.
            entry_fee = balance * self.commission_rate
            position_value = balance - entry_fee
            capital_used = position_value
        else:
            if risk_reference_price is None:
                raise ValueError(
                    "risk_reference_price is required "
                    "when stop_loss is set"
                )

            position_size = (
                self.risk_manager.calculate_position_size(
                    balance=balance,
                    entry_price=risk_reference_price,
                    stop_loss=stop_loss,
                    side=side,
                )
            )

            leverage = self.risk_manager.config.leverage

            # Комиссия также должна помещаться в свободный баланс.
            maximum_affordable_position_value = (
                balance
                / (
                    (1 / leverage)
                    + self.commission_rate
                )
            )

            position_value = min(
                position_size.position_value,
                maximum_affordable_position_value,
            )

            capital_used = position_value / leverage
            entry_fee = (
                position_value
                * self.commission_rate
            )

        quantity = position_value / entry_price
        entry_cost = capital_used + entry_fee
        remaining_balance = balance - entry_cost

        return (
            side,
            quantity,
            candle.timestamp,
            entry_price,
            entry_fee,
            entry_cost,
            remaining_balance,
        )

    def _close_position(
        self,
        *,
        side: PositionSide,
        quantity: float,
        exit_timestamp: int,
        exit_price: float,
        entry_timestamp: int,
        entry_price: float,
        entry_fee: float,
        entry_cost: float,
        exit_reason: ExitReason,
    ) -> tuple[float, Trade]:
        exit_notional = quantity * exit_price
        exit_fee = (
            exit_notional
            * self.commission_rate
        )

        entry_margin = entry_cost - entry_fee

        if side == PositionSide.LONG:
            gross_profit = (
                quantity
                * (exit_price - entry_price)
            )
        else:
            gross_profit = (
                quantity
                * (entry_price - exit_price)
            )

        released_capital = (
            entry_margin
            + gross_profit
            - exit_fee
        )

        profit = released_capital - entry_cost

        profit_percent = (
            profit / entry_cost * 100
            if entry_cost > 0
            else 0.0
        )

        trade = Trade(
            entry_timestamp=entry_timestamp,
            exit_timestamp=exit_timestamp,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            profit=profit,
            profit_percent=profit_percent,
            side=side,
            exit_reason=exit_reason,
        )

        return released_capital, trade

    @staticmethod
    def _empty_position() -> tuple[
        None,
        float,
        None,
        None,
        float,
        float,
    ]:
        return (
            None,
            0.0,
            None,
            None,
            0.0,
            0.0,
        )

    @staticmethod
    def _resolve_pending_action(
        *,
        requested_action: TradeAction,
        position_side: PositionSide | None,
    ) -> TradeAction:
        if position_side is None:
            if requested_action in {
                TradeAction.OPEN_LONG,
                TradeAction.OPEN_SHORT,
            }:
                return requested_action

            return TradeAction.HOLD

        if (
            position_side == PositionSide.LONG
            and requested_action == TradeAction.CLOSE_LONG
        ):
            return requested_action

        if (
            position_side == PositionSide.SHORT
            and requested_action == TradeAction.CLOSE_SHORT
        ):
            return requested_action

        return TradeAction.HOLD

    @staticmethod
    def _normalize_signal(
        signal: Signal | TradeSignal | TradeAction,
    ) -> TradeSignal:
        if isinstance(signal, TradeSignal):
            action = signal.action

            if isinstance(action, TradeAction):
                return signal

            if action == Signal.BUY:
                return TradeSignal(
                    action=TradeAction.OPEN_LONG,
                    stop_loss=signal.stop_loss,
                    trailing_stop_percent=(
                        signal.trailing_stop_percent
                    ),
                )

            if action == Signal.SELL:
                return TradeSignal(
                    action=TradeAction.CLOSE_LONG,
                    stop_loss=signal.stop_loss,
                    trailing_stop_percent=(
                        signal.trailing_stop_percent
                    ),
                )

            return TradeSignal(
                action=TradeAction.HOLD,
                stop_loss=signal.stop_loss,
                trailing_stop_percent=(
                    signal.trailing_stop_percent
                ),
            )

        if isinstance(signal, TradeAction):
            return TradeSignal(
                action=signal,
            )

        if isinstance(signal, Signal):
            if signal == Signal.BUY:
                action = TradeAction.OPEN_LONG
            elif signal == Signal.SELL:
                action = TradeAction.CLOSE_LONG
            else:
                action = TradeAction.HOLD

            return TradeSignal(
                action=action,
            )

        raise TypeError(
            "strategy must return Signal, "
            "TradeAction or TradeSignal"
        )

    @staticmethod
    def _validate_stop_loss(
        *,
        side: PositionSide,
        entry_price: float,
        stop_loss: float | None,
    ) -> None:
        if stop_loss is None:
            return

        if (
            side == PositionSide.LONG
            and stop_loss >= entry_price
        ):
            raise ValueError(
                "long stop_loss must be lower "
                "than entry price"
            )

        if (
            side == PositionSide.SHORT
            and stop_loss <= entry_price
        ):
            raise ValueError(
                "short stop_loss must be greater "
                "than entry price"
            )

    @staticmethod
    def _trail_stop(
        *,
        side: PositionSide,
        current_stop: float,
        close_price: float,
        trailing_stop_percent: float,
    ) -> float:
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

    @staticmethod
    def _stop_was_hit(
        *,
        side: PositionSide,
        candle: Candle,
        stop_loss: float,
    ) -> bool:
        if side == PositionSide.LONG:
            return candle.low <= stop_loss

        return candle.high >= stop_loss

    @staticmethod
    def _stop_exit_price(
        *,
        side: PositionSide,
        candle: Candle,
        stop_loss: float,
    ) -> float:
        if side == PositionSide.LONG:
            if candle.open <= stop_loss:
                return candle.open

            return stop_loss

        if candle.open >= stop_loss:
            return candle.open

        return stop_loss

    @staticmethod
    def _calculate_equity(
        *,
        balance: float,
        position_side: PositionSide | None,
        quantity: float,
        entry_price: float | None,
        entry_fee: float,
        entry_cost: float,
        current_price: float,
    ) -> float:
        if position_side is None:
            return balance

        assert entry_price is not None

        entry_margin = entry_cost - entry_fee

        if position_side == PositionSide.LONG:
            unrealized_profit = (
                quantity
                * (current_price - entry_price)
            )
        else:
            unrealized_profit = (
                quantity
                * (entry_price - current_price)
            )

        return (
            balance
            + entry_margin
            + unrealized_profit
        )

    def _build_result(
        self,
        *,
        final_balance: float,
        trades: list[Trade],
        equity_curve: Sequence[float],
    ) -> BacktestResult:
        total_profit = (
            final_balance
            - self.initial_balance
        )

        total_return_percent = (
            total_profit
            / self.initial_balance
            * 100
        )

        winning_trade_list = [
            trade
            for trade in trades
            if trade.profit > 0
        ]

        losing_trade_list = [
            trade
            for trade in trades
            if trade.profit < 0
        ]

        winning_trades = len(
            winning_trade_list
        )

        losing_trades = len(
            losing_trade_list
        )

        win_rate_percent = (
            winning_trades
            / len(trades)
            * 100
            if trades
            else 0.0
        )

        max_drawdown_percent = (
            self._calculate_max_drawdown(
                equity_curve
            )
        )

        gross_profit = sum(
            trade.profit
            for trade in winning_trade_list
        )

        gross_loss = abs(
            sum(
                trade.profit
                for trade in losing_trade_list
            )
        )

        if gross_loss > 0:
            profit_factor = (
                gross_profit / gross_loss
            )
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        average_winning_trade_percent = (
            sum(
                trade.profit_percent
                for trade in winning_trade_list
            )
            / len(winning_trade_list)
            if winning_trade_list
            else 0.0
        )

        average_losing_trade_percent = (
            sum(
                trade.profit_percent
                for trade in losing_trade_list
            )
            / len(losing_trade_list)
            if losing_trade_list
            else 0.0
        )

        average_loss_size = abs(
            average_losing_trade_percent
        )

        if average_loss_size > 0:
            payoff_ratio = (
                average_winning_trade_percent
                / average_loss_size
            )
        elif average_winning_trade_percent > 0:
            payoff_ratio = float("inf")
        else:
            payoff_ratio = 0.0

        expectancy_percent = (
            sum(
                trade.profit_percent
                for trade in trades
            )
            / len(trades)
            if trades
            else 0.0
        )

        return BacktestResult(
            initial_balance=self.initial_balance,
            final_balance=final_balance,
            total_profit=total_profit,
            total_return_percent=(
                total_return_percent
            ),
            trades=tuple(trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_percent=win_rate_percent,
            max_drawdown_percent=(
                max_drawdown_percent
            ),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            average_winning_trade_percent=(
                average_winning_trade_percent
            ),
            average_losing_trade_percent=(
                average_losing_trade_percent
            ),
            payoff_ratio=payoff_ratio,
            expectancy_percent=(
                expectancy_percent
            ),
        )

    @staticmethod
    def _calculate_max_drawdown(
        equity_curve: Sequence[float],
    ) -> float:
        if not equity_curve:
            return 0.0

        peak = equity_curve[0]
        max_drawdown = 0.0

        for equity in equity_curve:
            if equity > peak:
                peak = equity

            if peak == 0:
                continue

            drawdown = (
                peak - equity
            ) / peak * 100

            max_drawdown = max(
                max_drawdown,
                drawdown,
            )

        return max_drawdown

    @staticmethod
    def _validate_candle(
        candle: Candle,
    ) -> None:
        prices = [
            candle.open,
            candle.high,
            candle.low,
            candle.close,
        ]

        if any(price <= 0 for price in prices):
            raise ValueError(
                "candle prices must be greater than zero"
            )

        if candle.high < candle.low:
            raise ValueError(
                "candle high price must not be "
                "lower than low price"
            )

        if candle.high < max(
            candle.open,
            candle.close,
        ):
            raise ValueError(
                "candle high price must not be "
                "lower than open or close"
            )

        if candle.low > min(
            candle.open,
            candle.close,
        ):
            raise ValueError(
                "candle low price must not be "
                "higher than open or close"
            )

        if candle.volume < 0:
            raise ValueError(
                "candle volume must not be negative"
            )
