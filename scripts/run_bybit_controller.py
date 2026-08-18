from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bybit_market_data import (
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.break_even_shadow import (
    BreakEvenShadowJournal,
    BreakEvenShadowStateStore,
    observe_break_even_shadow,
    reconcile_break_even_shadow,
)
from app.config import (
    PaperStrategyConfig,
    PaperStrategyMode,
    RuntimeSafetyConfig,
)
from app.execution_runner import ExecutionRunner
from app.equity_history import (
    SnapshotService,
    SnapshotStorage,
    load_equity_history_config,
    read_trades as read_equity_trades,
)
from app.indicators import ema
from app.paper_executor import PaperExecutor
from app.paper_strategy_router import (
    PaperStrategyDecision,
    PaperStrategyRouter,
)
from app.profit_lock_shadow import (
    ProfitLockShadowJournal,
    ProfitLockShadowStateStore,
    observe_profit_lock_shadow,
    reconcile_profit_lock_shadow,
)
from app.process_lock import (
    ProcessAlreadyRunningError,
    ProcessLock,
    ProcessLockError,
)
from app.regime_runtime import (
    RegimeRuntimeStateStore,
    is_entry,
    is_exit,
)
from app.strategies import Signal
from app.shadow_decision_journal import (
    ShadowDecisionJournal,
    ShadowDecisionRecord,
)
from app.trade_signal import TradeSignal
from app.trade_journal import JsonlTradeJournal
from app.trade_diagnostics import build_and_append_trade_card
from app.trailing_stop_shadow import (
    TrailingShadowJournal,
    TrailingShadowStateStore,
    observe_trailing_shadow,
    reconcile_trailing_shadow,
)
from app.trading_controller import (
    TradingController,
    TradingControllerState,
)
from app.trading_types import TradeAction
from app.trading_controller_store import (
    TradingControllerStateStore,
)
from app.trading_runtime import TradingRuntime


SYMBOL = os.environ.get("SYMBOL", "ETHUSDT")
INTERVAL = os.environ.get("TIMEFRAME", "60")
CANDLE_LIMIT = 500

FAST_EMA = 20
SLOW_EMA = 50

ENTRY_QUANTITY = Decimal("0.01")

# Защитный стоп на 2% ниже цены входа.
STOP_LOSS_PERCENT = Decimal("0.02")

STATE_PATH = Path(
    os.environ.get(
        "CONTROLLER_STATE_PATH",
        "state/trading_controller.json",
    )
)
LAST_CANDLE_PATH = Path(
    os.environ.get(
        "CONTROLLER_LAST_CANDLE_PATH",
        "state/trading_controller_last_candle.txt",
    )
)
RUNTIME_STATE_PATH = Path(
    os.environ.get(
        "REGIME_RUNTIME_STATE_PATH",
        "state/regime_runtime.json",
    )
)
JOURNAL_PATH = Path(
    os.environ.get(
        "CONTROLLER_TRADE_JOURNAL_PATH",
        "state/controller_trade_journal.jsonl",
    )
)
DEFAULT_STATISTICS_REPORT_PATH = (
    Path(
        os.environ.get(
            "CONTROLLER_STATISTICS_REPORT_PATH",
            str(PROJECT_ROOT / "reports/trade_statistics.txt"),
        )
    )
)
DEFAULT_STATISTICS_PLOT_PATH = (
    Path(
        os.environ.get(
            "CONTROLLER_STATISTICS_PLOT_PATH",
            str(PROJECT_ROOT / "reports/trade_statistics.png"),
        )
    )
)
DEFAULT_LOCK_PATH = (
    Path(
        os.environ.get(
            "CONTROLLER_LOCK_PATH",
            str(PROJECT_ROOT / "state/bybit_controller.lock"),
        )
    )
)
BE_SHADOW_STATE_PATH = Path(
    os.environ.get("BE_SHADOW_STATE_PATH", "state/break_even_shadow.json")
)
BE_SHADOW_JOURNAL_PATH = Path(
    os.environ.get(
        "BE_SHADOW_JOURNAL_PATH", "state/break_even_shadow.jsonl"
    )
)
TRAILING_SHADOW_STATE_PATH = Path(
    os.environ.get("TRAILING_SHADOW_STATE_PATH", "state/trailing_stop_shadow.json")
)
TRAILING_SHADOW_JOURNAL_PATH = Path(
    os.environ.get("TRAILING_SHADOW_JOURNAL_PATH", "state/trailing_stop_shadow.jsonl")
)
PROFIT_LOCK_SHADOW_STATE_PATH = Path(
    os.environ.get("PROFIT_LOCK_SHADOW_STATE_PATH", "state/profit_lock_shadow.json")
)
PROFIT_LOCK_SHADOW_JOURNAL_PATH = Path(
    os.environ.get("PROFIT_LOCK_SHADOW_JOURNAL_PATH", "state/profit_lock_shadow.jsonl")
)
TRADE_DIAGNOSTICS_JOURNAL_PATH = Path(
    os.environ.get(
        "TRADE_DIAGNOSTICS_JOURNAL_PATH",
        "state/production_trade_diagnostics.jsonl",
    )
)
SCORED_65_DECISION_PATH = Path(
    os.environ.get(
        "SCORED_CANDIDATE_DECISION_PATH",
        "state/scored_candidate_shadow/decisions.jsonl",
    )
)
SCORED_62_DECISION_PATH = Path(
    os.environ.get(
        "SCORED_THRESHOLD62_DECISION_PATH",
        "state/scored_candidate_threshold62/decisions.jsonl",
    )
)


def run_break_even_shadow_observer(
    *,
    candle,
    production_before: TradingControllerState,
    production_after: TradingControllerState,
    production_exit_pnl: Decimal | None,
    historical_candles=(),
    state_path: Path | None = None,
    journal_path: Path | None = None,
) -> bool:
    """Persist one best-effort observation after production processing."""
    try:
        state_path = state_path or BE_SHADOW_STATE_PATH
        journal_path = journal_path or BE_SHADOW_JOURNAL_PATH
        be_store = BreakEvenShadowStateStore(state_path)
        be_state = be_store.load()
        if (
            production_before.has_open_position
            and production_after.has_open_position
        ):
            be_state = reconcile_break_even_shadow(
                be_state,
                production=production_before,
                candles=historical_candles,
            )
        be_update = observe_break_even_shadow(
            be_state,
            candle=candle,
            production_before=production_before,
            production_after=production_after,
            production_exit_pnl=production_exit_pnl,
        )
        BreakEvenShadowJournal(journal_path).append(be_update.observation)
        be_store.save(be_update.state)
    except Exception as exc:
        print(
            "Break-even shadow observer warning: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def run_trailing_shadow_observer(
    *, candle, production_before: TradingControllerState,
    production_after: TradingControllerState,
    production_exit_pnl: Decimal | None, historical_candles=(),
    state_path: Path | None = None, journal_path: Path | None = None,
) -> bool:
    """Persist research-only trailing observations after production processing."""
    try:
        store = TrailingShadowStateStore(state_path or TRAILING_SHADOW_STATE_PATH)
        state = store.load()
        if production_before.has_open_position and production_after.has_open_position:
            state = reconcile_trailing_shadow(
                state, production=production_before, candles=historical_candles
            )
        update = observe_trailing_shadow(
            state, candle=candle, production_before=production_before,
            production_after=production_after,
            production_net_pnl=production_exit_pnl,
        )
        TrailingShadowJournal(journal_path or TRAILING_SHADOW_JOURNAL_PATH).append(
            update.observation
        )
        store.save(update.state)
    except Exception as exc:
        print(
            f"Trailing shadow observer warning: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def run_profit_lock_shadow_observer(
    *, candle, production_before: TradingControllerState,
    production_after: TradingControllerState,
    production_exit_pnl: Decimal | None, historical_candles=(),
    state_path: Path | None = None, journal_path: Path | None = None,
) -> bool:
    """Persist the isolated research-only profit-lock counterfactuals."""
    try:
        store = ProfitLockShadowStateStore(state_path or PROFIT_LOCK_SHADOW_STATE_PATH)
        state = store.load()
        if production_before.has_open_position and production_after.has_open_position:
            state = reconcile_profit_lock_shadow(
                state, production=production_before, candles=historical_candles,
            )
        update = observe_profit_lock_shadow(
            state, candle=candle, production_before=production_before,
            production_after=production_after,
            production_net_pnl=production_exit_pnl,
        )
        ProfitLockShadowJournal(journal_path or PROFIT_LOCK_SHADOW_JOURNAL_PATH).append(
            update.observation
        )
        store.save(update.state)
    except Exception as exc:
        print(
            f"Profit-lock shadow observer warning: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Bybit paper trading controller",
    )
    parser.add_argument(
        "--statistics-report",
        type=Path,
        default=DEFAULT_STATISTICS_REPORT_PATH,
        help="path to the generated text trade report",
    )
    parser.add_argument(
        "--statistics-plot",
        type=Path,
        default=DEFAULT_STATISTICS_PLOT_PATH,
        help="path to the generated PNG trade report",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_PATH,
        help="path to the single-instance process lock",
    )
    parser.add_argument(
        "--strategy-mode",
        help=(
            "regime filter mode: off keeps legacy behavior; "
            "enforce filters new paper entries; shadow executes "
            "baseline and records filter decisions"
        ),
    )
    return parser


def generate_trade_reports(*args, **kwargs):
    from app.trade_reporting import generate_trade_reports as generate

    return generate(*args, **kwargs)


def generate_reports(
    *,
    text_report: Path,
    png_report: Path,
) -> int:
    from app.trade_reporting import TradeReportError

    try:
        reports = generate_trade_reports(
            JOURNAL_PATH,
            text_report,
            png_report,
        )
    except TradeReportError as exc:
        print(f"Ошибка генерации отчётов: {exc}", file=sys.stderr)
        return 1

    print(f"Текстовый отчёт: {reports.text_report}")
    print(f"PNG-отчёт: {reports.png_report}")
    return 0


def load_last_candle_timestamp() -> int | None:
    if not LAST_CANDLE_PATH.exists():
        return None

    raw_value = LAST_CANDLE_PATH.read_text(
        encoding="utf-8"
    ).strip()

    if not raw_value:
        return None

    try:
        timestamp = int(raw_value)
    except ValueError as error:
        raise ValueError(
            "Некорректный timestamp в "
            f"{LAST_CANDLE_PATH}"
        ) from error

    if timestamp < 0:
        raise ValueError(
            "Timestamp свечи не может быть отрицательным"
        )

    return timestamp


def save_last_candle_timestamp(
    timestamp: int,
) -> None:
    LAST_CANDLE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = LAST_CANDLE_PATH.with_suffix(
        LAST_CANDLE_PATH.suffix + ".tmp"
    )

    temporary_path.write_text(
        f"{timestamp}\n",
        encoding="utf-8",
    )

    temporary_path.replace(LAST_CANDLE_PATH)


def calculate_latest_signal(
    candles: tuple,
) -> tuple[Signal, float, float]:
    frame = pd.DataFrame(
        {
            "timestamp": [
                candle.timestamp for candle in candles
            ],
            "close": [
                candle.close for candle in candles
            ],
        }
    )

    fast = ema(frame["close"], FAST_EMA)
    slow = ema(frame["close"], SLOW_EMA)

    if (
        pd.isna(fast.iloc[-1])
        or pd.isna(slow.iloc[-1])
    ):
        raise RuntimeError(
            "Недостаточно свечей для расчёта EMA"
        )

    previous_fast = fast.iloc[-2]
    previous_slow = slow.iloc[-2]
    current_fast = fast.iloc[-1]
    current_slow = slow.iloc[-1]

    if (
        previous_fast <= previous_slow
        and current_fast > current_slow
    ):
        signal = Signal.BUY

    elif (
        previous_fast >= previous_slow
        and current_fast < current_slow
    ):
        signal = Signal.SELL

    else:
        signal = Signal.HOLD

    return (
        signal,
        float(current_fast),
        float(current_slow),
    )


def signal_name(signal: Signal) -> str:
    return {
        Signal.BUY: "BUY",
        Signal.SELL: "SELL",
        Signal.HOLD: "HOLD",
    }[signal]


def build_execution_signal(
    *,
    strategy_signal: Signal,
    price: Decimal,
    state: TradingControllerState,
) -> tuple[Signal | TradeSignal, bool]:
    """
    Добавляет защитный стоп к новой LONG-позиции
    и принудительно закрывает позицию при его достижении.

    Возвращает:
    - сигнал для TradingController;
    - флаг срабатывания стоп-лосса.
    """

    if (
        state.has_open_position
        and state.stop_loss is not None
        and price <= state.stop_loss
    ):
        return (
            TradeSignal(
                action=TradeAction.CLOSE_LONG,
            ),
            True,
        )

    if (
        strategy_signal == Signal.BUY
        and not state.has_open_position
    ):
        stop_loss = (
            price
            * (Decimal("1") - STOP_LOSS_PERCENT)
        ).quantize(Decimal("0.01"))

        return (
            TradeSignal(
                action=Signal.BUY,
                stop_loss=stop_loss,
            ),
            False,
        )

    return strategy_signal, False


def run_controller(args: argparse.Namespace) -> int:
    strategy_config = PaperStrategyConfig.from_env(
        mode_override=getattr(args, "strategy_mode", None)
    )
    safety_config = RuntimeSafetyConfig.from_env()
    runtime_state_store = RegimeRuntimeStateStore(RUNTIME_STATE_PATH)
    operational_state = runtime_state_store.load()
    diagnostics_path = strategy_config.shadow_diagnostics_path
    if not diagnostics_path.is_absolute():
        diagnostics_path = PROJECT_ROOT / diagnostics_path
    router = PaperStrategyRouter(
        strategy_config,
        fast_ema_period=FAST_EMA,
        slow_ema_period=SLOW_EMA,
    )
    print(
        "Paper strategy: "
        f"mode={strategy_config.mode.value}, "
        f"filter={router.detector_parameters}, "
        f"shadow_diagnostics={strategy_config.shadow_diagnostics_enabled}, "
        f"path={diagnostics_path}, "
        "entry_error_policy=fail-closed"
    )

    feed = BybitMarketDataFeed(
        BybitMarketDataConfig(
            symbol=SYMBOL,
            interval=INTERVAL,
            category="spot",
            limit=CANDLE_LIMIT,
            closed_candles_only=True,
        )
    )

    print("Получаем закрытые свечи Bybit...")

    try:
        candles = feed.get_candles()
    except Exception:
        if safety_config.halt_on_api_error:
            operational_state.active_halt_reason = "api_error"
            operational_state.counters.api_error_halts += 1
            runtime_state_store.save(operational_state)
        raise
    latest_candle = candles[-1]
    now = datetime.now(timezone.utc)
    data_age_seconds = max(
        0.0, now.timestamp() - float(latest_candle.timestamp)
    )
    if (
        data_age_seconds <= safety_config.max_data_age_seconds
        and operational_state.active_halt_reason
        in {"stale_data", "api_error"}
    ):
        operational_state.active_halt_reason = None

    last_processed_timestamp = (
        load_last_candle_timestamp()
    )

    if (
        last_processed_timestamp is not None
        and latest_candle.timestamp
        <= last_processed_timestamp
    ):
        try:
            history_config = load_equity_history_config(
                PROJECT_ROOT / "config/equity_history.json",
                root=PROJECT_ROOT,
            )
            history_storage = SnapshotStorage(history_config.database_path)
            candle_close = latest_candle.timestamp + int(INTERVAL) * 60
            history_service = SnapshotService(
                history_storage, history_config
            )
            if not history_storage.has_candle(
                "production", "production", candle_close
            ):
                recovery_state = TradingControllerStateStore(STATE_PATH).load()
                recovered, _ = history_service.capture(
                    environment="production", strategy_name="production",
                    state=recovery_state,
                    trades=read_equity_trades(JOURNAL_PATH),
                    market_price=Decimal(str(latest_candle.close)),
                    candle_open_timestamp=latest_candle.timestamp,
                    timeframe_minutes=int(INTERVAL), symbol=SYMBOL,
                    reason="startup_recovery",
                    source_cycle_id=(
                        f"production:{latest_candle.timestamp}:recovery"
                    ),
                )
                if recovered is not None:
                    history_service.maybe_daily_close(recovered, now=now)
            else:
                existing = history_storage.latest("production")
                if existing is not None:
                    history_service.maybe_daily_close(existing, now=now)
        except Exception as exc:
            print(
                "Equity history observer warning: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        print()
        print("===== BYBIT CONTROLLER PAPER =====")
        print(f"Инструмент: {SYMBOL}")
        print(
            "Последняя свеча уже обработана: "
            f"{latest_candle.timestamp}"
        )
        print("Новых закрытых свечей нет.")
        if (
            not args.statistics_report.exists()
            or not args.statistics_plot.exists()
        ):
            print(
                "Один или несколько отчётов отсутствуют. "
                "Восстанавливаем их из журнала."
            )
            return generate_reports(
                text_report=args.statistics_report,
                png_report=args.statistics_plot,
            )
        return 0

    signal, fast_value, slow_value = (
        calculate_latest_signal(candles)
    )

    executor = PaperExecutor()
    runner = ExecutionRunner(
        executor,
        allow_live=False,
    )
    runtime = TradingRuntime(runner)

    state_store = TradingControllerStateStore(
        STATE_PATH
    )

    controller = TradingController(
        runtime,
        state_store=state_store,
        trade_journal=JsonlTradeJournal(JOURNAL_PATH),
    )
    operational_state.update_risk(
        controller_equity(controller.state, Decimal(str(latest_candle.close))),
        safety_config,
        now=now,
    )

    # Создаём состояние даже при первом HOLD
    # и обновляем старый формат JSON.
    state_store.save(controller.state)

    current_price = Decimal(
        str(latest_candle.close)
    )

    execution_signal, stop_triggered = (
        build_execution_signal(
            strategy_signal=signal,
            price=current_price,
            state=controller.state,
        )
    )
    decision = router.route(execution_signal, candles)
    before_state = controller.state
    baseline_action = decision.baseline_signal.action
    operational_state.counters.signals_total += 1
    if is_entry(baseline_action):
        operational_state.counters.entry_signals_total += 1
    elif is_exit(baseline_action):
        operational_state.counters.exits_total += 1

    risk_reason = None
    if is_entry(baseline_action):
        if data_age_seconds > safety_config.max_data_age_seconds:
            risk_reason = "stale_data"
            operational_state.counters.stale_data_rejections += 1
            operational_state.active_halt_reason = risk_reason
        elif controller.state.has_open_position:
            risk_reason = "maximum_positions"
        elif not operational_state.permits_entry():
            risk_reason = operational_state.active_halt_reason
        if risk_reason is not None:
            decision = decision.__class__(
                baseline_signal=decision.baseline_signal,
                filtered_signal=TradeSignal(action=TradeAction.HOLD),
                execution_signal=TradeSignal(action=TradeAction.HOLD),
                mode=decision.mode,
                regime=decision.regime,
                confidence=decision.confidence,
                entry_allowed=False,
                blocked=True,
                blocked_reason=risk_reason,
                detector_diagnostics=decision.detector_diagnostics,
            )

    if decision.blocked and is_entry(baseline_action):
        if strategy_config.mode is PaperStrategyMode.SHADOW and risk_reason is None:
            operational_state.counters.record_block(
                decision.blocked_reason or "unknown", shadow=True
            )
            operational_state.counters.entries_allowed += 1
        else:
            operational_state.counters.record_block(
                decision.blocked_reason or "unknown", shadow=False
            )
    elif is_entry(baseline_action):
        operational_state.counters.entries_allowed += 1

    if decision.blocked:
        print(
            "Paper filter blocked entry: "
            f"mode={strategy_config.mode.value}, "
            f"timestamp={latest_candle.timestamp}, "
            f"signal={decision.baseline_signal.action.value}, "
            f"regime={decision.regime}, "
            f"confidence={decision.confidence}, "
            f"reason={decision.blocked_reason}"
        )

    result = controller.process_signal(
        symbol=SYMBOL,
        signal=decision.execution_signal,
        entry_quantity=ENTRY_QUANTITY,
        price=current_price,
        client_order_id=(
            f"controller-{latest_candle.timestamp}"
        ),
        exit_reason=(
            "stop_loss" if stop_triggered else "signal"
        ),
    )

    # Observation only: this component cannot emit an execution request or
    # mutate TradingControllerState. Failures must not affect paper trading.
    run_break_even_shadow_observer(
        candle=latest_candle,
        production_before=before_state,
        production_after=result.state,
        production_exit_pnl=(
            result.accounting.net_pnl
            if result.accounting is not None
            else None
        ),
        historical_candles=candles,
    )
    run_trailing_shadow_observer(
        candle=latest_candle,
        production_before=before_state,
        production_after=result.state,
        production_exit_pnl=(
            result.accounting.net_pnl if result.accounting is not None else None
        ),
        historical_candles=candles,
    )
    run_profit_lock_shadow_observer(
        candle=latest_candle,
        production_before=before_state,
        production_after=result.state,
        production_exit_pnl=(
            result.accounting.net_pnl if result.accounting is not None else None
        ),
        historical_candles=candles,
    )

    # Observation only. A diagnostics failure must never affect PAPER state,
    # execution, signals, stops, scoring, or position sizing.
    if result.journal_entry is not None:
        try:
            card, appended = build_and_append_trade_card(
                trade=result.journal_entry,
                candles=candles,
                exit_candle_timestamp=latest_candle.timestamp,
                timeframe_minutes=int(INTERVAL),
                journal_path=TRADE_DIAGNOSTICS_JOURNAL_PATH,
                production_decision_path=diagnostics_path,
                scored65_path=SCORED_65_DECISION_PATH,
                scored62_path=SCORED_62_DECISION_PATH,
                break_even_path=BE_SHADOW_JOURNAL_PATH,
                trailing_path=TRAILING_SHADOW_JOURNAL_PATH,
                profit_lock_path=PROFIT_LOCK_SHADOW_JOURNAL_PATH,
            )
            if appended:
                print(
                    "Trade diagnostics card saved: "
                    f"{card['trade_id']} -> {TRADE_DIAGNOSTICS_JOURNAL_PATH}"
                )
        except Exception as exc:
            print(
                "Trade diagnostics observer warning: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    operational_state.last_processed_closed_candle = latest_candle.timestamp
    operational_state.last_journal_sequence += 1
    operational_state.update_risk(
        controller_equity(result.state, current_price),
        safety_config,
        now=now,
    )
    runtime_state_store.save(operational_state)

    if strategy_config.shadow_diagnostics_enabled:
        record = build_shadow_record(
            decision=decision,
            latest_candle=latest_candle,
            state=before_state,
            state_after=result.state,
            controller_run_identifier=str(uuid4()),
            price=current_price,
            data_age_seconds=data_age_seconds,
            journal_sequence=operational_state.last_journal_sequence,
            baseline_trade_executed=(
                result.execution is not None
                and decision.execution_signal.action
                == decision.baseline_signal.action
            ),
        )
        try:
            ShadowDecisionJournal(diagnostics_path).append(record)
        except ValueError as exc:
            print(f"Decision journal error: {exc}", file=sys.stderr)

    # Отмечаем свечу обработанной только после успешного
    # завершения торгового контура.
    save_last_candle_timestamp(
        latest_candle.timestamp
    )
    try:
        history_config = load_equity_history_config(
            PROJECT_ROOT / "config/equity_history.json",
            root=PROJECT_ROOT,
        )
        history = SnapshotService(
            SnapshotStorage(history_config.database_path), history_config
        )
        cycle_snapshot, _ = history.capture(
            environment="production", strategy_name="production",
            state=result.state, trades=read_equity_trades(JOURNAL_PATH),
            market_price=current_price,
            candle_open_timestamp=latest_candle.timestamp,
            timeframe_minutes=int(INTERVAL), symbol=SYMBOL,
            reason="cycle",
            source_cycle_id=f"production:{latest_candle.timestamp}",
            snapshot_at=now,
        )
        if cycle_snapshot is not None:
            history.maybe_daily_close(cycle_snapshot, now=now)
        if before_state.has_open_position != result.state.has_open_position:
            history.capture(
                environment="production", strategy_name="production",
                state=result.state, trades=read_equity_trades(JOURNAL_PATH),
                market_price=current_price,
                candle_open_timestamp=latest_candle.timestamp,
                timeframe_minutes=int(INTERVAL), symbol=SYMBOL,
                reason=(
                    "trade_open" if result.state.has_open_position
                    else "trade_close"
                ),
                source_cycle_id=(
                    f"production:{latest_candle.timestamp}:trade"
                ),
                snapshot_at=now,
            )
    except Exception as exc:
        print(
            f"Equity history observer warning: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

    print()
    print("===== BYBIT CONTROLLER PAPER =====")
    print(f"Инструмент: {SYMBOL}")
    print(f"Интервал: {INTERVAL} минут")
    print(f"Получено свечей: {len(candles)}")
    print(
        "Последняя закрытая свеча: "
        f"{latest_candle.timestamp}"
    )
    print(f"Цена закрытия: {latest_candle.close}")
    print(f"EMA {FAST_EMA}: {fast_value:.4f}")
    print(f"EMA {SLOW_EMA}: {slow_value:.4f}")
    print(f"Сигнал стратегии: {signal_name(signal)}")

    if stop_triggered:
        print("Защитный выход: сработал STOP LOSS")
    else:
        print("Защитный выход: не сработал")

    print(f"Действие контроллера: {result.action.value}")

    if result.execution is None:
        print("Бумажная заявка: не создавалась")
        print(
            "Причина: "
            f"{result.skipped_reason or 'нет'}"
        )
    else:
        execution = result.execution

        print("Бумажная заявка: исполнена")
        print(f"Статус: {execution.status.value}")
        print(f"Номер: {execution.order_id}")
        print(
            "Количество: "
            f"{execution.executed_quantity}"
        )
        print(
            "Цена исполнения: "
            f"{execution.average_price}"
        )

    print(
        "Открытая позиция ETH: "
        f"{result.state.position_quantity}"
    )
    print(
        "Цена входа: "
        f"{result.state.entry_price}"
    )
    print(
        "Активный стоп-лосс: "
        f"{result.state.stop_loss}"
    )
    print(
        "Виртуальный баланс: "
        f"{result.state.virtual_balance}"
    )
    print(
        "Реализованный PnL: "
        f"{result.state.realized_pnl}"
    )
    print(
        "Всего комиссий: "
        f"{result.state.total_fees}"
    )
    print(
        "Закрытых сделок: "
        f"{result.state.closed_trades}"
    )

    if result.accounting is not None:
        accounting = result.accounting
        print("Финансовый результат закрытия:")
        print(f"  Стоимость входа: {accounting.entry_notional}")
        print(f"  Стоимость выхода: {accounting.exit_notional}")
        print(f"  Gross PnL: {accounting.gross_pnl}")
        print(f"  Комиссия входа: {accounting.entry_fee}")
        print(f"  Комиссия выхода: {accounting.exit_fee}")
        print(f"  Net PnL: {accounting.net_pnl}")

    if result.journal_entry is not None:
        print(
            "Запись о закрытии сохранена в журнал: "
            f"{JOURNAL_PATH}"
        )

    print(f"Файл состояния: {STATE_PATH}")
    print(
        "Timestamp сохранён в: "
        f"{LAST_CANDLE_PATH}"
    )

    if result.journal_entry is None:
        return 0

    return generate_reports(
        text_report=args.statistics_report,
        png_report=args.statistics_plot,
    )


def controller_equity(
    state: TradingControllerState,
    price: Decimal,
) -> Decimal:
    """Mark the paper position to market for risk limits."""
    return state.virtual_balance + state.position_quantity * price


def build_shadow_record(
    *,
    decision: PaperStrategyDecision,
    latest_candle,
    state: TradingControllerState,
    controller_run_identifier: str,
    state_after: TradingControllerState | None = None,
    price: Decimal | None = None,
    data_age_seconds: float | None = None,
    journal_sequence: int | None = None,
    baseline_trade_executed: bool = False,
) -> ShadowDecisionRecord:
    position = "long" if state.has_open_position else "flat"
    unique_identifier = (
        f"{SYMBOL}:{INTERVAL}:{latest_candle.timestamp}"
    )
    return ShadowDecisionRecord(
        candle_timestamp=latest_candle.timestamp,
        symbol=SYMBOL,
        timeframe=INTERVAL,
        strategy_mode=decision.mode.value,
        baseline_signal=decision.baseline_signal.action.value,
        filtered_signal=decision.filtered_signal.action.value,
        execution_signal=decision.execution_signal.action.value,
        regime=decision.regime,
        confidence=decision.confidence,
        allowed=decision.entry_allowed,
        blocked=decision.blocked,
        blocked_reason=decision.blocked_reason,
        current_position=position,
        virtual_balance=str(state.virtual_balance),
        detector_parameters=(
            decision.detector_diagnostics.parameters
        ),
        filter_parameters_fingerprint=(
            decision.detector_diagnostics.parameters_fingerprint
        ),
        unique_candle_identifier=unique_identifier,
        controller_run_identifier=controller_run_identifier,
        detector_error=decision.detector_diagnostics.error_type,
        effective_action=decision.execution_signal.action.value,
        filter_mode=decision.mode.value,
        price=str(price) if price is not None else None,
        position_state_before=position,
        position_state_after=(
            "long"
            if state_after is not None and state_after.has_open_position
            else "flat"
        ),
        data_age_seconds=data_age_seconds,
        runtime_instance_id=controller_run_identifier,
        shadow_would_block=(
            decision.mode is PaperStrategyMode.SHADOW
            and decision.blocked
        ),
        shadow_block_reason=(
            decision.blocked_reason
            if decision.mode is PaperStrategyMode.SHADOW
            and decision.blocked
            else None
        ),
        baseline_trade_executed=baseline_trade_executed,
        journal_sequence=journal_sequence,
        strategy_id="production",
        signal=decision.baseline_signal.action.value,
        action=decision.execution_signal.action.value,
        position_before=position,
        position_after=(
            "long"
            if state_after is not None and state_after.has_open_position
            else "flat"
        ),
        reason=(
            decision.blocked_reason
            or decision.detector_diagnostics.error_type
            or "strategy decision produced"
        ),
        decision_status=(
            "error"
            if decision.detector_diagnostics.error_type
            else "produced"
        ),
        status_reason=decision.detector_diagnostics.error_type,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        with ProcessLock(args.lock_file):
            return run_controller(args)
    except ProcessAlreadyRunningError as exc:
        print(
            "Bybit controller уже запущен; "
            f"lock-файл: {args.lock_file}. {exc}",
            file=sys.stderr,
        )
        return 2
    except ProcessLockError as exc:
        print(
            "Ошибка single-instance lock "
            f"{args.lock_file}: {exc}",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(f"Controller configuration error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
