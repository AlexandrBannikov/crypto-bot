from app.bybit_account import BybitAccountConfig
from app.bybit_executor import BybitExecutor
from app.execution import ExecutionMode, TradeExecutor
from app.execution_config import ExecutionConfig
from app.executor_factory import build_executor
from app.paper_executor import PaperExecutor

import pytest


class FakeBybitOrderClient:
    def __init__(
        self,
        account: BybitAccountConfig,
    ) -> None:
        self.config = account


def make_account(
    *,
    testnet: bool = True,
) -> BybitAccountConfig:
    return BybitAccountConfig(
        api_key="key",
        api_secret="secret",
        testnet=testnet,
    )


def test_builds_paper_executor() -> None:
    executor = build_executor(
        ExecutionConfig(
            mode=ExecutionMode.PAPER,
            account=None,
            dry_run=False,
        )
    )

    assert isinstance(executor, TradeExecutor)
    assert isinstance(executor, PaperExecutor)
    assert executor.mode == ExecutionMode.PAPER


def test_builds_dry_run_bybit_executor() -> None:
    account = make_account()
    received_accounts = []

    def client_factory(
        supplied_account: BybitAccountConfig,
    ):
        received_accounts.append(supplied_account)
        return FakeBybitOrderClient(supplied_account)

    executor = build_executor(
        ExecutionConfig(
            mode=ExecutionMode.DRY_RUN,
            account=account,
            dry_run=True,
        ),
        bybit_client_factory=client_factory,
    )

    assert isinstance(executor, TradeExecutor)
    assert isinstance(executor, BybitExecutor)
    assert executor.mode == ExecutionMode.DRY_RUN
    assert executor.dry_run is True
    assert executor.client.config is account
    assert received_accounts == [account]


def test_builds_live_bybit_executor() -> None:
    account = make_account()

    executor = build_executor(
        ExecutionConfig(
            mode=ExecutionMode.LIVE,
            account=account,
            dry_run=False,
        ),
        bybit_client_factory=FakeBybitOrderClient,
    )

    assert isinstance(executor, TradeExecutor)
    assert isinstance(executor, BybitExecutor)
    assert executor.mode == ExecutionMode.LIVE
    assert executor.dry_run is False
    assert executor.client.config is account


def test_paper_mode_rejects_exchange_account() -> None:
    with pytest.raises(
        ValueError,
        match="paper execution must not have",
    ):
        build_executor(
            ExecutionConfig(
                mode=ExecutionMode.PAPER,
                account=make_account(),
                dry_run=False,
            )
        )


@pytest.mark.parametrize(
    "mode",
    [
        ExecutionMode.DRY_RUN,
        ExecutionMode.LIVE,
    ],
)
def test_exchange_modes_require_account(
    mode: ExecutionMode,
) -> None:
    with pytest.raises(
        ValueError,
        match="exchange execution requires",
    ):
        build_executor(
            ExecutionConfig(
                mode=mode,
                account=None,
                dry_run=(
                    mode == ExecutionMode.DRY_RUN
                ),
            )
        )


def test_dry_run_mode_requires_dry_run_flag() -> None:
    with pytest.raises(
        ValueError,
        match="dry_run execution mode requires",
    ):
        build_executor(
            ExecutionConfig(
                mode=ExecutionMode.DRY_RUN,
                account=make_account(),
                dry_run=False,
            ),
            bybit_client_factory=FakeBybitOrderClient,
        )


def test_live_mode_rejects_dry_run_flag() -> None:
    with pytest.raises(
        ValueError,
        match="live execution mode requires",
    ):
        build_executor(
            ExecutionConfig(
                mode=ExecutionMode.LIVE,
                account=make_account(),
                dry_run=True,
            ),
            bybit_client_factory=FakeBybitOrderClient,
        )
