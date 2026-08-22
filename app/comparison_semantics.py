"""Shared sign conventions for performance metrics and comparisons."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable


D = Decimal


def max_drawdown_percent(equity_curve: Iterable[Decimal]) -> Decimal:
    """Return peak-to-trough drawdown as a non-negative percentage."""
    peak: Decimal | None = None
    maximum = D("0")
    for raw in equity_curve:
        equity = D(str(raw))
        if equity <= 0:
            raise ValueError("equity values must be greater than zero")
        peak = equity if peak is None else max(peak, equity)
        maximum = max(maximum, (peak - equity) / peak * D("100"))
    return maximum


def candidate_delta(candidate: Decimal, production: Decimal) -> Decimal:
    """Raw metric delta. Positive always means candidate value is larger."""
    return D(str(candidate)) - D(str(production))


def candidate_advantage(
    candidate: Decimal, production: Decimal, *, lower_is_better: bool,
) -> Decimal:
    """Directional delta. Positive always means candidate is better."""
    raw = candidate_delta(candidate, production)
    return -raw if lower_is_better else raw
