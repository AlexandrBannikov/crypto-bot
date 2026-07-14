from collections.abc import Sequence

import pandas as pd


def calculate_return_percent(
    start_balance: float,
    final_balance: float,
) -> float:
    if start_balance <= 0:
        raise ValueError("Стартовый баланс должен быть больше нуля")

    return (final_balance / start_balance - 1) * 100


def calculate_max_drawdown(
    equity_values: Sequence[float],
) -> float:
    if not equity_values:
        return 0.0

    equity = pd.Series(equity_values, dtype="float64")

    if (equity <= 0).any():
        raise ValueError("Значения капитала должны быть больше нуля")

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max

    return float(drawdown.min() * 100)

