from dataclasses import dataclass

from app.trading_types import PositionSide


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """
    Настройки управления риском.

    risk_per_trade:
        Доля капитала, которой разрешено рискнуть в одной сделке.
        0.01 означает 1%.

    max_position_fraction:
        Максимальная доля собственного капитала, которую можно
        использовать для позиции до применения плеча.
        1.0 означает 100% капитала.

    leverage:
        Максимально разрешённое кредитное плечо.
        1.0 означает торговлю без плеча.
    """

    risk_per_trade: float = 0.01
    max_position_fraction: float = 1.0
    leverage: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= 1:
            raise ValueError(
                "risk_per_trade must be greater than zero "
                "and less than or equal to one"
            )

        if not 0 < self.max_position_fraction <= 1:
            raise ValueError(
                "max_position_fraction must be greater than zero "
                "and less than or equal to one"
            )

        if self.leverage < 1:
            raise ValueError(
                "leverage must be greater than or equal to one"
            )


@dataclass(frozen=True, slots=True)
class PositionSize:
    quantity: float
    position_value: float
    capital_used: float
    risk_amount: float
    stop_distance: float
    stop_distance_percent: float


class RiskManager:
    def __init__(
        self,
        config: RiskConfig | None = None,
    ) -> None:
        self.config = config or RiskConfig()

    def calculate_position_size(
        self,
        *,
        balance: float,
        entry_price: float,
        stop_loss: float,
        side: PositionSide,
    ) -> PositionSize:
        self._validate_inputs(
            balance=balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            side=side,
        )

        stop_distance = abs(entry_price - stop_loss)
        stop_distance_percent = stop_distance / entry_price

        risk_amount = balance * self.config.risk_per_trade

        position_value_by_risk = (
            risk_amount / stop_distance_percent
        )

        maximum_capital = (
            balance * self.config.max_position_fraction
        )

        maximum_position_value = (
            maximum_capital * self.config.leverage
        )

        position_value = min(
            position_value_by_risk,
            maximum_position_value,
        )

        quantity = position_value / entry_price
        capital_used = position_value / self.config.leverage

        return PositionSize(
            quantity=quantity,
            position_value=position_value,
            capital_used=capital_used,
            risk_amount=(
                position_value * stop_distance_percent
            ),
            stop_distance=stop_distance,
            stop_distance_percent=stop_distance_percent,
        )

    @staticmethod
    def _validate_inputs(
        *,
        balance: float,
        entry_price: float,
        stop_loss: float,
        side: PositionSide,
    ) -> None:
        if balance <= 0:
            raise ValueError(
                "balance must be greater than zero"
            )

        if entry_price <= 0:
            raise ValueError(
                "entry_price must be greater than zero"
            )

        if stop_loss <= 0:
            raise ValueError(
                "stop_loss must be greater than zero"
            )

        if side == PositionSide.LONG:
            if stop_loss >= entry_price:
                raise ValueError(
                    "LONG stop_loss must be below entry_price"
                )

        elif side == PositionSide.SHORT:
            if stop_loss <= entry_price:
                raise ValueError(
                    "SHORT stop_loss must be above entry_price"
                )

        else:
            raise ValueError("unsupported position side")
