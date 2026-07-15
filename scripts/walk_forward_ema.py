from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.candle_mapper import dataframe_to_candles
from app.data_loader import load_market_data
from app.ema_cross_strategy import EMACrossStrategy
from app.engine import BacktestEngine


DATA_FILE = Path("data/eth_usdt_1h_full.csv")

START_BALANCE = 1000.0
COMMISSION_RATE = 0.001

TRAIN_MONTHS = 18
TEST_MONTHS = 6

SHORT_PERIODS = [
    5,
    10,
    15,
    20,
    30,
    40,
    50,
]

LONG_PERIODS = [
    50,
    80,
    100,
    150,
    200,
    250,
    300,
]

MINIMUM_TRADES = 15


@dataclass(frozen=True)
class StrategyResult:
    short_period: int
    long_period: int
    return_percent: float
    drawdown_percent: float
    profit_factor: float
    trades: int
    score: float


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    short_period: int
    long_period: int

    train_return_percent: float
    train_drawdown_percent: float
    train_profit_factor: float

    test_return_percent: float
    test_drawdown_percent: float
    test_profit_factor: float
    test_trades: int


def run_strategy(
    data: pd.DataFrame,
    short_period: int,
    long_period: int,
    initial_balance: float = START_BALANCE,
) -> StrategyResult:
    candles = dataframe_to_candles(data)

    strategy = EMACrossStrategy(
        short_period=short_period,
        long_period=long_period,
    )

    engine = BacktestEngine(
        initial_balance=initial_balance,
        commission_rate=COMMISSION_RATE,
    )

    result = engine.run(
        candles=candles,
        strategy=strategy,
    )

    drawdown = result.max_drawdown_percent

    score = (
        result.total_return_percent
        / max(drawdown, 1.0)
    )

    return StrategyResult(
        short_period=short_period,
        long_period=long_period,
        return_percent=result.total_return_percent,
        drawdown_percent=drawdown,
        profit_factor=result.profit_factor,
        trades=len(result.trades),
        score=score,
    )


def find_best_parameters(
    train_data: pd.DataFrame,
) -> StrategyResult:
    results: list[StrategyResult] = []

    for short_period in SHORT_PERIODS:
        for long_period in LONG_PERIODS:
            if short_period >= long_period:
                continue

            result = run_strategy(
                data=train_data,
                short_period=short_period,
                long_period=long_period,
            )

            if result.trades >= MINIMUM_TRADES:
                results.append(result)

    if not results:
        raise RuntimeError(
            "Не найдено подходящих комбинаций параметров"
        )

    results.sort(
        key=lambda item: (
            item.score,
            item.profit_factor,
            item.return_percent,
        ),
        reverse=True,
    )

    return results[0]


def build_windows(
    data: pd.DataFrame,
) -> list[
    tuple[
        pd.Timestamp,
        pd.Timestamp,
        pd.Timestamp,
        pd.Timestamp,
    ]
]:
    first_datetime = pd.Timestamp(
        data.iloc[0]["datetime"]
    )

    last_datetime = pd.Timestamp(
        data.iloc[-1]["datetime"]
    )

    train_start = first_datetime

    windows = []

    while True:
        train_end = (
            train_start
            + pd.DateOffset(months=TRAIN_MONTHS)
        )

        test_start = train_end

        test_end = (
            test_start
            + pd.DateOffset(months=TEST_MONTHS)
        )

        if test_end > last_datetime:
            break

        windows.append(
            (
                train_start,
                train_end,
                test_start,
                test_end,
            )
        )

        train_start = (
            train_start
            + pd.DateOffset(months=TEST_MONTHS)
        )

    return windows


def calculate_buy_and_hold(
    data: pd.DataFrame,
) -> float:
    first_price = float(data.iloc[0]["open"])
    last_price = float(data.iloc[-1]["close"])

    entry_fee = START_BALANCE * COMMISSION_RATE

    quantity = (
        START_BALANCE - entry_fee
    ) / first_price

    gross_value = quantity * last_price
    exit_fee = gross_value * COMMISSION_RATE

    final_balance = gross_value - exit_fee

    return (
        final_balance / START_BALANCE - 1
    ) * 100


