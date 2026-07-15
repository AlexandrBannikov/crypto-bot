from pathlib import Path

from app.candle_mapper import dataframe_to_candles
from app.data_loader import load_market_data
from app.ema_cross_strategy import EMACrossStrategy
from app.ema_trend_strategy import EMATrendStrategy
from app.engine import BacktestEngine, BacktestResult
from app.trend_pullback_strategy import TrendPullbackStrategy


DATA_FILE = Path("data/eth_usdt_1h_full.csv")
START_BALANCE = 1000.0
COMMISSION_RATE = 0.001


def print_header() -> None:
    print()
    print("=" * 112)
    print(
        f"{'Стратегия':<28}"
        f"{'Доходность':>12}"
        f"{'Просадка':>11}"
        f"{'PF':>9}"
        f"{'Win rate':>11}"
        f"{'Сделок':>9}"
        f"{'LONG':>8}"
        f"{'SHORT':>8}"
        f"{'Баланс':>12}"
    )
    print("=" * 112)


def print_result(
    name: str,
    result: BacktestResult,
) -> None:
    long_trades = sum(
        trade.side.value == "long"
        for trade in result.trades
    )

    short_trades = sum(
        trade.side.value == "short"
        for trade in result.trades
    )

    print(
        f"{name:<28}"
        f"{result.total_return_percent:>+11.2f}%"
        f"{result.max_drawdown_percent:>10.2f}%"
        f"{result.profit_factor:>9.2f}"
        f"{result.win_rate_percent:>10.2f}%"
        f"{len(result.trades):>9}"
        f"{long_trades:>8}"
        f"{short_trades:>8}"
        f"{result.final_balance:>12.2f}"
    )


def calculate_buy_and_hold(
    first_price: float,
    last_price: float,
) -> tuple[float, float]:
    entry_fee = START_BALANCE * COMMISSION_RATE
    invested_amount = START_BALANCE - entry_fee

    quantity = invested_amount / first_price
    gross_value = quantity * last_price
    exit_fee = gross_value * COMMISSION_RATE
    final_balance = gross_value - exit_fee

    return_percent = (
        final_balance / START_BALANCE - 1
    ) * 100

    return final_balance, return_percent


def print_buy_and_hold(
    first_price: float,
    last_price: float,
) -> None:
    final_balance, return_percent = calculate_buy_and_hold(
        first_price=first_price,
        last_price=last_price,
    )

    print(
        f"{'Buy & Hold ETH':<28}"
        f"{return_percent:>+11.2f}%"
        f"{'-':>11}"
        f"{'-':>9}"
        f"{'-':>11}"
        f"{1:>9}"
        f"{1:>8}"
        f"{0:>8}"
        f"{final_balance:>12.2f}"
    )


def main() -> None:
    data = load_market_data(DATA_FILE)

    # Последняя свеча может быть ещё открыта.
    data = data.iloc[:-1].copy()

    candles = dataframe_to_candles(data)

    strategies = [
        (
            "EMA Cross 20/50",
            EMACrossStrategy(
                short_period=20,
                long_period=50,
            ),
        ),
        (
            "EMA Cross 50/200",
            EMACrossStrategy(
                short_period=50,
                long_period=200,
            ),
        ),
        (
            "EMA Trend 40/300",
            EMATrendStrategy(
                fast_period=40,
                slow_period=300,
                trend_period=300,
                trend_slope_lookback=24,
            ),
        ),
        (
            "Trend Pullback LONG/SHORT",
            TrendPullbackStrategy(
                pullback_ema_period=20,
                trend_fast_period=50,
                trend_slow_period=200,
                trend_slope_lookback=5,
                trend_min_separation_percent=0.1,
                adx_period=14,
                minimum_adx=25.0,
                allow_short=True,
            ),
        ),
        (
            "Trend Pullback LONG",
            TrendPullbackStrategy(
                pullback_ema_period=20,
                trend_fast_period=50,
                trend_slow_period=200,
                trend_slope_lookback=5,
                trend_min_separation_percent=0.1,
                adx_period=14,
                minimum_adx=25.0,
                allow_short=False,
            ),
        ),
    ]

    print(
        f"Период: {data.iloc[0]['datetime']} — "
        f"{data.iloc[-1]['datetime']}"
    )
    print(f"Свечей: {len(candles)}")
    print(f"Комиссия за операцию: {COMMISSION_RATE * 100:.2f}%")

    print_header()

    print_buy_and_hold(
        first_price=float(data.iloc[0]["open"]),
        last_price=float(data.iloc[-1]["close"]),
    )

    for name, strategy in strategies:
        engine = BacktestEngine(
            initial_balance=START_BALANCE,
            commission_rate=COMMISSION_RATE,
        )

        result = engine.run(
            candles=candles,
            strategy=strategy,
        )

        print_result(name, result)

    print("=" * 112)


if __name__ == "__main__":
    main()
