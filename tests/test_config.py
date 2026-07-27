import pytest

from app.config import (
    BacktestConfig,
    DEFAULT_CONFIG,
    PaperStrategyConfig,
    PaperStrategyMode,
)


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


def test_default_paper_strategy_mode_is_baseline(
    monkeypatch,
) -> None:
    monkeypatch.delenv("PAPER_STRATEGY_MODE", raising=False)

    config = PaperStrategyConfig.from_env()

    assert config.mode is PaperStrategyMode.BASELINE


def test_cli_mode_override_has_priority(monkeypatch) -> None:
    monkeypatch.setenv("PAPER_STRATEGY_MODE", "filtered")

    config = PaperStrategyConfig.from_env(
        mode_override="shadow"
    )

    assert config.mode is PaperStrategyMode.SHADOW


def test_invalid_paper_strategy_mode_is_rejected(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PAPER_STRATEGY_MODE", "live")

    with pytest.raises(ValueError, match="invalid PAPER_STRATEGY_MODE"):
        PaperStrategyConfig.from_env()


def test_invalid_direct_paper_strategy_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="mode must be"):
        PaperStrategyConfig(mode="live")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("REGIME_ADX_PERIOD", "0"),
        ("REGIME_ATR_PERIOD", "-1"),
        ("REGIME_ADX_THRESHOLD", "nan"),
        ("REGIME_LOW_VOLATILITY_THRESHOLD", "0.03"),
        ("REGIME_MINIMUM_CONFIDENCE", "1.1"),
    ],
)
def test_invalid_regime_environment_is_rejected(
    monkeypatch,
    name,
    value,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        PaperStrategyConfig.from_env()


def test_shadow_path_required_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("SHADOW_DIAGNOSTICS_ENABLED", "true")
    monkeypatch.setenv("SHADOW_DIAGNOSTICS_PATH", " ")

    with pytest.raises(ValueError, match="must not be empty"):
        PaperStrategyConfig.from_env()
