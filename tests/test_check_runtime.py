from app.execution import ExecutionMode
from app.runtime import build_runtime
from app.settings import Settings
from scripts.check_runtime import summarize_runtime


def make_paper_settings() -> Settings:
    return Settings(
        execution_mode=ExecutionMode.PAPER,
        bybit_api_key=None,
        bybit_api_secret=None,
        bybit_testnet=False,
        live_trading_confirmed=False,
        bybit_allow_mainnet=False,
    )


def test_summarizes_paper_runtime() -> None:
    runtime = build_runtime(make_paper_settings())

    summary = summarize_runtime(runtime)

    assert summary.execution_mode == ExecutionMode.PAPER
    assert summary.executor_type == "PaperExecutor"
    assert summary.uses_exchange is False
    assert summary.dry_run is False
    assert summary.submits_orders is False
    assert summary.testnet is None


def test_summary_does_not_contain_credentials() -> None:
    runtime = build_runtime(make_paper_settings())

    summary = summarize_runtime(runtime)

    assert not hasattr(summary, "api_key")
    assert not hasattr(summary, "api_secret")


def test_summary_mode_matches_executor() -> None:
    runtime = build_runtime(make_paper_settings())

    summary = summarize_runtime(runtime)

    assert summary.execution_mode == runtime.executor.mode
