from pathlib import Path

import pandas as pd

from app.data_loader import load_market_data
from app.engine import BacktestEngine, Candle
from app.trend_pullback_strategy import TrendPullbackStrategy


DATA_FILE = Path("data/eth_usdt_5m.csv")
START_BALANCE = 1000.0
COMMISSION_RATE = 0.001


def dataframe_to_candles(
    data: pd.DataFrame,
) -> list[Candle]:
    return [
        Candle(
            timestamp=int(row.datetime.timestamp()),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in data.itertuples(index=False)
    ]


def print_result(result) -> None:
    print("=" * 70)
    print("TREND PULLBACK STRATEGY")
    print("=" * 70)
    print(f"Стартовый баланс: {result.initial_balance:.2f} USDT")
    print(f"Конечный баланс: {result.final_balance:.2f} USDT")
    print(f"Прибыль: {result.total_profit:+.2f} USDT")
    print(f"Доходность: {result.total_return_percent:+.2f}%")
    print(
        "Максимальная просадка: "
        f"{result.max_drawdown_percent:.2f}%"
    )
    print(f"Закрытых сделок: {len(result.trades)}")
    long_trades = sum(
        trade.side.value == "long"
        for trade in result.trades
    )

    short_trades = sum(
        trade.side.value == "short"
        for trade in result.trades
    )

    print(f"LONG-сделок: {long_trades}")
    print(f"SHORT-сделок: {short_trades}")
    print(f"Прибыльных сделок: {result.winning_trades}")
    print(f"Убыточных сделок: {result.losing_trades}")
    print(f"Win rate: {result.win_rate_percent:.2f}%")
    print(f"Gross profit: {result.gross_profit:.2f} USDT")
    print(f"Gross loss: {result.gross_loss:.2f} USDT")
    print(f"Profit factor: {result.profit_factor:.2f}")
    print(
        "Средняя прибыльная сделка: "
        f"{result.average_winning_trade_percent:+.2f}%"
    )
    print(
        "Средняя убыточная сделка: "
        f"{result.average_losing_trade_percent:+.2f}%"
    )
    print(f"Payoff ratio: {result.payoff_ratio:.2f}")
    print(
        "Ожидаемый результат сделки: "
        f"{result.expectancy_percent:+.2f}%"
    )

    if result.trades:
        total_fees = sum(
            trade.entry_fee + trade.exit_fee
            for trade in result.trades
        )
        best_trade = max(
            trade.profit_percent
            for trade in result.trades
        )
        worst_trade = min(
            trade.profit_percent
            for trade in result.trades
        )

        print(f"Комиссии: {total_fees:.2f} USDT")
        print(f"Лучшая сделка: {best_trade:+.2f}%")
        print(f"Худшая сделка: {worst_trade:+.2f}%")


    for side_name in ("long", "short"):
        side_trades = [
            trade
            for trade in result.trades
            if trade.side.value == side_name
        ]

        side_winners = [
            trade
            for trade in side_trades
            if trade.profit > 0
        ]

        side_losers = [
            trade
            for trade in side_trades
            if trade.profit < 0
        ]

        side_gross_profit = sum(
            trade.profit
            for trade in side_winners
        )

        side_gross_loss = abs(
            sum(
                trade.profit
                for trade in side_losers
            )
        )

        side_profit = sum(
            trade.profit
            for trade in side_trades
        )

        side_win_rate = (
            len(side_winners)
            / len(side_trades)
            * 100
            if side_trades
            else 0.0
        )

        side_profit_factor = (
            side_gross_profit / side_gross_loss
            if side_gross_loss > 0
            else 0.0
        )

        print()
        print(f"--- {side_name.upper()} ---")
        print(f"Сделок: {len(side_trades)}")
        print(f"Результат: {side_profit:+.2f} USDT")
        print(f"Win rate: {side_win_rate:.2f}%")
        print(f"Profit factor: {side_profit_factor:.2f}")


def main() -> None:
    data = load_market_data(DATA_FILE)

    # Последняя свеча может быть ещё открыта.
    data = data.iloc[:-1].copy()

    candles = dataframe_to_candles(data)

    strategy = TrendPullbackStrategy(
        pullback_ema_period=20,
        trend_fast_period=50,
        trend_slow_period=200,
        trend_slope_lookback=5,
        trend_min_separation_percent=0.1,
        adx_period=14,
        minimum_adx=25.0,
        allow_short=False,
    )

    engine = BacktestEngine(
        initial_balance=START_BALANCE,
        commission_rate=COMMISSION_RATE,
    )

    result = engine.run(
        candles=candles,
        strategy=strategy,
    )

    print(
        f"Период: {data.iloc[0]['datetime']} — "
        f"{data.iloc[-1]['datetime']}"
    )
    print(f"Свечей: {len(candles)}")
    print()

    print_result(result)


if __name__ == "__main__":
    main()
