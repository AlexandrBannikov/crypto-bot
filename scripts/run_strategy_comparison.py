from pathlib import Path

import pandas as pd

from app.backtester import run_backtest
from app.data_loader import load_market_data
from app.strategies import ma_cross_signals, rsi_signals


DATA_FILE = Path("data/eth_usdt_1h_full.csv")
START_BALANCE = 1000.0
FEE_RATE = 0.001


def print_result(name: str, result) -> None:
    print()
    print("=" * 70)
    print(name)
    print("=" * 70)
    print(f"Стартовый баланс: {result.start_balance:.2f} USDT")
    print(f"Конечный баланс: {result.final_balance:.2f} USDT")
    print(f"Доходность: {result.return_percent:+.2f}%")
    print(f"Максимальная просадка: {result.max_drawdown_percent:.2f}%")
    print(f"Комиссии: {result.total_fees:.2f} USDT")
    print(f"Операций: {result.operations}")
    print(f"Закрытых сделок: {result.completed_trades}")
    print(f"Прибыльных сделок: {result.winning_trades}")
    print(f"Win rate: {result.win_rate_percent:.2f}%")


def calculate_buy_and_hold(
    data: pd.DataFrame,
    start_balance: float,
    fee_rate: float,
) -> float:
    first_price = float(data.iloc[0]["close"])
    last_price = float(data.iloc[-1]["close"])

    buy_fee = start_balance * fee_rate
    quantity = (start_balance - buy_fee) / first_price

    gross_value = quantity * last_price
    sell_fee = gross_value * fee_rate

    final_balance = gross_value - sell_fee

    return (final_balance / start_balance - 1) * 100


def main() -> None:
    data = load_market_data(DATA_FILE)

    # Последняя свеча может быть ещё открытой.
    data = data.iloc[:-1].copy()

    ma_signals = ma_cross_signals(
        data,
        fast_period=10,
        slow_period=40,
    )

    ma_result = run_backtest(
        data,
        ma_signals,
        start_balance=START_BALANCE,
        fee_rate=FEE_RATE,
    )

    rsi_signal_series = rsi_signals(
        data,
        period=14,
        buy_level=30,
        sell_level=70,
    )

    rsi_result = run_backtest(
        data,
        rsi_signal_series,
        start_balance=START_BALANCE,
        fee_rate=FEE_RATE,
    )

    buy_and_hold = calculate_buy_and_hold(
        data,
        start_balance=START_BALANCE,
        fee_rate=FEE_RATE,
    )

    print("=" * 70)
    print("СРАВНЕНИЕ СТРАТЕГИЙ ETH/USDT")
    print("=" * 70)
    print(f"Период: {data.iloc[0]['datetime']} — {data.iloc[-1]['datetime']}")
    print(f"Свечей: {len(data)}")
    print(f"Купить и держать ETH: {buy_and_hold:+.2f}%")

    print_result("SMA 10 / 40", ma_result)
    print_result("RSI 14 / 30 / 70", rsi_result)


if __name__ == "__main__":
    main()

