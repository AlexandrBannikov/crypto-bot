from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_types import TradeAction


def normalize_signal(
    signal: Signal | TradeSignal | TradeAction,
) -> TradeSignal:
    if isinstance(signal, TradeSignal):
        action = signal.action

        if isinstance(action, TradeAction):
            return signal

        if action == Signal.BUY:
            normalized_action = TradeAction.OPEN_LONG
        elif action == Signal.SELL:
            normalized_action = TradeAction.CLOSE_LONG
        else:
            normalized_action = TradeAction.HOLD

        return TradeSignal(
            action=normalized_action,
            stop_loss=signal.stop_loss,
            trailing_stop_percent=(
                signal.trailing_stop_percent
            ),
            break_even_r_multiple=(
                signal.break_even_r_multiple
            ),
        )

    if isinstance(signal, TradeAction):
        return TradeSignal(action=signal)

    if isinstance(signal, Signal):
        if signal == Signal.BUY:
            action = TradeAction.OPEN_LONG
        elif signal == Signal.SELL:
            action = TradeAction.CLOSE_LONG
        else:
            action = TradeAction.HOLD

        return TradeSignal(action=action)

    raise TypeError(
        "strategy must return Signal, "
        "TradeAction or TradeSignal"
    )
