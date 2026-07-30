from collections.abc import Sequence

from app.engine import Candle, Strategy, Trade
from app.paper_session import PaperTradingSession
from app.signal_normalizer import normalize_signal
from app.strategy_diagnostics import (
    Decision,
    DiagnosticJournal,
    DiagnosticRecord,
    PositionState,
)


class PaperTradingEngine:
    def __init__(
        self,
        *,
        session: PaperTradingSession,
        strategy: Strategy,
        diagnostic_journal: DiagnosticJournal | None = None,
        diagnostic_symbol: str = "ETHUSDT",
        diagnostic_timeframe: str = "60",
        diagnostic_session_id: str = "paper",
        save_all_diagnostics: bool = True,
    ) -> None:
        self.session = session
        self.strategy = strategy
        self.diagnostic_journal = diagnostic_journal
        self.diagnostic_symbol = diagnostic_symbol
        self.diagnostic_timeframe = diagnostic_timeframe
        self.diagnostic_session_id = diagnostic_session_id
        self.save_all_diagnostics = save_all_diagnostics

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

            position_state = self._position_state()
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

            self._record_diagnostics(
                candles=candles,
                index=index,
                position_state=position_state,
            )

        return tuple(trades)

    def _position_state(self) -> PositionState:
        position = self.session.snapshot.position
        if position is None:
            return PositionState.FLAT
        return PositionState(position.side.value)

    def _record_diagnostics(
        self,
        *,
        candles: Sequence[Candle],
        index: int,
        position_state: PositionState,
    ) -> None:
        if self.diagnostic_journal is None:
            return
        evaluator = getattr(
            self.strategy, "evaluate_with_diagnostics", None
        )
        if evaluator is None:
            return
        decision = evaluator(
            candles,
            index,
            position_state=position_state,
        )
        if (
            not self.save_all_diagnostics
            and decision.decision != Decision.HOLD
        ):
            return
        parameters = getattr(
            self.strategy, "strategy_parameters", {}
        )
        self.diagnostic_journal.append(
            DiagnosticRecord.from_decision(
                decision,
                symbol=self.diagnostic_symbol,
                timeframe=self.diagnostic_timeframe,
                strategy_name=type(self.strategy).__name__,
                strategy_parameters=dict(parameters),
                session_id=self.diagnostic_session_id,
            )
        )
