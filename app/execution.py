from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

from app.trading_types import PositionSide


class ExecutionMode(str, Enum):
    DRY_RUN = "dry_run"
    PAPER = "paper"
    LIVE = "live"


class ExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    CANCELED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    symbol: str
    side: PositionSide
    quantity: Decimal
    price: Decimal
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        if self.quantity <= 0:
            raise ValueError(
                "quantity must be greater than zero"
            )

        if self.price <= 0:
            raise ValueError(
                "price must be greater than zero"
            )

        if self.client_order_id is not None:
            normalized_client_order_id = (
                self.client_order_id.strip()
            )

            if not normalized_client_order_id:
                raise ValueError(
                    "client_order_id must not be empty"
                )

            object.__setattr__(
                self,
                "client_order_id",
                normalized_client_order_id,
            )

        object.__setattr__(
            self,
            "symbol",
            normalized_symbol,
        )


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    mode: ExecutionMode
    status: ExecutionStatus
    symbol: str
    side: PositionSide
    requested_quantity: Decimal
    requested_price: Decimal
    executed_quantity: Decimal = Decimal("0")
    average_price: Decimal | None = None
    order_id: str | None = None
    client_order_id: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        if self.requested_quantity <= 0:
            raise ValueError(
                "requested_quantity must be greater than zero"
            )

        if self.requested_price <= 0:
            raise ValueError(
                "requested_price must be greater than zero"
            )

        if self.executed_quantity < 0:
            raise ValueError(
                "executed_quantity must not be negative"
            )

        if self.executed_quantity > self.requested_quantity:
            raise ValueError(
                "executed_quantity must not exceed "
                "requested_quantity"
            )

        if (
            self.average_price is not None
            and self.average_price <= 0
        ):
            raise ValueError(
                "average_price must be greater than zero"
            )

        if (
            self.executed_quantity > 0
            and self.average_price is None
        ):
            raise ValueError(
                "average_price is required when "
                "executed_quantity is greater than zero"
            )

        if self.order_id is not None:
            normalized_order_id = self.order_id.strip()

            if not normalized_order_id:
                raise ValueError(
                    "order_id must not be empty"
                )

            object.__setattr__(
                self,
                "order_id",
                normalized_order_id,
            )

        if self.client_order_id is not None:
            normalized_client_order_id = (
                self.client_order_id.strip()
            )

            if not normalized_client_order_id:
                raise ValueError(
                    "client_order_id must not be empty"
                )

            object.__setattr__(
                self,
                "client_order_id",
                normalized_client_order_id,
            )

        object.__setattr__(
            self,
            "symbol",
            normalized_symbol,
        )

    @property
    def is_successful(self) -> bool:
        return self.status not in {
            ExecutionStatus.REJECTED,
            ExecutionStatus.FAILED,
        }

    @property
    def is_complete(self) -> bool:
        return self.status in {
            ExecutionStatus.FILLED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.REJECTED,
            ExecutionStatus.FAILED,
        }


@runtime_checkable
class TradeExecutor(Protocol):
    @property
    def mode(self) -> ExecutionMode:
        ...

    def open_position(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        ...

    def close_position(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        ...

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> ExecutionResult:
        ...

    def get_order_status(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> ExecutionResult:
        ...
