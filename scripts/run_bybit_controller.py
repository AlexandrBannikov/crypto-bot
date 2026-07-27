from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bybit_market_data import (
    BybitMarketDataConfig,
    BybitMarketDataFeed,
)
from app.execution_runner import ExecutionRunner
from app.indicators import ema
from app.paper_executor import PaperExecutor
from app.process_lock import (
    ProcessAlreadyRunningError,
    ProcessLock,
    ProcessLockError,
)
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trade_journal import JsonlTradeJournal
from app.trading_controller import (
    TradingController,
    TradingControllerState,
)
from app.trading_types import TradeAction
from app.trading_controller_store import (
    TradingControllerStateStore,
)
from app.trading_runtime import TradingRuntime


SYMBOL = "ETHUSDT"
INTERVAL = "60"
CANDLE_LIMIT = 500

FAST_EMA = 20
SLOW_EMA = 50

ENTRY_QUANTITY = Decimal("0.01")

# Защитный стоп на 2% ниже цены входа.
STOP_LOSS_PERCENT = Decimal("0.02")

STATE_PATH = Path("state/trading_controller.json")
LAST_CANDLE_PATH = Path(
    "state/trading_controller_last_candle.txt"
)
JOURNAL_PATH = Path(
    os.environ.get(
        "CONTROLLER_TRADE_JOURNAL_PATH",
        "state/controller_trade_journal.jsonl",
    )
)
DEFAULT_STATISTICS_REPORT_PATH = (
    PROJECT_ROOT / "reports/trade_statistics.txt"
)
DEFAULT_STATISTICS_PLOT_PATH = (
    PROJECT_ROOT / "reports/trade_statistics.png"
)
DEFAULT_LOCK_PATH = (
    PROJECT_ROOT / "state/bybit_controller.lock"
)


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

    candles = feed.get_candles()
    latest_candle = candles[-1]

    last_processed_timestamp = (
        load_last_candle_timestamp()
    )

    if (
        last_processed_timestamp is not None
        and latest_candle.timestamp
        <= last_processed_timestamp
    ):
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

    result = controller.process_signal(
        symbol=SYMBOL,
        signal=execution_signal,
        entry_quantity=ENTRY_QUANTITY,
        price=current_price,
        client_order_id=(
            f"controller-{latest_candle.timestamp}"
        ),
        exit_reason=(
            "stop_loss" if stop_triggered else "signal"
        ),
    )

    # Отмечаем свечу обработанной только после успешного
    # завершения торгового контура.
    save_last_candle_timestamp(
        latest_candle.timestamp
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


if __name__ == "__main__":
    raise SystemExit(main())
