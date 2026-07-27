from __future__ import annotations

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
from app.strategies import Signal
from app.trading_controller import TradingController
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

STATE_PATH = Path("state/trading_controller.json")
LAST_CANDLE_PATH = Path(
    "state/trading_controller_last_candle.txt"
)


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


def main() -> None:
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
        return

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
    )

    # Создаём состояние даже при первом HOLD.
    state_store.save(controller.state)

    result = controller.process_signal(
        symbol=SYMBOL,
        signal=signal,
        entry_quantity=ENTRY_QUANTITY,
        price=Decimal(str(latest_candle.close)),
        client_order_id=(
            f"controller-{latest_candle.timestamp}"
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
    print(f"Файл состояния: {STATE_PATH}")
    print(
        "Timestamp сохранён в: "
        f"{LAST_CANDLE_PATH}"
    )


if __name__ == "__main__":
    main()
