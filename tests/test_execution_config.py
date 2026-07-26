import pytest

from app.execution import ExecutionMode
from app.execution_config import (
    ExecutionConfigurationError,
    build_execution_config,
)
from app.settings import Settings


def make_settings(
    *,
    mode: ExecutionMode,
    api_key: str | None = "key",
    api_secret: str | None = "secret",
    testnet: bool = True,
    confirmed: bool = False,
    allow_mainnet: bool = False,
) -> Settings:
    return Settings(
        execution_mode=mode,
        bybit_api_key=api_key,
        bybit_api_secret=api_secret,
        bybit_testnet=testnet,
        live_trading_confirmed=confirmed,
        bybit_allow_mainnet=allow_mainnet,
    )


def test_paper_mode_does_not_require_credentials() -> None:
    config = build_execution_config(
        make_settings(
            mode=ExecutionMode.PAPER,
            api_key=None,
            api_secret=None,
        )
    )

    assert config.mode == ExecutionMode.PAPER
    assert config.account is None
    assert config.dry_run is False
    assert config.uses_exchange is False
    assert config.submits_orders is False


def test_dry_run_builds_testnet_account() -> None:
    config = build_execution_config(
        make_settings(
            mode=ExecutionMode.DRY_RUN,
            testnet=True,
        )
    )

    assert config.mode == ExecutionMode.DRY_RUN
    assert config.account is not None
    assert config.account.api_key == "key"
    assert config.account.api_secret == "secret"
    assert config.account.testnet is True
    assert config.dry_run is True
    assert config.uses_exchange is True
    assert config.submits_orders is False


@pytest.mark.parametrize(
    ("api_key", "api_secret"),
    [
        (None, "secret"),
        ("key", None),
        (None, None),
    ],
)
def test_exchange_modes_require_both_credentials(
    api_key: str | None,
    api_secret: str | None,
) -> None:
    with pytest.raises(
        ExecutionConfigurationError,
        match="BYBIT_API_KEY and BYBIT_API_SECRET",
    ):
        build_execution_config(
            make_settings(
                mode=ExecutionMode.DRY_RUN,
                api_key=api_key,
                api_secret=api_secret,
            )
        )


def test_live_requires_explicit_confirmation() -> None:
    with pytest.raises(
        ExecutionConfigurationError,
        match="LIVE_TRADING_CONFIRMED=true",
    ):
        build_execution_config(
            make_settings(
                mode=ExecutionMode.LIVE,
                confirmed=False,
            )
        )


def test_live_testnet_is_allowed_after_confirmation() -> None:
    config = build_execution_config(
        make_settings(
            mode=ExecutionMode.LIVE,
            testnet=True,
            confirmed=True,
        )
    )

    assert config.mode == ExecutionMode.LIVE
    assert config.account is not None
    assert config.account.testnet is True
    assert config.dry_run is False
    assert config.submits_orders is True


def test_live_mainnet_requires_separate_permission() -> None:
    with pytest.raises(
        ExecutionConfigurationError,
        match="BYBIT_ALLOW_MAINNET=true",
    ):
        build_execution_config(
            make_settings(
                mode=ExecutionMode.LIVE,
                testnet=False,
                confirmed=True,
                allow_mainnet=False,
            )
        )


def test_live_mainnet_requires_two_confirmations() -> None:
    config = build_execution_config(
        make_settings(
            mode=ExecutionMode.LIVE,
            testnet=False,
            confirmed=True,
            allow_mainnet=True,
        )
    )

    assert config.account is not None
    assert config.account.testnet is False
    assert config.submits_orders is True
