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

    required_columns = {"datetime", "open", "close"}

    if not required_columns.issubset(data.columns):
        raise ValueError(
            "Данные должны содержать колонки datetime, open и close"
        )

    if data.empty:
        raise ValueError("Нет данных для тестирования")

    if len(data) != len(signals):
        raise ValueError(
            "Количество сигналов не совпадает с количеством свечей"
        )

    frame = (
        data.copy()
        .sort_values("datetime")
        .reset_index(drop=True)
    )

    signals = signals.reset_index(drop=True)

    valid_signals = {
        int(Signal.SELL),
        int(Signal.HOLD),
        int(Signal.BUY),
    }

    if not set(signals.astype(int).unique()).issubset(valid_signals):
        raise ValueError("Обнаружен неизвестный торговый сигнал")

    balance = float(start_balance)
    asset_quantity = 0.0
    in_position = False

    entry_balance = 0.0
    total_fees = 0.0
    completed_trades = 0
    winning_trades = 0

    trades: list[Trade] = []
    equity_curve: list[float] = [start_balance]

    # Сигнал свечи index - 1 исполняется на открытии свечи index.
    for index in range(1, len(frame)):
        row = frame.iloc[index]
        execution_signal = Signal(int(signals.iloc[index - 1]))

        open_price = float(row["open"])
        close_price = float(row["close"])

        if open_price <= 0 or close_price <= 0:
            raise ValueError("Цена должна быть больше нуля")

        if execution_signal == Signal.BUY and not in_position:
            fee = balance * fee_rate
            purchase_amount = balance - fee

            asset_quantity = purchase_amount / open_price
            entry_balance = balance
            balance = 0.0
            in_position = True
            total_fees += fee

            trades.append(
                Trade(
                    side=TradeSide.BUY,
                    timestamp=row["datetime"].to_pydatetime(),
                    price=open_price,
                    quantity=asset_quantity,
                    fee=fee,
                    balance_after=0.0,
                )
            )

        elif execution_signal == Signal.SELL and in_position:
            gross_value = asset_quantity * open_price
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
                    price=open_price,
                    quantity=asset_quantity,
                    fee=fee,
                    balance_after=balance,
                )
            )

            asset_quantity = 0.0

        if in_position:
            current_equity = (
                asset_quantity
                * close_price
                * (1 - fee_rate)
            )
        else:
            current_equity = balance

        equity_curve.append(current_equity)

    # Незакрытую позицию закрываем по последней цене закрытия.
    if in_position:
        last_row = frame.iloc[-1]
        last_price = float(last_row["close"])

        gross_value = asset_quantity * last_price
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
                quantity=asset_quantity,
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

