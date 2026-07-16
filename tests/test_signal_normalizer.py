import pytest

from app.signal_normalizer import normalize_signal
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_types import TradeAction


@pytest.mark.parametrize(
    ("signal", "expected_action"),
    [
        (Signal.BUY, TradeAction.OPEN_LONG),
        (Signal.SELL, TradeAction.CLOSE_LONG),
        (Signal.HOLD, TradeAction.HOLD),
    ],
)
def test_normalizes_legacy_signal(
    signal: Signal,
    expected_action: TradeAction,
) -> None:
    result = normalize_signal(signal)

    assert result.action == expected_action


@pytest.mark.parametrize(
    "action",
    list(TradeAction),
)
def test_normalizes_trade_action(
    action: TradeAction,
) -> None:
    result = normalize_signal(action)

    assert result.action == action


def test_preserves_trade_signal_with_trade_action() -> None:
    signal = TradeSignal(
        action=TradeAction.OPEN_LONG,
        stop_loss=95,
        trailing_stop_percent=0.05,
        break_even_r_multiple=1.5,
    )

    assert normalize_signal(signal) is signal


def test_preserves_trade_signal_settings() -> None:
    signal = TradeSignal(
        action=Signal.BUY,
        stop_loss=95,
        trailing_stop_percent=0.05,
        break_even_r_multiple=1.5,
    )

    result = normalize_signal(signal)

    assert result.action == TradeAction.OPEN_LONG
    assert result.stop_loss == pytest.approx(95)
    assert result.trailing_stop_percent == pytest.approx(
        0.05
    )
    assert result.break_even_r_multiple == pytest.approx(
        1.5
    )


def test_rejects_unknown_signal_type() -> None:
    with pytest.raises(
        TypeError,
        match="strategy must return",
    ):
        normalize_signal("BUY")  # type: ignore[arg-type]
