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

    net_profit = sum(
        trade.profit
        for trade in trades
    )
    current_balance = start_balance + net_profit

    winning_trades = sum(
        trade.profit > 0
        for trade in trades
    )
    losing_trades = sum(
        trade.profit < 0
        for trade in trades
    )
    total_trades = len(trades)

    win_rate_percent = (
        winning_trades
        / total_trades
        * 100
        if total_trades
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
        gross_profit=0.0,
        gross_loss=0.0,
        profit_factor=0.0,
        average_win=0.0,
        average_loss=0.0,
        max_drawdown_percent=0.0,
    )
