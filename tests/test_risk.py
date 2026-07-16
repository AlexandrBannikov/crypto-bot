import pytest

from app.risk import (
    PositionSize,
    RiskConfig,
    RiskManager,
)
from app.trading_types import PositionSide


def test_default_risk_config() -> None:
    config = RiskConfig()

    assert config.risk_per_trade == pytest.approx(0.01)
    assert config.max_position_fraction == pytest.approx(1.0)
    assert config.leverage == pytest.approx(1.0)


@pytest.mark.parametrize(
    "risk_per_trade",
    [0, -0.01, 1.01],
)
def test_rejects_invalid_risk_per_trade(
    risk_per_trade: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="risk_per_trade",
    ):
        RiskConfig(risk_per_trade=risk_per_trade)


@pytest.mark.parametrize(
    "max_position_fraction",
    [0, -0.1, 1.01],
)
def test_rejects_invalid_max_position_fraction(
    max_position_fraction: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="max_position_fraction",
    ):
        RiskConfig(
            max_position_fraction=max_position_fraction
        )


@pytest.mark.parametrize(
    "leverage",
    [0, 0.5, -1],
)
def test_rejects_invalid_leverage(
    leverage: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="leverage",
    ):
        RiskConfig(leverage=leverage)


def test_calculates_long_position_by_risk() -> None:
    manager = RiskManager(
        RiskConfig(
            risk_per_trade=0.01,
            max_position_fraction=1.0,
            leverage=1.0,
        )
    )

    result = manager.calculate_position_size(
        balance=10_000,
        entry_price=2_000,
        stop_loss=1_960,
        side=PositionSide.LONG,
    )

    assert isinstance(result, PositionSize)
    assert result.stop_distance == pytest.approx(40)
    assert result.stop_distance_percent == pytest.approx(
        0.02
    )
    assert result.position_value == pytest.approx(5_000)
    assert result.quantity == pytest.approx(2.5)
    assert result.capital_used == pytest.approx(5_000)
    assert result.risk_amount == pytest.approx(100)


def test_calculates_short_position_by_risk() -> None:
    manager = RiskManager(
        RiskConfig(risk_per_trade=0.02)
    )

    result = manager.calculate_position_size(
        balance=5_000,
        entry_price=2_000,
        stop_loss=2_100,
        side=PositionSide.SHORT,
    )

    assert result.stop_distance == pytest.approx(100)
    assert result.stop_distance_percent == pytest.approx(
        0.05
    )
    assert result.position_value == pytest.approx(2_000)
    assert result.quantity == pytest.approx(1)
    assert result.risk_amount == pytest.approx(100)


def test_position_is_limited_by_available_capital() -> None:
    manager = RiskManager(
        RiskConfig(
            risk_per_trade=0.02,
            max_position_fraction=0.5,
            leverage=1.0,
        )
    )

    result = manager.calculate_position_size(
        balance=10_000,
        entry_price=2_000,
        stop_loss=1_990,
        side=PositionSide.LONG,
    )

    assert result.position_value == pytest.approx(5_000)
    assert result.capital_used == pytest.approx(5_000)
    assert result.quantity == pytest.approx(2.5)
    assert result.risk_amount == pytest.approx(25)


def test_leverage_increases_maximum_position_value() -> None:
    manager = RiskManager(
        RiskConfig(
            risk_per_trade=0.02,
            max_position_fraction=0.5,
            leverage=3.0,
        )
    )

    result = manager.calculate_position_size(
        balance=10_000,
        entry_price=2_000,
        stop_loss=1_990,
        side=PositionSide.LONG,
    )

    assert result.position_value == pytest.approx(15_000)
    assert result.capital_used == pytest.approx(5_000)
    assert result.quantity == pytest.approx(7.5)
    assert result.risk_amount == pytest.approx(75)


def test_position_by_risk_can_use_less_than_maximum() -> None:
    manager = RiskManager(
        RiskConfig(
            risk_per_trade=0.01,
            max_position_fraction=1.0,
            leverage=3.0,
        )
    )

    result = manager.calculate_position_size(
        balance=10_000,
        entry_price=2_000,
        stop_loss=1_900,
        side=PositionSide.LONG,
    )

    assert result.position_value == pytest.approx(2_000)
    assert result.capital_used == pytest.approx(
        2_000 / 3
    )
    assert result.risk_amount == pytest.approx(100)


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        (
            "balance",
            {
                "balance": 0,
                "entry_price": 2_000,
                "stop_loss": 1_900,
            },
        ),
        (
            "entry_price",
            {
                "balance": 10_000,
                "entry_price": 0,
                "stop_loss": 1_900,
            },
        ),
        (
            "stop_loss",
            {
                "balance": 10_000,
                "entry_price": 2_000,
                "stop_loss": 0,
            },
        ),
    ],
)
def test_rejects_non_positive_values(
    field_name: str,
    kwargs: dict[str, float],
) -> None:
    manager = RiskManager()

    with pytest.raises(ValueError, match=field_name):
        manager.calculate_position_size(
            **kwargs,
            side=PositionSide.LONG,
        )


@pytest.mark.parametrize(
    "stop_loss",
    [2_000, 2_100],
)
def test_rejects_invalid_long_stop_loss(
    stop_loss: float,
) -> None:
    manager = RiskManager()

    with pytest.raises(
        ValueError,
        match="LONG stop_loss",
    ):
        manager.calculate_position_size(
            balance=10_000,
            entry_price=2_000,
            stop_loss=stop_loss,
            side=PositionSide.LONG,
        )


@pytest.mark.parametrize(
    "stop_loss",
    [2_000, 1_900],
)
def test_rejects_invalid_short_stop_loss(
    stop_loss: float,
) -> None:
    manager = RiskManager()

    with pytest.raises(
        ValueError,
        match="SHORT stop_loss",
    ):
        manager.calculate_position_size(
            balance=10_000,
            entry_price=2_000,
            stop_loss=stop_loss,
            side=PositionSide.SHORT,
        )


def test_accepts_full_risk_and_full_position_fraction() -> None:
    config = RiskConfig(
        risk_per_trade=1.0,
        max_position_fraction=1.0,
        leverage=1.0,
    )

    assert config.risk_per_trade == pytest.approx(1.0)
    assert config.max_position_fraction == pytest.approx(
        1.0
    )
