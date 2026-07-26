from app.execution import (
    ExecutionMode,
    TradeExecutor,
)
from app.paper_executor import PaperExecutor
from app.runtime import build_runtime
from app.settings import Settings


def make_settings() -> Settings:
    return Settings(
        execution_mode=ExecutionMode.PAPER,
        bybit_api_key=None,
        bybit_api_secret=None,
        bybit_testnet=False,
        live_trading_confirmed=False,
        bybit_allow_mainnet=False,
    )


def test_build_runtime_returns_runtime() -> None:
    runtime = build_runtime(make_settings())

    assert runtime.settings.execution_mode == ExecutionMode.PAPER
    assert runtime.execution.mode == ExecutionMode.PAPER
    assert isinstance(runtime.executor, TradeExecutor)
    assert isinstance(runtime.executor, PaperExecutor)


def test_runtime_uses_same_settings_instance() -> None:
    settings = make_settings()

    runtime = build_runtime(settings)

    assert runtime.settings is settings


def test_runtime_executor_mode_matches_execution_mode() -> None:
    runtime = build_runtime(make_settings())

    assert runtime.executor.mode == runtime.execution.mode
