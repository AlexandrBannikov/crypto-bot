from dataclasses import dataclass
from pathlib import Path

from app.candle_mapper import dataframe_to_candles
from app.data_loader import load_market_data
from app.ema_cross_strategy import EMACrossStrategy
from app.engine import BacktestEngine


DATA_FILE = Path("data/eth_usdt_1h_full.csv")
START_BALANCE = 1000.0
COMMISSION_RATE = 0.001

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

TOP_RESULTS = 20


@dataclass(frozen=True)
class OptimizationResult:
    short_period: int
    long_period: int
    return_percent: float
    max_drawdown_percent: float
    profit_factor: float
    win_rate_percent: float
    trades: int
    final_balance: float


def main() -> None:
    data = load_market_data(DATA_FILE)

    # Последняя свеча может быть ещё открыта.
    data = data.iloc[:-1].copy()

    candles = dataframe_to_candles(data)

    results: list[OptimizationResult] = []

    total_combinations = sum(
        1
        for short_period in SHORT_PERIODS
        for long_period in LONG_PERIODS
        if short_period < long_period
    )

    print(
        f"Период: {data.iloc[0]['datetime']} — "
        f"{data.iloc[-1]['datetime']}"
    )
    print(f"Свечей: {len(candles)}")
    print(f"Комбинаций: {total_combinations}")
    print()

    completed = 0

    for short_period in SHORT_PERIODS:
        for long_period in LONG_PERIODS:
            if short_period >= long_period:
                continue

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

            results.append(
                OptimizationResult(
                    short_period=short_period,
                    long_period=long_period,
                    return_percent=(
                        result.total_return_percent
                    ),
                    max_drawdown_percent=(
                        result.max_drawdown_percent
                    ),
                    profit_factor=result.profit_factor,
                    win_rate_percent=(
                        result.win_rate_percent
                    ),
                    trades=len(result.trades),
                    final_balance=result.final_balance,
                )
            )

            completed += 1
            print(
                f"\rПроверено: "
                f"{completed}/{total_combinations}",
                end="",
                flush=True,
            )

    print()
    print()

    results.sort(
        key=lambda item: item.return_percent,
        reverse=True,
    )

    print("=" * 106)
    print(
        f"{'Место':>6}"
        f"{'EMA':>12}"
        f"{'Доходность':>14}"
        f"{'Просадка':>12}"
        f"{'PF':>10}"
        f"{'Win rate':>12}"
        f"{'Сделок':>10}"
        f"{'Баланс':>14}"
    )
    print("=" * 106)

    for place, item in enumerate(
        results[:TOP_RESULTS],
        start=1,
    ):
        ema_name = (
            f"{item.short_period}/"
            f"{item.long_period}"
        )

        print(
            f"{place:>6}"
            f"{ema_name:>12}"
            f"{item.return_percent:>+13.2f}%"
            f"{item.max_drawdown_percent:>11.2f}%"
            f"{item.profit_factor:>10.2f}"
            f"{item.win_rate_percent:>11.2f}%"
            f"{item.trades:>10}"
            f"{item.final_balance:>14.2f}"
        )

    print("=" * 106)


if __name__ == "__main__":
    main()
