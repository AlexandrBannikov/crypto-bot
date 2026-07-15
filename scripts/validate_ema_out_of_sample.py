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

TRAIN_END = pd.Timestamp("2025-01-01", tz="UTC")

SHORT_PERIODS = [5, 10, 15, 20, 30, 40, 50]
LONG_PERIODS = [50, 80, 100, 150, 200, 250, 300]

TOP_PARAMETERS = 10


@dataclass(frozen=True)
class Result:
    short_period: int
    long_period: int
    return_percent: float
    drawdown_percent: float
    profit_factor: float
    trades: int


def run_strategy(
    data: pd.DataFrame,
    short_period: int,
    long_period: int,
) -> Result:
    candles = dataframe_to_candles(data)

    strategy = EMACrossStrategy(
        short_period=short_period,
        long_period=long_period,
    )

    engine = BacktestEngine(
        initial_balance=START_BALANCE,
        commission_rate=COMMISSION_RATE,
    )

    result = engine.run(
        candles=candles,
        strategy=strategy,
    )

    return Result(
        short_period=short_period,
        long_period=long_period,
        return_percent=result.total_return_percent,
        drawdown_percent=result.max_drawdown_percent,
        profit_factor=result.profit_factor,
        trades=len(result.trades),
    )


def calculate_buy_and_hold(
    data: pd.DataFrame,
) -> float:
    first_price = float(data.iloc[0]["open"])
    last_price = float(data.iloc[-1]["close"])

    entry_fee = START_BALANCE * COMMISSION_RATE
    quantity = (START_BALANCE - entry_fee) / first_price

    gross_value = quantity * last_price
    exit_fee = gross_value * COMMISSION_RATE
    final_balance = gross_value - exit_fee

    return (final_balance / START_BALANCE - 1) * 100


def main() -> None:
    data = load_market_data(DATA_FILE)
    data = data.iloc[:-1].copy()

    train_data = data[
        data["datetime"] < TRAIN_END
    ].copy()

    test_data = data[
        data["datetime"] >= TRAIN_END
    ].copy()

    print(
        f"Обучение: {train_data.iloc[0]['datetime']} — "
        f"{train_data.iloc[-1]['datetime']}"
    )
    print(
        f"Проверка: {test_data.iloc[0]['datetime']} — "
        f"{test_data.iloc[-1]['datetime']}"
    )
    print()

    training_results: list[Result] = []

    for short_period in SHORT_PERIODS:
        for long_period in LONG_PERIODS:
            if short_period >= long_period:
                continue

            training_results.append(
                run_strategy(
                    data=train_data,
                    short_period=short_period,
                    long_period=long_period,
                )
            )

    training_results.sort(
        key=lambda item: item.return_percent,
        reverse=True,
    )

    best_parameters = training_results[:TOP_PARAMETERS]

    print("Лучшие параметры на обучающей выборке:")
    print("=" * 92)
    print(
        f"{'EMA':>10}"
        f"{'Train Return':>16}"
        f"{'Train DD':>12}"
        f"{'Train PF':>12}"
        f"{'Test Return':>16}"
        f"{'Test DD':>12}"
        f"{'Test PF':>12}"
    )
    print("=" * 92)

    for train_result in best_parameters:
        test_result = run_strategy(
            data=test_data,
            short_period=train_result.short_period,
            long_period=train_result.long_period,
        )

        ema_name = (
            f"{train_result.short_period}/"
            f"{train_result.long_period}"
        )

        print(
            f"{ema_name:>10}"
            f"{train_result.return_percent:>+15.2f}%"
            f"{train_result.drawdown_percent:>11.2f}%"
            f"{train_result.profit_factor:>12.2f}"
            f"{test_result.return_percent:>+15.2f}%"
            f"{test_result.drawdown_percent:>11.2f}%"
            f"{test_result.profit_factor:>12.2f}"
        )

    print("=" * 92)
    print(
        "Buy & Hold на проверочной выборке: "
        f"{calculate_buy_and_hold(test_data):+.2f}%"
    )


if __name__ == "__main__":
    main()
