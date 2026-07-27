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
from app.trade_signal import TradeSignal
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
    print(f"Файл состояния: {STATE_PATH}")
    print(
        "Timestamp сохранён в: "
        f"{LAST_CANDLE_PATH}"
    )


if __name__ == "__main__":
    main()
