from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from app.engine import Candle, Trade
from app.paper_session import PaperTradingSession
from app.trade_signal import TradeSignal
from app.trading_types import TradeAction


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: float | None = None
    stop_loss: float | None = None
    reduce_only: bool = False

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        object.__setattr__(
            self,
            "symbol",
            normalized_symbol,
        )

        if self.quantity <= 0:
            raise ValueError(
                "quantity must be greater than zero"
            )

        if (
            self.order_type == OrderType.LIMIT
            and self.price is None
        ):
            raise ValueError(
                "price is required for limit orders"
            )

        if self.price is not None and self.price <= 0:
            raise ValueError(
                "price must be greater than zero"
            )

        if (
            self.stop_loss is not None
            and self.stop_loss <= 0
        ):
            raise ValueError(
                "stop_loss must be greater than zero"
            )

    @classmethod
    def from_trade_action(
        cls,
        *,
        symbol: str,
        action: TradeAction,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
        stop_loss: float | None = None,
    ) -> "OrderRequest":
        if action == TradeAction.OPEN_LONG:
            side = OrderSide.BUY
            reduce_only = False
        elif action == TradeAction.CLOSE_LONG:
            side = OrderSide.SELL
            reduce_only = True
        elif action == TradeAction.OPEN_SHORT:
            side = OrderSide.SELL
            reduce_only = False
        elif action == TradeAction.CLOSE_SHORT:
            side = OrderSide.BUY
            reduce_only = True
        else:
            raise ValueError(
                "HOLD cannot be converted to an order"
            )

        return cls(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            reduce_only=reduce_only,
        )


@dataclass(frozen=True, slots=True)
class OrderResult:
    request: OrderRequest
    status: OrderStatus
    order_id: str | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if (
            self.status == OrderStatus.ACCEPTED
            and not self.order_id
        ):
            raise ValueError(
                "order_id is required for accepted orders"
            )

        if (
            self.status == OrderStatus.REJECTED
            and not self.message
        ):
            raise ValueError(
                "message is required for rejected orders"
            )


class DirectOrderExecutor(Protocol):
    def submit_order(
        self,
        request: OrderRequest,
    ) -> OrderResult:
        ...


class OrderExecutor(Protocol):
    def execute_pending_action(
        self,
        candle: Candle,
    ) -> Trade | None:
        ...

    def process_closed_candle(
        self,
        candle: Candle,
    ) -> Trade | None:
        ...

    def queue_signal(
        self,
        *,
        signal: TradeSignal,
        reference_price: float,
    ) -> None:
        ...


class DryRunOrderExecutor:
    def __init__(self) -> None:
        self._orders: list[OrderRequest] = []
        self._results: list[OrderResult] = []
        self._next_order_number = 1

    @property
    def orders(self) -> tuple[OrderRequest, ...]:
        return tuple(self._orders)

    @property
    def results(self) -> tuple[OrderResult, ...]:
        return tuple(self._results)

    def submit_order(
        self,
        request: OrderRequest,
    ) -> OrderResult:
        order_id = (
            f"dry-run-{self._next_order_number}"
        )
        self._next_order_number += 1

        result = OrderResult(
            request=request,
            status=OrderStatus.ACCEPTED,
            order_id=order_id,
            message=(
                "Dry run only: order was not sent "
                "to an exchange"
            ),
        )

        self._orders.append(request)
        self._results.append(result)

        return result


class PaperOrderExecutor:
    def __init__(
        self,
        session: PaperTradingSession,
    ) -> None:
        self.session = session

    def execute_pending_action(
        self,
        candle: Candle,
    ) -> Trade | None:
        return self.session.execute_pending_action(
            candle
        )

    def process_closed_candle(
        self,
        candle: Candle,
    ) -> Trade | None:
        return self.session.process_closed_candle(
            candle
        )

    def queue_signal(
        self,
        *,
        signal: TradeSignal,
        reference_price: float,
    ) -> None:
        self.session.queue_action(
            action=signal.action,
            reference_price=reference_price,
            stop_loss=signal.stop_loss,
            trailing_stop_percent=(
                signal.trailing_stop_percent
            ),
        )
