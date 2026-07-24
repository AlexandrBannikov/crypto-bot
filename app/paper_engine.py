from collections.abc import Sequence

from app.engine import Candle, Strategy, Trade
from app.order_executor import (
    OrderExecutor,
    PaperOrderExecutor,
)
from app.paper_session import PaperTradingSession
from app.signal_normalizer import normalize_signal


class PaperTradingEngine:
    def __init__(
        self,
        *,
        session: PaperTradingSession,
        strategy: Strategy,
        executor: OrderExecutor | None = None,
    ) -> None:
        self.session = session
        self.strategy = strategy
        self.executor = (
            executor
            or PaperOrderExecutor(session)
        )

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
                self.executor.execute_pending_action(
                    candle
                )
            )

            if pending_trade is not None:
                trades.append(pending_trade)

            stop_trade = (
                self.executor.process_closed_candle(
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

            self.executor.queue_signal(
                signal=signal,
                reference_price=candle.close,
            )

        return tuple(trades)
