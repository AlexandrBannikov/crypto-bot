from decimal import Decimal

from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_controller import TradingControllerState
from app.trading_types import TradeAction
from scripts.run_bybit_controller import (
    STOP_LOSS_PERCENT,
    build_execution_signal,
)


def test_stop_loss_percent_is_two_percent() -> None:
    assert STOP_LOSS_PERCENT == Decimal("0.02")


def test_buy_signal_receives_stop_loss() -> None:
    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.BUY,
        price=Decimal("1950"),
        state=TradingControllerState(),
    )

    assert isinstance(signal, TradeSignal)
    assert signal.action == Signal.BUY
    assert signal.stop_loss == Decimal("1911.00")
    assert stop_triggered is False


def test_stop_loss_closes_open_position() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.HOLD,
        price=Decimal("1910"),
        state=state,
    )

    assert isinstance(signal, TradeSignal)
    assert signal.action == TradeAction.CLOSE_LONG
    assert stop_triggered is True


def test_stop_loss_triggers_at_exact_price() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.HOLD,
        price=Decimal("1911"),
        state=state,
    )

    assert isinstance(signal, TradeSignal)
    assert signal.action == TradeAction.CLOSE_LONG
    assert stop_triggered is True


def test_hold_above_stop_does_not_close() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.HOLD,
        price=Decimal("1920"),
        state=state,
    )

    assert signal == Signal.HOLD
    assert stop_triggered is False


def test_strategy_sell_is_preserved() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.SELL,
        price=Decimal("2000"),
        state=state,
    )

    assert signal == Signal.SELL
    assert stop_triggered is False


def test_buy_does_not_replace_existing_stop() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.BUY,
        price=Decimal("2000"),
        state=state,
    )

    assert signal == Signal.BUY
    assert stop_triggered is False
