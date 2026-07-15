from collections import Counter

from app.data_loader import load_market_data
from app.engine import Candle
from app.trend_detector import (
    TrendDetector,
    TrendState,
)

DATA_FILE = "data/eth_usdt_1h_full.csv"


def main() -> None:
    frame = load_market_data(DATA_FILE)

    candles = [
        Candle(
            timestamp=i,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for i, row in enumerate(frame.itertuples())
    ]

    detector = TrendDetector()

    states = []

    for index in range(len(candles)):
        state = detector.detect(
            candles,
            index,
        )
        states.append(state)

    counts = Counter(states)

    print("=" * 70)
    print("TREND ANALYSIS")
    print("=" * 70)
    print(f"Всего свечей: {len(states)}")
    print()

    for state in (
        TrendState.UPTREND,
        TrendState.DOWNTREND,
        TrendState.SIDEWAYS,
    ):
        count = counts[state]
        percent = count / len(states) * 100

        print(
            f"{state.value:10s}: "
            f"{count:6d} "
            f"({percent:5.2f}%)"
        )

    print()

    runs = []

    current = states[0]
    length = 1

    for state in states[1:]:
        if state == current:
            length += 1
        else:
            runs.append((current, length))
            current = state
            length = 1

    runs.append((current, length))

    print("=" * 70)
    print("СРЕДНЯЯ ДЛИНА УЧАСТКОВ")
    print("=" * 70)

    for trend in (
        TrendState.UPTREND,
        TrendState.DOWNTREND,
        TrendState.SIDEWAYS,
    ):
        values = [
            length
            for state, length in runs
            if state == trend
        ]

        if not values:
            continue

        print(
            f"{trend.value:10s}: "
            f"avg={sum(values)/len(values):6.1f} "
            f"max={max(values):5d} "
            f"segments={len(values):4d}"
        )


if __name__ == "__main__":
    main()
