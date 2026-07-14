from dataclasses import dataclass
from typing import Protocol, Sequence

from app.strategies import Signal


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


class Strategy(Protocol):
    def generate_signal(
        self,
        candles: Sequence[Candle],
        index: int,
    ) -> Signal:
        ...


class BacktestEngine:
    def __init__(
        self,
        initial_balance: float = 10_000.0,
        commission_rate: float = 0.001,
    ) -> None:
        if initial_balance <= 0:
            raise ValueError("initial_balance must be greater than zero")

        if not 0 <= commission_rate < 1:
            raise ValueError(
                "commission_rate must be greater than or equal to zero "
                "and less than one"
            )

        self.initial_balance = initial_balance
        self.commission_rate = commission_rate

    def run(
        self,
        candles: Sequence[Candle],
        strategy: Strategy,
    ) -> BacktestResult:
        if not candles:
            raise ValueError("candles must not be empty")

        balance = self.initial_balance
        quantity = 0.0

        entry_timestamp: int | None = None
        entry_price: float | None = None
        entry_fee = 0.0
        entry_cost = 0.0

        pending_signal = Signal.HOLD

        trades: list[Trade] = []
        equity_curve: list[float] = [self.initial_balance]

        for index, candle in enumerate(candles):
            self._validate_candle(candle)

            # Сигнал предыдущей свечи исполняется
            # на открытии текущей свечи.
            if pending_signal == Signal.BUY and quantity == 0:
                entry_price = candle.open
                entry_timestamp = candle.timestamp

                entry_fee = balance * self.commission_rate
                entry_cost = balance

                available_for_position = balance - entry_fee
                quantity = available_for_position / entry_price
                balance = 0.0

            elif pending_signal == Signal.SELL and quantity > 0:
                assert entry_price is not None
                assert entry_timestamp is not None

                execution_candle = Candle(
                    timestamp=candle.timestamp,
                    open=candle.open,
                    high=candle.open,
                    low=candle.open,
                    close=candle.open,
                    volume=candle.volume,
                )

                balance, trade = self._close_position(
                    quantity=quantity,
                    exit_candle=execution_candle,
                    entry_timestamp=entry_timestamp,
                    entry_price=entry_price,
                    entry_fee=entry_fee,
                    entry_cost=entry_cost,
                )

                trades.append(trade)

                quantity = 0.0
                entry_timestamp = None
                entry_price = None
                entry_fee = 0.0
                entry_cost = 0.0

            signal = strategy.generate_signal(candles, index)

            if signal == Signal.BUY and quantity == 0:
                pending_signal = Signal.BUY
            elif signal == Signal.SELL and quantity > 0:
                pending_signal = Signal.SELL
            else:
                pending_signal = Signal.HOLD

            equity = balance + quantity * candle.close
            equity_curve.append(equity)

        # Если позиция осталась открытой, закрываем её
        # по close последней доступной свечи.
        if quantity > 0:
            last_candle = candles[-1]

            assert entry_price is not None
            assert entry_timestamp is not None

            balance, trade = self._close_position(
                quantity=quantity,
                exit_candle=last_candle,
                entry_timestamp=entry_timestamp,
                entry_price=entry_price,
                entry_fee=entry_fee,
                entry_cost=entry_cost,
            )

            trades.append(trade)
            equity_curve.append(balance)

        return self._build_result(
            final_balance=balance,
            trades=trades,
            equity_curve=equity_curve,
        )

    def _close_position(
        self,
        *,
        quantity: float,
        exit_candle: Candle,
        entry_timestamp: int,
        entry_price: float,
        entry_fee: float,
        entry_cost: float,
    ) -> tuple[float, Trade]:
        gross_exit_value = quantity * exit_candle.close
        exit_fee = gross_exit_value * self.commission_rate
        final_value = gross_exit_value - exit_fee

        profit = final_value - entry_cost
        profit_percent = (
            profit / entry_cost * 100
            if entry_cost > 0
            else 0.0
        )

        trade = Trade(
            entry_timestamp=entry_timestamp,
            exit_timestamp=exit_candle.timestamp,
            entry_price=entry_price,
            exit_price=exit_candle.close,
            quantity=quantity,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            profit=profit,
            profit_percent=profit_percent,
        )

        return final_value, trade

    def _build_result(
        self,
        *,
        final_balance: float,
        trades: list[Trade],
        equity_curve: Sequence[float],
    ) -> BacktestResult:
        total_profit = final_balance - self.initial_balance
        total_return_percent = (
            total_profit / self.initial_balance * 100
        )

        winning_trades = sum(
            trade.profit > 0
            for trade in trades
        )
        losing_trades = sum(
            trade.profit < 0
            for trade in trades
        )

        win_rate_percent = (
            winning_trades / len(trades) * 100
            if trades
            else 0.0
        )

        max_drawdown_percent = self._calculate_max_drawdown(
            equity_curve
        )

        return BacktestResult(
            initial_balance=self.initial_balance,
            final_balance=final_balance,
            total_profit=total_profit,
            total_return_percent=total_return_percent,
            trades=tuple(trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_percent=win_rate_percent,
            max_drawdown_percent=max_drawdown_percent,
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

            drawdown = (peak - equity) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    @staticmethod
    def _validate_candle(candle: Candle) -> None:
        if candle.close <= 0:
            raise ValueError("candle close price must be greater than zero")

        if candle.high < candle.low:
            raise ValueError(
                "candle high price must not be lower than low price"
            )

        if candle.volume < 0:
            raise ValueError(
                "candle volume must not be negative"
            )

