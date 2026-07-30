from app.engine import Candle
from app.strategy_experiments import (
    ExperimentConfig,
    format_experiment_table,
    run_experiments,
)


def sample_candles() -> tuple[Candle, ...]:
    prices = (
        [100 - index for index in range(12)]
        + [88 + index * 3 for index in range(15)]
        + [133 - index * 3 for index in range(15)]
        + [88 + index * 2 for index in range(15)]
    )
    return tuple(
        Candle(
            timestamp=1_700_000_000 + index * 3600,
            open=price,
            high=price + 1,
            low=price - 1,
            close=price,
            volume=1,
        )
        for index, price in enumerate(prices)
    )


def test_compares_multiple_configurations_with_train_and_test() -> None:
    configs = (
        ExperimentConfig("control", 2, 5),
        ExperimentConfig(
            "filtered",
            3,
            8,
            price_confirmation_percent=0.1,
            minimum_trend_spread_percent=0.05,
        ),
    )

    results = run_experiments(
        sample_candles(),
        configs=configs,
        commission_rate=0.001,
    )

    assert [result.name for result in results] == ["control", "filtered"]
    assert all(result.parameters for result in results)
    assert all(result.full.fees >= 0 for result in results)
    assert all(result.full.blocked_entry_reasons for result in results)
    assert "train %" in format_experiment_table(results)
    assert "test %" in format_experiment_table(results)
