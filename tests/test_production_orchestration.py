from decimal import Decimal
from pathlib import Path

from app.candle import Candle
from app.canonical_features import CanonicalFeatureStore, materialize_feature_snapshots
from app.config import PaperStrategyConfig, PaperStrategyMode
from app.execution_runner import ExecutionRunner
from app.paper_executor import PaperExecutor
from app.paper_strategy_router import PaperStrategyRouter
from app.production_orchestration import process_production_candles, select_unprocessed_candles
from app.strategies import Signal
from app.trade_journal import JsonlTradeJournal
from app.trading_controller import TradingController
from app.trading_runtime import TradingRuntime
from app.trading_types import TradeAction


HOUR = 3600
D = Decimal


def market(count: int = 70) -> tuple[Candle, ...]:
    return tuple(
        Candle(index * HOUR, 100 + index, 101 + index,
               99 + index, 100.5 + index, 1)
        for index in range(count)
    )


def setup(tmp_path: Path):
    candles = market()
    features = CanonicalFeatureStore(tmp_path / "features.jsonl")
    materialize_feature_snapshots(
        candles, store=features, symbol="ETHUSDT", timeframe_seconds=HOUR,
    )
    controller = TradingController(
        TradingRuntime(ExecutionRunner(PaperExecutor())),
        trade_journal=JsonlTradeJournal(tmp_path / "trades.jsonl"),
    )
    router = PaperStrategyRouter(PaperStrategyConfig(mode=PaperStrategyMode.OFF))
    return candles, features, controller, router


def test_all_candles_after_persisted_cursor_are_selected() -> None:
    candles = market(5)
    selected, continuity = select_unprocessed_candles(
        candles, last_processed_timestamp=HOUR, timeframe_seconds=HOUR,
    )
    assert [item.timestamp for item in selected] == [2 * HOUR, 3 * HOUR, 4 * HOUR]
    assert not continuity.unresolved_gap


def test_signal_fills_on_next_candle_open_not_signal_close(tmp_path: Path) -> None:
    candles, features, controller, router = setup(tmp_path)

    def signals(history):
        signal = Signal.BUY if history[-1].timestamp == 67 * HOUR else Signal.HOLD
        return signal, 1.0, 2.0

    cycles = process_production_candles(
        candles, last_processed_timestamp=66 * HOUR,
        timeframe_seconds=HOUR, symbol="ETHUSDT", controller=controller,
        router=router, feature_store=features, entry_quantity=D("0.01"),
        signal_function=signals,
    )
    assert len(cycles) == 3
    assert not cycles[0].state_after.has_open_position
    assert cycles[0].state_after.pending_action == TradeAction.OPEN_LONG
    assert cycles[1].open_step.opened_on_candle
    assert controller.state.entry_price == D(str(candles[68].open))


def test_missing_exact_score_blocks_entry_without_using_stale_row(tmp_path: Path) -> None:
    candles, _, controller, router = setup(tmp_path)
    stale = CanonicalFeatureStore(tmp_path / "stale.jsonl")
    materialize_feature_snapshots(
        candles[:-1], store=stale, symbol="ETHUSDT", timeframe_seconds=HOUR,
    )
    cycles = process_production_candles(
        candles, last_processed_timestamp=68 * HOUR,
        timeframe_seconds=HOUR, symbol="ETHUSDT", controller=controller,
        router=router, feature_store=stale, entry_quantity=D("0.01"),
        signal_function=lambda history: (Signal.BUY, 1.0, 2.0),
    )
    assert cycles[0].score_status == "PENDING"
    assert controller.state.pending_action == TradeAction.HOLD


def test_unresolved_cursor_gap_forbids_entry(tmp_path: Path) -> None:
    candles, features, controller, router = setup(tmp_path)
    cycles = process_production_candles(
        candles[-2:], last_processed_timestamp=60 * HOUR,
        timeframe_seconds=HOUR, symbol="ETHUSDT", controller=controller,
        router=router, feature_store=features, entry_quantity=D("0.01"),
        signal_function=lambda history: (Signal.BUY, 1.0, 2.0),
    )
    assert cycles and all(item.unresolved_gap for item in cycles)
    assert controller.state.pending_action == TradeAction.HOLD