def main() -> None:
    data = load_market_data(DATA_FILE)

    # Последняя свеча может быть ещё открыта.
    data = data.iloc[:-1].copy()

    windows = build_windows(data)

    if not windows:
        raise RuntimeError(
            "Недостаточно данных для Walk Forward Analysis"
        )

    results: list[WalkForwardWindow] = []

    compounded_balance = START_BALANCE

    print(
        f"Период данных: "
        f"{data.iloc[0]['datetime']} — "
        f"{data.iloc[-1]['datetime']}"
    )
    print(
        f"Обучение: {TRAIN_MONTHS} месяцев, "
        f"проверка: {TEST_MONTHS} месяцев"
    )
    print(f"Окон: {len(windows)}")
    print()

    for number, (
        train_start,
        train_end,
        test_start,
        test_end,
    ) in enumerate(windows, start=1):
        train_data = data[
            (data["datetime"] >= train_start)
            & (data["datetime"] < train_end)
        ].copy()

        test_data = data[
            (data["datetime"] >= test_start)
            & (data["datetime"] < test_end)
        ].copy()

        if train_data.empty or test_data.empty:
            continue

        best = find_best_parameters(train_data)

        test_result = run_strategy(
            data=test_data,
            short_period=best.short_period,
            long_period=best.long_period,
            initial_balance=compounded_balance,
        )

        compounded_balance *= (
            1 + test_result.return_percent / 100
        )

        results.append(
            WalkForwardWindow(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                short_period=best.short_period,
                long_period=best.long_period,
                train_return_percent=best.return_percent,
                train_drawdown_percent=(
                    best.drawdown_percent
                ),
                train_profit_factor=best.profit_factor,
                test_return_percent=(
                    test_result.return_percent
                ),
                test_drawdown_percent=(
                    test_result.drawdown_percent
                ),
                test_profit_factor=(
                    test_result.profit_factor
                ),
                test_trades=test_result.trades,
            )
        )

        print(
            f"Окно {number}/{len(windows)}: "
            f"EMA {best.short_period}/"
            f"{best.long_period}, "
            f"TRAIN {best.return_percent:+.2f}%, "
            f"TEST {test_result.return_percent:+.2f}%"
        )

    if not results:
        raise RuntimeError(
            "Не удалось выполнить ни одного окна"
        )

    print()
    print("=" * 126)
    print(
        f"{'№':>3}"
        f"{'Проверочный период':>25}"
        f"{'EMA':>10}"
        f"{'Train':>11}"
        f"{'Train DD':>11}"
        f"{'Test':>11}"
        f"{'Test DD':>11}"
        f"{'Test PF':>10}"
        f"{'Сделок':>9}"
    )
    print("=" * 126)

    for number, result in enumerate(
        results,
        start=1,
    ):
        period = (
            f"{result.test_start.date()} — "
            f"{result.test_end.date()}"
        )

        ema_name = (
            f"{result.short_period}/"
            f"{result.long_period}"
        )

        print(
            f"{number:>3}"
            f"{period:>25}"
            f"{ema_name:>10}"
            f"{result.train_return_percent:>+10.2f}%"
            f"{result.train_drawdown_percent:>10.2f}%"
            f"{result.test_return_percent:>+10.2f}%"
            f"{result.test_drawdown_percent:>10.2f}%"
            f"{result.test_profit_factor:>10.2f}"
            f"{result.test_trades:>9}"
        )

    print("=" * 126)

    total_return_percent = (
        compounded_balance / START_BALANCE - 1
    ) * 100

    profitable_windows = sum(
        item.test_return_percent > 0
        for item in results
    )

    losing_windows = sum(
        item.test_return_percent < 0
        for item in results
    )

    average_test_return = sum(
        item.test_return_percent
        for item in results
    ) / len(results)

    full_test_start = results[0].test_start
    full_test_end = results[-1].test_end

    full_test_data = data[
        (data["datetime"] >= full_test_start)
        & (data["datetime"] < full_test_end)
    ].copy()

    buy_and_hold_return = calculate_buy_and_hold(
        full_test_data
    )

    print()
    print("ИТОГ WALK FORWARD")
    print("=" * 70)
    print(f"Тестовых окон: {len(results)}")
    print(f"Прибыльных окон: {profitable_windows}")
    print(f"Убыточных окон: {losing_windows}")
    print(
        "Средняя доходность окна: "
        f"{average_test_return:+.2f}%"
    )
    print(
        "Итоговый баланс: "
        f"{compounded_balance:.2f} USDT"
    )
    print(
        "Совокупная доходность: "
        f"{total_return_percent:+.2f}%"
    )
    print(
        "Buy & Hold за проверочный период: "
        f"{buy_and_hold_return:+.2f}%"
    )


if __name__ == "__main__":
    main()
