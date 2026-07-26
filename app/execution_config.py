from __future__ import annotations

from dataclasses import dataclass

from app.bybit_account import BybitAccountConfig
from app.execution import ExecutionMode
from app.settings import Settings


class ExecutionConfigurationError(ValueError):
    """Небезопасная или неполная конфигурация исполнения."""


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    mode: ExecutionMode
    account: BybitAccountConfig | None
    dry_run: bool

    @property
    def uses_exchange(self) -> bool:
        return self.account is not None

    @property
    def submits_orders(self) -> bool:
        return (
            self.mode == ExecutionMode.LIVE
            and not self.dry_run
        )


def build_execution_config(
    settings: Settings,
) -> ExecutionConfig:
    if settings.execution_mode == ExecutionMode.PAPER:
        return ExecutionConfig(
            mode=ExecutionMode.PAPER,
            account=None,
            dry_run=False,
        )

    api_key = settings.bybit_api_key
    api_secret = settings.bybit_api_secret

    if api_key is None or api_secret is None:
        raise ExecutionConfigurationError(
            "BYBIT_API_KEY and BYBIT_API_SECRET "
            "are required for dry_run and live modes"
        )

    account = BybitAccountConfig(
        api_key=api_key,
        api_secret=api_secret,
        testnet=settings.bybit_testnet,
    )

    if settings.execution_mode == ExecutionMode.DRY_RUN:
        return ExecutionConfig(
            mode=ExecutionMode.DRY_RUN,
            account=account,
            dry_run=True,
        )

    if settings.execution_mode != ExecutionMode.LIVE:
        raise ExecutionConfigurationError(
            "unsupported execution mode"
        )

    if not settings.live_trading_confirmed:
        raise ExecutionConfigurationError(
            "live trading requires "
            "LIVE_TRADING_CONFIRMED=true"
        )

    if (
        not settings.bybit_testnet
        and not settings.bybit_allow_mainnet
    ):
        raise ExecutionConfigurationError(
            "mainnet trading requires "
            "BYBIT_ALLOW_MAINNET=true"
        )

    return ExecutionConfig(
        mode=ExecutionMode.LIVE,
        account=account,
        dry_run=False,
    )
