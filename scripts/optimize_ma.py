from pathlib import Path

import pandas as pd


DATA_FILE = Path("data/eth_usdt_1h.csv")

START_BALANCE = 1000.0
FEE_RATE = 0.001

FAST_PERIODS = [5, 10, 15, 20, 25, 30, 40]
SLOW_PERIODS = [30, 40, 50, 60, 80, 100, 150, 200]


def calculate_max_drawdown(equity_values: list[float]) -> float:
    equity = pd.Series(equity_values, dtype="float64")
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(drawdown.min() * 100)


def run_backtest(
    source_df: pd.DataFrame,
    fast_period: int,
    slow_period: int,
) -> dict:
    df = source_df.copy()

    df["fast_ma"] = df["close"].rolling(fast_period).mean()
    df["slow_ma"] = df["close"].rolling(slow_period).mean()

    balance = START_BALANCE
    eth_amount = 0.0
    in_position = False

    operations = 0
    completed_trades = 0
    winning_trades = 0
    total_fees = 0.0

    entry_value = 0.0
    equity_curve = []

    for index in range(1, len(df)):
        row = df.iloc[index]
        previous = df.iloc[index - 1]

        price = float(row["close"])

        if pd.isna(row["fast_ma"]) or pd.isna(row["slow_ma"]):
            equity_curve.append(balance)
            continue

        buy_signal = (
            previous["fast_ma"] <= previous["slow_ma"]
            and row["fast_ma"] > row["slow_ma"]
        )

        sell_signal = (
            previous["fast_ma"] >= previous["slow_ma"]
            and row["fast_ma"] < row["slow_ma"]
        )

        if buy_signal and not in_position:
            fee = balance * FEE_RATE
            amount_for_purchase = balance - fee

            eth_amount = amount_for_purchase / price
            entry_value = balance
            balance = 0.0
            in_position = True

            total_fees += fee
            operations += 1

        elif sell_signal and in_position:
            gross_value = eth_amount * price
            fee = gross_value * FEE_RATE
            balance = gross_value - fee

            if balance > entry_value:
                winning_trades += 1

            completed_trades += 1
            total_fees += fee
            operations += 1

            eth_amount = 0.0
            in_position = False

        if in_position:
            current_equity = eth_amount * price * (1 - FEE_RATE)
        else:
            current_equity = balance

        equity_curve.append(current_equity)

    last_price = float(df.iloc[-1]["close"])

    if in_position:
        gross_value = eth_amount * last_price
        closing_fee = gross_value * FEE_RATE
        final_balance = gross_value - closing_fee
        total_fees += closing_fee

        if final_balance > entry_value:
            winning_trades += 1

        completed_trades += 1
    else:
        final_balance = balance

    profit = final_balance - START_BALANCE
    profit_percent = profit / START_BALANCE * 100

    win_rate = (
        winning_trades / completed_trades * 100
        if completed_trades
        else 0.0
    )

    max_drawdown = calculate_max_drawdown(equity_curve)

    return {
        "fast": fast_period,
        "slow": slow_period,
        "final_balance": final_balance,
        "profit_percent": profit_percent,
        "max_drawdown_percent": max_drawdown,
        "operations": operations,
        "completed_trades": completed_trades,
        "win_rate_percent": win_rate,
        "fees": total_fees,
    }


def calculate_buy_and_hold(df: pd.DataFrame) -> float:
    first_price = float(df.iloc[0]["close"])
    last_price = float(df.iloc[-1]["close"])

    purchase_fee = START_BALANCE * FEE_RATE
    eth_amount = (START_BALANCE - purchase_fee) / first_price

    gross_value = eth_amount * last_price
    sale_fee = gross_value * FEE_RATE

    final_balance = gross_value - sale_fee
    return (final_balance / START_BALANCE - 1) * 100


def main() -> None:
    df = pd.read_csv(DATA_FILE, parse_dates=["datetime"])

    # Последняя свеча может быть ещё незакрытой.
    df = df.iloc[:-1].copy()

    results = []

    for fast_period in FAST_PERIODS:
        for slow_period in SLOW_PERIODS:
            if fast_period >= slow_period:
                continue

            result = run_backtest(
                source_df=df,
                fast_period=fast_period,
                slow_period=slow_period,
            )
            results.append(result)

    results_df = pd.DataFrame(results)

    results_df = results_df.sort_values(
        by=["profit_percent", "max_drawdown_percent"],
        ascending=[False, False],
    )

    output_file = Path("reports/ma_optimization.csv")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_file, index=False)

    buy_and_hold = calculate_buy_and_hold(df)

    print("=" * 90)
    print("ОПТИМИЗАЦИЯ СТРАТЕГИИ ПЕРЕСЕЧЕНИЯ СРЕДНИХ")
    print("=" * 90)
    print(f"Период: {df.iloc[0]['datetime']} — {df.iloc[-1]['datetime']}")
    print(f"Свечей: {len(df)}")
    print(f"Проверено комбинаций: {len(results_df)}")
    print(f"Купить и держать ETH: {buy_and_hold:+.2f}%")
    print()
    print("10 лучших комбинаций:")
    print(
        results_df.head(10).to_string(
            index=False,
            formatters={
                "final_balance": "{:.2f}".format,
                "profit_percent": "{:+.2f}".format,
                "max_drawdown_percent": "{:.2f}".format,
                "win_rate_percent": "{:.1f}".format,
                "fees": "{:.2f}".format,
            },
        )
    )
    print()
    print(f"Полный отчёт: {output_file}")
    print("=" * 90)


if __name__ == "__main__":
    main()

