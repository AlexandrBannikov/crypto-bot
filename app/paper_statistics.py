from collections.abc import Sequence

from app.engine import Trade
from app.models import PaperStatistics


def calculate_statistics(
    *,
    start_balance: float,
    trades: Sequence[Trade],
) -> PaperStatistics:
    if start_balance <= 0:
        raise ValueError(
            "Стартовый баланс должен быть больше нуля"
        )

    profits = [
        trade.profit
        for trade in trades
    ]

    winning_profits = [
        profit
        for profit in profits
        if profit > 0
    ]
    losing_profits = [
        profit
        for profit in profits
        if profit < 0
    ]

    net_profit = sum(profits)
    current_balance = start_balance + net_profit

    total_trades = len(trades)
    winning_trades = len(winning_profits)
    losing_trades = len(losing_profits)

    gross_profit = sum(winning_profits)
    gross_loss = sum(losing_profits)

    win_rate_percent = (
        winning_trades
        / total_trades
        * 100
        if total_trades
        else 0.0
    )

    profit_factor = (
        gross_profit
        / abs(gross_loss)
        if gross_loss < 0
        else 0.0
    )

    average_win = (
        gross_profit
        / winning_trades
        if winning_trades
        else 0.0
    )

    average_loss = (
        gross_loss
        / losing_trades
        if losing_trades
        else 0.0
    )

    return PaperStatistics(
        start_balance=start_balance,
        current_balance=current_balance,
        net_profit=net_profit,
        return_percent=(
            net_profit
            / start_balance
            * 100
        ),
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate_percent=win_rate_percent,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        average_win=average_win,
        average_loss=average_loss,
        max_drawdown_percent=0.0,
    )
