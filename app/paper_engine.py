from collections.abc import Sequence

from app.engine import Candle, Strategy, Trade
from app.paper_session import PaperTradingSession
from app.signal_normalizer import normalize_signal


class PaperTradingEngine:
    def __init__(
        self,
        *,
        session: PaperTradingSession,
        strategy: Strategy,
    ) -> None:
        self.session = session
        self.strategy = strategy

    def run_iteration(
        self,
        candles: Sequence[Candle],
    ) -> tuple[Trade, ...]:
        if not candles:
            return ()

        trades: list[Trade] = []

        last_timestamp = (
            self.session.snapshot.last_candle_timestamp
        )

        new_candles = tuple(
            candle
            for candle in candles
            if (
                last_timestamp is None
                or candle.timestamp > last_timestamp
            )
        )

        for candle in new_candles:
            index = candles.index(candle)

            pending_trade = (
                self.session.execute_pending_action(
                    candle
                )
            )

            if pending_trade is not None:
                trades.append(pending_trade)

            stop_trade = (
                self.session.process_closed_candle(
                    candle
                )
            )

            if stop_trade is not None:
                trades.append(stop_trade)

            raw_signal = (
                self.strategy.generate_signal(
                    candles,
                    index,
                )
            )

            signal = normalize_signal(
                raw_signal
            )

            self.session.queue_action(
                action=signal.action,
                reference_price=candle.close,
                stop_loss=signal.stop_loss,
                trailing_stop_percent=(
                    signal.trailing_stop_percent
                ),
            )

        return tuple(trades)
