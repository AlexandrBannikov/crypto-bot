import pytest

from app.metrics import (
    calculate_max_drawdown,
    calculate_return_percent,
)


def test_calculate_positive_return():
    assert calculate_return_percent(1000, 1100) == pytest.approx(10.0)


def test_calculate_negative_return():
    assert calculate_return_percent(1000, 900) == pytest.approx(-10.0)


def test_start_balance_error():
    with pytest.raises(ValueError):
        calculate_return_percent(0, 100)


def test_drawdown():
    equity = [1000, 1100, 990, 1200]
    assert calculate_max_drawdown(equity) == pytest.approx(10.0)


def test_drawdown_zero():
    equity = [1000, 1100, 1200]
    assert calculate_max_drawdown(equity) == pytest.approx(0.0)


def test_drawdown_empty():
    assert calculate_max_drawdown([]) == 0.0
