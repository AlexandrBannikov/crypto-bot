from dataclasses import dataclass

import pandas as pd

from app.metrics import (
    calculate_max_drawdown,
    calculate_return_percent,
)
from app.models import BacktestResult, Trade, TradeSide
from app.strategies import Signal


def run_backtest(
    data: pd.DataFrame,
    signals: pd.Series,
    start_balance: float = 1000.0,
    fee_rate: float = 0.001,
) -> BacktestResult:
    if start_balance <= 0:
        raise ValueError("Стартовый баланс должен быть больше нуля")

    if not 0 <= fee_rate < 1:
        raise ValueError("Некорректная комиссия")

    required_columns = {"datetime", "close"}

    if not required_columns.issubset(data.columns):
        raise ValueError(
            "Данные должны содержать колонки datetime и close"
        )

    if len(data) != len(signals):
        raise ValueError(
            "Количество сигналов не совпадает с количеством свечей"
        )

    if data.empty:
        raise ValueError("Нет данных для тестирования")

    frame = data.copy()
    frame = frame.sort_values("datetime").reset_index(drop=True)

    signals = signals.reset_index(drop=True)

    balance = float(start_balance)
    eth_quantity = 0.0
    in_position = False

    entry_balance = 0.0
    total_fees = 0.0
    completed_trades = 0
    winning_trades = 0

    trades: list[Trade] = []
    equity_curve: list[float] = [start_balance]

    for index, row in frame.iterrows():
        price = float(row["close"])
        signal = Signal(int(signals.iloc[index]))

        if signal == Signal.BUY and not in_position:
            fee = balance * fee_rate
            purchase_amount = balance - fee

            eth_quantity = purchase_amount / price
            entry_balance = balance
            balance = 0.0
            in_position = True
            total_fees += fee

            trades.append(
                Trade(
                    side=TradeSide.BUY,
                    timestamp=row["datetime"].to_pydatetime(),
                    price=price,
                    quantity=eth_quantity,
                    fee=fee,
                    balance_after=0.0,
                )
            )

        elif signal == Signal.SELL and in_position:
            gross_value = eth_quantity * price
            fee = gross_value * fee_rate
            balance = gross_value - fee
            total_fees += fee

            if balance > entry_balance:
                winning_trades += 1

            completed_trades += 1
            in_position = False

            trades.append(
                Trade(
                    side=TradeSide.SELL,
                    timestamp=row["datetime"].to_pydatetime(),
                    price=price,
                    quantity=eth_quantity,
                    fee=fee,
                    balance_after=balance,
                )
            )

            eth_quantity = 0.0

        if in_position:
            current_equity = (
                eth_quantity
                * price
                * (1 - fee_rate)
            )
        else:
            current_equity = balance

        equity_curve.append(current_equity)

    if in_position:
        last_row = frame.iloc[-1]
        last_price = float(last_row["close"])

        gross_value = eth_quantity * last_price
        fee = gross_value * fee_rate
        balance = gross_value - fee
        total_fees += fee

        if balance > entry_balance:
            winning_trades += 1

        completed_trades += 1

        trades.append(
            Trade(
                side=TradeSide.SELL,
                timestamp=last_row["datetime"].to_pydatetime(),
                price=last_price,
                quantity=eth_quantity,
                fee=fee,
                balance_after=balance,
            )
        )

        equity_curve.append(balance)

    final_balance = balance

    win_rate_percent = (
        winning_trades / completed_trades * 100
        if completed_trades
        else 0.0
    )

    return BacktestResult(
        start_balance=start_balance,
        final_balance=final_balance,
        return_percent=calculate_return_percent(
            start_balance,
            final_balance,
        ),
        max_drawdown_percent=calculate_max_drawdown(
            equity_curve
        ),
        total_fees=total_fees,
        operations=len(trades),
        completed_trades=completed_trades,
        winning_trades=winning_trades,
        win_rate_percent=win_rate_percent,
        trades=trades,
    )

