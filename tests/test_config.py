import pytest

from app.config import BacktestConfig, DEFAULT_CONFIG


def test_default_config() -> None:
    assert DEFAULT_CONFIG.symbol == "ETH/USDT"
    assert DEFAULT_CONFIG.timeframe == "1h"
    assert DEFAULT_CONFIG.start_balance == 1000.0
    assert DEFAULT_CONFIG.fee_rate == 0.001


def test_custom_config() -> None:
    config = BacktestConfig(
        symbol="ETH/USDT",
        timeframe="4h",
        start_balance=500.0,
        fee_rate=0.0005,
    )

    assert config.timeframe == "4h"
    assert config.start_balance == 500.0
    assert config.fee_rate == 0.0005


@pytest.mark.parametrize(
    "start_balance",
    [0.0, -1.0],
)
def test_invalid_start_balance(
    start_balance: float,
) -> None:
    with pytest.raises(ValueError):
        BacktestConfig(start_balance=start_balance)


@pytest.mark.parametrize(
    "fee_rate",
    [-0.001, 1.0, 2.0],
)
def test_invalid_fee_rate(
    fee_rate: float,
) -> None:
    with pytest.raises(ValueError):
        BacktestConfig(fee_rate=fee_rate)


def test_empty_symbol() -> None:
    with pytest.raises(ValueError):
        BacktestConfig(symbol="   ")


def test_empty_timeframe() -> None:
    with pytest.raises(ValueError):
        BacktestConfig(timeframe="")

