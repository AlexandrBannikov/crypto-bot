from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.execution import ExecutionResult
from app.execution_runner import (
    ExecutionCommand,
    ExecutionRunner,
)
from app.signal_normalizer import normalize_signal
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_types import TradeAction


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    symbol: str
    signal: Signal | TradeSignal | TradeAction
    quantity: Decimal
    price: Decimal
    client_order_id: str | None = None


class TradingRuntime:
    """
    Соединяет сигнал торговой стратегии с ExecutionRunner.

    Runtime:
    - нормализует Signal, TradeSignal или TradeAction;
    - создаёт ExecutionCommand;
    - передаёт команду на исполнение.
    """

    def __init__(
        self,
        runner: ExecutionRunner,
    ) -> None:
        self.runner = runner

    def process_signal(
        self,
        request: RuntimeRequest,
    ) -> ExecutionResult | None:
        normalized_signal = normalize_signal(
            request.signal
        )

        action = normalized_signal.action

        if not isinstance(action, TradeAction):
            raise TypeError(
                "normalized signal action must be TradeAction"
            )

        command = ExecutionCommand(
            symbol=request.symbol,
            action=action,
            quantity=request.quantity,
            price=request.price,
            client_order_id=request.client_order_id,
        )

        return self.runner.execute(command)
