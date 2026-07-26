from __future__ import annotations

from dataclasses import dataclass

from app.execution import ExecutionMode
from app.runtime import Runtime, build_runtime


@dataclass(frozen=True, slots=True)
class RuntimeSummary:
    execution_mode: ExecutionMode
    executor_type: str
    uses_exchange: bool
    dry_run: bool
    submits_orders: bool
    testnet: bool | None


def summarize_runtime(runtime: Runtime) -> RuntimeSummary:
    account = runtime.execution.account

    return RuntimeSummary(
        execution_mode=runtime.execution.mode,
        executor_type=type(runtime.executor).__name__,
        uses_exchange=runtime.execution.uses_exchange,
        dry_run=runtime.execution.dry_run,
        submits_orders=runtime.execution.submits_orders,
        testnet=(
            account.testnet
            if account is not None
            else None
        ),
    )


def main() -> None:
    runtime = build_runtime()
    summary = summarize_runtime(runtime)

    print(
        "Режим исполнения:",
        summary.execution_mode.value,
    )
    print(
        "Исполнитель:",
        summary.executor_type,
    )
    print(
        "Подключение к бирже:",
        "да" if summary.uses_exchange else "нет",
    )
    print(
        "Dry-run:",
        "да" if summary.dry_run else "нет",
    )
    print(
        "Возможна отправка ордеров:",
        "да" if summary.submits_orders else "нет",
    )

    if summary.testnet is None:
        print("Среда Bybit: не используется")
    else:
        print(
            "Среда Bybit:",
            "testnet" if summary.testnet else "mainnet",
        )

    print("Проверка Runtime выполнена.")
    print("Ордера не отправлялись.")


if __name__ == "__main__":
    main()
