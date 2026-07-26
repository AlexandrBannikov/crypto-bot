from __future__ import annotations

from collections.abc import Callable

from app.bybit_account import BybitAccountConfig
from app.bybit_executor import BybitExecutor
from app.bybit_orders import BybitOrderClient
from app.execution import ExecutionMode, TradeExecutor
from app.execution_config import ExecutionConfig
from app.paper_executor import PaperExecutor


def build_executor(
    config: ExecutionConfig,
    *,
    bybit_client_factory: Callable[
        [BybitAccountConfig],
        BybitOrderClient,
    ] = BybitOrderClient,
) -> TradeExecutor:
    if config.mode == ExecutionMode.PAPER:
        if config.account is not None:
            raise ValueError(
                "paper execution must not have "
                "a Bybit account"
            )

        return PaperExecutor()

    if config.account is None:
        raise ValueError(
            "exchange execution requires "
            "a Bybit account"
        )

    client = bybit_client_factory(config.account)

    if config.mode == ExecutionMode.DRY_RUN:
        if not config.dry_run:
            raise ValueError(
                "dry_run execution mode requires "
                "dry_run=True"
            )

        return BybitExecutor(
            client,
            dry_run=True,
        )

    if config.mode == ExecutionMode.LIVE:
        if config.dry_run:
            raise ValueError(
                "live execution mode requires "
                "dry_run=False"
            )

        return BybitExecutor(
            client,
            dry_run=False,
        )

    raise ValueError(
        f"unsupported execution mode: {config.mode}"
    )
