import os

import pytest

from app.execution import ExecutionMode
from app.settings import load_settings


@pytest.fixture(autouse=True)
def clear_environment():
    keys = [
        "EXECUTION_MODE",
        "BYBIT_API_KEY",
        "BYBIT_API_SECRET",
        "BYBIT_TESTNET",
        "LIVE_TRADING_CONFIRMED",
    ]

    previous = {
        key: os.environ.get(key)
        for key in keys
    }

    for key in keys:
        os.environ.pop(key, None)

    yield

    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_defaults():
    settings = load_settings()

    assert settings.execution_mode == ExecutionMode.PAPER
    assert settings.bybit_api_key is None
    assert settings.bybit_api_secret is None
    assert settings.bybit_testnet is False
    assert settings.live_trading_confirmed is False


def test_environment_loading():
    os.environ["EXECUTION_MODE"] = "dry_run"
    os.environ["BYBIT_API_KEY"] = "key"
    os.environ["BYBIT_API_SECRET"] = "secret"
    os.environ["BYBIT_TESTNET"] = "true"
    os.environ["LIVE_TRADING_CONFIRMED"] = "1"

    settings = load_settings()

    assert settings.execution_mode == ExecutionMode.DRY_RUN
    assert settings.bybit_api_key == "key"
    assert settings.bybit_api_secret == "secret"
    assert settings.bybit_testnet is True
    assert settings.live_trading_confirmed is True


def test_invalid_execution_mode():
    os.environ["EXECUTION_MODE"] = "invalid"

    with pytest.raises(ValueError):
        load_settings()
