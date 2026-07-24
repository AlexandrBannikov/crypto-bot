from app.order_executor import (
    OrderRequest,
    OrderType,
)
from app.paper_session import PaperPosition
from app.risk import RiskConfig, RiskManager
from app.signal_normalizer import normalize_signal
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_types import (
    PositionSide,
    TradeAction,
)


class OrderPlanner:
    def __init__(
        self,
        *,
        symbol: str,
        risk_config: RiskConfig | None = None,
    ) -> None:
        self.symbol = symbol
        self.risk_manager = RiskManager(risk_config)

    def plan(
        self,
        *,
        signal: Signal | TradeSignal | TradeAction,
        balance: float,
        reference_price: float,
        current_position: PaperPosition | None = None,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
    ) -> OrderRequest | None:
        if balance < 0:
            raise ValueError(
                "balance must not be negative"
            )

        if reference_price <= 0:
            raise ValueError(
                "reference_price must be greater than zero"
            )

        normalized_signal = normalize_signal(signal)
        action = normalized_signal.action

        if action == TradeAction.HOLD:
            return None

        if action in {
            TradeAction.OPEN_LONG,
            TradeAction.OPEN_SHORT,
        }:
            if current_position is not None:
                return None

            if balance <= 0:
                raise ValueError(
                    "balance must be greater than zero "
                    "for open orders"
                )

            side = (
                PositionSide.LONG
                if action == TradeAction.OPEN_LONG
                else PositionSide.SHORT
            )

            quantity = self._calculate_open_quantity(
                balance=balance,
                reference_price=reference_price,
                stop_loss=normalized_signal.stop_loss,
                side=side,
            )

            return OrderRequest.from_trade_action(
                symbol=self.symbol,
                action=action,
                quantity=quantity,
                order_type=order_type,
                price=price,
                stop_loss=normalized_signal.stop_loss,
            )

        if current_position is None:
            return None

        if (
            action == TradeAction.CLOSE_LONG
            and current_position.side
            != PositionSide.LONG
        ):
            return None

        if (
            action == TradeAction.CLOSE_SHORT
            and current_position.side
            != PositionSide.SHORT
        ):
            return None

        return OrderRequest.from_trade_action(
            symbol=self.symbol,
            action=action,
            quantity=current_position.quantity,
            order_type=order_type,
            price=price,
        )

    def _calculate_open_quantity(
        self,
        *,
        balance: float,
        reference_price: float,
        stop_loss: float | None,
        side: PositionSide,
    ) -> float:
        if stop_loss is not None:
            return (
                self.risk_manager
                .calculate_position_size(
                    balance=balance,
                    entry_price=reference_price,
                    stop_loss=stop_loss,
                    side=side,
                )
                .quantity
            )

        position_value = (
            balance
            * self.risk_manager.config.max_position_fraction
            * self.risk_manager.config.leverage
        )

        return position_value / reference_price
