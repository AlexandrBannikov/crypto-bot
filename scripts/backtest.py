from pathlib import Path

import pandas as pd


DATA_FILE = Path("data/eth_usdt_1h.csv")

START_BALANCE = 1000.0
FAST_MA = 20
SLOW_MA = 50
FEE_RATE = 0.001


def main() -> None:
    df = pd.read_csv(DATA_FILE, parse_dates=["datetime"])

    df["fast_ma"] = df["close"].rolling(FAST_MA).mean()
    df["slow_ma"] = df["close"].rolling(SLOW_MA).mean()

    balance = START_BALANCE
    eth_amount = 0.0
    in_position = False

    trades = []
    total_fees = 0.0

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row["fast_ma"]) or pd.isna(row["slow_ma"]):
            continue

        buy_signal = (
            prev["fast_ma"] <= prev["slow_ma"]
            and row["fast_ma"] > row["slow_ma"]
        )

        sell_signal = (
            prev["fast_ma"] >= prev["slow_ma"]
            and row["fast_ma"] < row["slow_ma"]
        )

        price = float(row["close"])

        if buy_signal and not in_position:
            fee = balance * FEE_RATE
            total_fees += fee

            amount_to_buy = balance - fee
            eth_amount = amount_to_buy / price
            balance = 0.0
            in_position = True

            trades.append(
                {
                    "type": "BUY",
                    "datetime": row["datetime"],
                    "price": price,
                    "fee": fee,
                }
            )

        elif sell_signal and in_position:
            gross_value = eth_amount * price
            fee = gross_value * FEE_RATE
            total_fees += fee

            balance = gross_value - fee
            eth_amount = 0.0
            in_position = False

            trades.append(
                {
                    "type": "SELL",
                    "datetime": row["datetime"],
                    "price": price,
                    "fee": fee,
                }
            )

    last_price = float(df.iloc[-1]["close"])

    if in_position:
        final_balance = eth_amount * last_price
    else:
        final_balance = balance

    profit = final_balance - START_BALANCE
    profit_percent = profit / START_BALANCE * 100

    print("=" * 60)
    print("BACKTEST ETH/USDT")
    print("=" * 60)
    print(f"Период: {df.iloc[0]['datetime']} — {df.iloc[-1]['datetime']}")
    print(f"Стартовый баланс: {START_BALANCE:.2f} USDT")
    print(f"Конечный баланс: {final_balance:.2f} USDT")
    print(f"Результат: {profit:+.2f} USDT ({profit_percent:+.2f}%)")
    print(f"Комиссии: {total_fees:.2f} USDT")
    print(f"Операций: {len(trades)}")
    print("=" * 60)

    if trades:
        print("\nПоследние операции:")
        for trade in trades[-10:]:
            print(
                f"{trade['datetime']} | "
                f"{trade['type']} | "
                f"{trade['price']:.2f} | "
                f"fee={trade['fee']:.4f}"
            )


if __name__ == "__main__":
    main()

