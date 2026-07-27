from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.candle import Candle
from app.config import PaperStrategyConfig, PaperStrategyMode
from app.execution_runner import ExecutionRunner
from app.market_regime import (
    MarketRegime,
    MarketTrend,
    MarketVolatility,
)
from app.paper_executor import PaperExecutor
from app.paper_strategy_router import PaperStrategyRouter
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_controller import TradingController
from app.trading_runtime import TradingRuntime
from app.trading_types import TradeAction


def candles() -> list[Candle]:
    return [
        Candle(index, 100, 101, 99, 100 + index)
        for index in range(60)
    ]


def regime(
    trend=MarketTrend.TREND_UP,
    volatility=MarketVolatility.NORMAL,
):
    return MarketRegime(trend, volatility, 1.0)


def router(mode, detected=None):
    detector = Mock()
    detector.detect.return_value = detected or regime()
    return (
        PaperStrategyRouter(
            PaperStrategyConfig(mode=mode),
            detector=detector,
        ),
        detector,
    )


def test_baseline_preserves_signal_without_detector() -> None:
    strategy_router, detector = router(PaperStrategyMode.BASELINE)
    signal = TradeSignal(action=Signal.BUY, stop_loss=95)

    decision = strategy_router.route(signal, candles())

    assert decision.execution_signal.action is TradeAction.OPEN_LONG
    assert decision.execution_signal.stop_loss == 95
    detector.detect.assert_not_called()


def test_filtered_allows_valid_entry() -> None:
    strategy_router, _ = router(PaperStrategyMode.FILTERED)

    decision = strategy_router.route(Signal.BUY, candles())

    assert decision.execution_signal.action is TradeAction.OPEN_LONG
    assert decision.entry_allowed is True
    assert decision.blocked is False


@pytest.mark.parametrize(
    ("detected", "reason"),
    [
        (regime(MarketTrend.RANGE), "range"),
        (regime(MarketTrend.TREND_DOWN), "downtrend"),
        (
            regime(
                MarketTrend.TREND_UP,
                MarketVolatility.HIGH,
            ),
            "high_volatility",
        ),
    ],
)
def test_filtered_blocks_invalid_entry(detected, reason) -> None:
    strategy_router, _ = router(
        PaperStrategyMode.FILTERED, detected
    )

    decision = strategy_router.route(Signal.BUY, candles())

    assert decision.execution_signal.action is TradeAction.HOLD
    assert decision.blocked_reason == reason


@pytest.mark.parametrize(
    "signal",
    [
        Signal.SELL,
        TradeAction.CLOSE_LONG,
        TradeAction.CLOSE_SHORT,
    ],
)
def test_filtered_never_blocks_exit(signal) -> None:
    strategy_router, detector = router(
        PaperStrategyMode.FILTERED,
        regime(MarketTrend.RANGE),
    )

    decision = strategy_router.route(signal, candles())

    assert decision.execution_signal.action in {
        TradeAction.CLOSE_LONG,
        TradeAction.CLOSE_SHORT,
    }
    assert decision.blocked is False
    detector.detect.assert_not_called()


def test_shadow_executes_baseline_and_records_filtered_view() -> None:
    strategy_router, _ = router(
        PaperStrategyMode.SHADOW,
        regime(MarketTrend.RANGE),
    )

    decision = strategy_router.route(Signal.BUY, candles())

    assert decision.baseline_signal.action is TradeAction.OPEN_LONG
    assert decision.filtered_signal.action is TradeAction.HOLD
    assert decision.execution_signal.action is TradeAction.OPEN_LONG
    assert decision.blocked is True


def test_detector_error_filtered_fails_closed_only_for_entry() -> None:
    strategy_router, detector = router(PaperStrategyMode.FILTERED)
    detector.detect.side_effect = RuntimeError("secret=do-not-record")

    entry = strategy_router.route(Signal.BUY, candles())
    exit_decision = strategy_router.route(Signal.SELL, candles())

    assert entry.execution_signal.action is TradeAction.HOLD
    assert entry.blocked_reason == "detector_error"
    assert entry.detector_diagnostics.error_type == "RuntimeError"
    assert "secret" not in repr(entry)
    assert exit_decision.execution_signal.action is TradeAction.CLOSE_LONG


def test_detector_error_shadow_keeps_baseline_entry() -> None:
    strategy_router, detector = router(PaperStrategyMode.SHADOW)
    detector.detect.side_effect = RuntimeError("failed")

    decision = strategy_router.route(Signal.BUY, candles())

    assert decision.execution_signal.action is TradeAction.OPEN_LONG
    assert decision.filtered_signal.action is TradeAction.HOLD


def test_shadow_and_baseline_have_identical_accounting() -> None:
    baseline_router, _ = router(PaperStrategyMode.BASELINE)
    shadow_router, _ = router(
        PaperStrategyMode.SHADOW,
        regime(MarketTrend.RANGE),
    )

    def run(strategy_router):
        journal_entries = []

        class Journal:
            def append(self, entry):
                journal_entries.append(entry)

        controller = TradingController(
            TradingRuntime(ExecutionRunner(PaperExecutor())),
            trade_journal=Journal(),
        )
        for signal, price in (
            (Signal.BUY, Decimal("100")),
            (Signal.SELL, Decimal("110")),
        ):
            decision = strategy_router.route(signal, candles())
            controller.process_signal(
                symbol="ETHUSDT",
                signal=decision.execution_signal,
                entry_quantity=Decimal("1"),
                price=price,
            )
        return controller.state, journal_entries

    baseline_state, baseline_journal = run(baseline_router)
    shadow_state, shadow_journal = run(shadow_router)

    assert shadow_state == baseline_state
    assert len(shadow_journal) == len(baseline_journal) == 1
    assert shadow_journal[0].net_pnl == baseline_journal[0].net_pnl


def test_filtered_can_differ_only_by_suppressing_entry() -> None:
    strategy_router, _ = router(
        PaperStrategyMode.FILTERED,
        regime(MarketTrend.RANGE),
    )
    controller = TradingController(
        TradingRuntime(ExecutionRunner(PaperExecutor()))
    )

    decision = strategy_router.route(Signal.BUY, candles())
    controller.process_signal(
        symbol="ETHUSDT",
        signal=decision.execution_signal,
        entry_quantity=Decimal("1"),
        price=Decimal("100"),
    )

    assert controller.state.has_open_position is False
    assert controller.state.virtual_balance == Decimal("1000")
