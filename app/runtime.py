from __future__ import annotations

from dataclasses import dataclass

from app.execution import TradeExecutor
from app.execution_config import (
    ExecutionConfig,
    build_execution_config,
)
from app.executor_factory import build_executor
from app.settings import Settings, load_settings


@dataclass(frozen=True, slots=True)
class Runtime:
    settings: Settings
    execution: ExecutionConfig
    executor: TradeExecutor


def build_runtime(
    settings: Settings | None = None,
) -> Runtime:
    if settings is None:
        settings = load_settings()

    execution = build_execution_config(settings)

    executor = build_executor(execution)

    return Runtime(
        settings=settings,
        execution=execution,
        executor=executor,
    )
