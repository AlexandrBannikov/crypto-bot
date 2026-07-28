from pathlib import Path

import pandas as pd

from app.candle_mapper import dataframe_to_candles
from app.strategy_v2_research import (
    StrategyV2Config,
    fingerprint_candles,
    metadata,
    run_comparison,
    run_period,
)


def market_data() -> pd.DataFrame:
    datetimes = pd.date_range(
        "2024-11-01", periods=240, freq="h", tz="UTC"
    )
    close = [
        100 + index * 0.05 + (index % 12 - 6) * 0.7
        for index in range(len(datetimes))
    ]
    return pd.DataFrame(
        {
            "datetime": datetimes,
            "open": close,
            "high": [value + 2 for value in close],
            "low": [value - 2 for value in close],
            "close": close,
            "volume": [100 + index for index in range(len(close))],
        }
    )


def small_config() -> StrategyV2Config:
    return StrategyV2Config(
        fast_ema=2,
        slow_ema=5,
        train_end="2024-11-06",
    )


def test_period_runner_is_reproducible() -> None:
    data = market_data()
    first = run_period(
        data,
        period="full",
        variant="atr_adx",
        config=small_config(),
    )
    second = run_period(
        data,
        period="full",
        variant="atr_adx",
        config=small_config(),
    )

    assert first == second


def test_comparison_contains_factorial_variants() -> None:
    rows = run_comparison(market_data(), small_config())

    assert len(rows) == 12
    assert {
        (row.period, row.variant) for row in rows
    } == {
        (period, variant)
        for period in ("full", "train", "oos")
        for variant in ("baseline", "atr", "adx", "atr_adx")
    }


def test_metadata_contains_data_fingerprint(tmp_path) -> None:
    data = market_data()
    root = Path(__file__).resolve().parents[1]
    result = metadata(
        root=root,
        data_path=tmp_path / "fixture.csv",
        data=data,
        config=small_config(),
    )

    assert result["data_fingerprint"] == fingerprint_candles(
        dataframe_to_candles(data)
    )
    assert result["candles"] == len(data)
    assert result["atr"]["period"] == 14
    assert result["adx"]["minimum_adx"] == 20
