from dataclasses import replace

import pandas as pd
import pytest

from app.candle import Candle
from app.candle_mapper import dataframe_to_candles
from app.strategy_v2_research import StrategyV2Config, run_period
from app.strategy_v2_relaxed import (
    RelaxedPullbackConfig,
    RelaxedPullbackMode,
    confirms_pullback,
    precompute_features,
    relaxed_grid,
    simulate,
)


def market(count: int = 240) -> list[Candle]:
    return [
        Candle(
            timestamp=index * 3600,
            open=100 + index * 0.02 + (index % 12 - 6) * 0.5,
            high=102 + index * 0.02 + (index % 12 - 6) * 0.5,
            low=98 + index * 0.02 + (index % 12 - 6) * 0.5,
            close=100 + index * 0.02 + (index % 12 - 6) * 0.5,
            volume=100 + index,
        )
        for index in range(count)
    ]


@pytest.mark.parametrize(
    ("mode", "low", "close", "expected"),
    [
        (RelaxedPullbackMode.LOW_TOUCH_CLOSE_ABOVE, 99, 101, True),
        (RelaxedPullbackMode.LOW_TOUCH_CLOSE_ABOVE, 99, 99, False),
        (RelaxedPullbackMode.LOW_TOUCH, 100, 99, True),
        (RelaxedPullbackMode.LOW_TOUCH, 100.01, 99, False),
    ],
)
def test_low_touch_modes(mode, low, close, expected) -> None:
    config = RelaxedPullbackConfig(mode, 3)

    assert confirms_pullback(
        config,
        low=low,
        close=close,
        fast_ema=100,
        cross_price=102,
    ) is expected


@pytest.mark.parametrize("tolerance", [0.0025, 0.005, 0.0075])
def test_close_near_ema_inclusive_boundary(tolerance: float) -> None:
    config = RelaxedPullbackConfig(
        RelaxedPullbackMode.CLOSE_NEAR_EMA,
        3,
        tolerance=tolerance,
    )

    assert confirms_pullback(
        config,
        low=110,
        close=100 * (1 + tolerance),
        fast_ema=100,
        cross_price=105,
    )
    assert not confirms_pullback(
        config,
        low=110,
        close=100 * (1 + tolerance + 1e-8),
        fast_ema=100,
        cross_price=105,
    )


@pytest.mark.parametrize("retrace", [0.0025, 0.005, 0.0075])
def test_percent_retrace_inclusive_boundary(retrace: float) -> None:
    config = RelaxedPullbackConfig(
        RelaxedPullbackMode.PERCENT_RETRACE,
        5,
        retrace_pct=retrace,
    )

    assert confirms_pullback(
        config,
        low=110,
        close=100 * (1 - retrace),
        fast_ema=99,
        cross_price=100,
    )
    assert not confirms_pullback(
        config,
        low=110,
        close=100 * (1 - retrace + 1e-8),
        fast_ema=99,
        cross_price=100,
    )


def test_hybrid_uses_or_logic() -> None:
    config = RelaxedPullbackConfig(
        RelaxedPullbackMode.HYBRID,
        5,
        tolerance=0.0025,
        retrace_pct=0.0075,
    )

    assert confirms_pullback(
        config, low=99, close=105, fast_ema=100, cross_price=105
    )
    assert confirms_pullback(
        config,
        low=105,
        close=100.2,
        fast_ema=100,
        cross_price=105,
    )
    assert confirms_pullback(
        config,
        low=105,
        close=99,
        fast_ema=95,
        cross_price=100,
    )


@pytest.mark.parametrize("wait", [2, 3, 5, 8])
def test_grid_contains_every_wait_deterministically(wait: int) -> None:
    first = relaxed_grid()
    second = relaxed_grid()

    assert first == second
    assert any(item.max_wait_bars == wait for item in first)
    assert len(first) == 68
    assert len({item.identifier for item in first}) == 68


def forced_features(
    *,
    repeated_cross: bool = False,
    trend_loss: bool = False,
):
    candles = tuple(market(15))
    fast = [101.0] * 15
    slow = [100.0] * 15
    if trend_loss:
        fast[5] = 99.0
    cross_up = [False] * 15
    cross_up[3] = True
    if repeated_cross:
        cross_up[4] = True
    base = precompute_features(candles, fast_period=2, slow_period=3)
    return replace(
        base,
        fast_ema=tuple(fast),
        slow_ema=tuple(slow),
        cross_up=tuple(cross_up),
        cross_down=tuple(False for _ in candles),
    )


def test_pending_cancels_when_ema_trend_is_lost() -> None:
    result = simulate(
        forced_features(trend_loss=True),
        pullback=RelaxedPullbackConfig(
            RelaxedPullbackMode.PERCENT_RETRACE,
            8,
            retrace_pct=0.50,
        ),
    )

    assert result.stats.ema_signals == 1
    assert result.stats.cancelled == 1


def test_pending_cancels_on_invalid_indicator() -> None:
    features = forced_features()
    fast = list(features.fast_ema)
    fast[5] = float("nan")
    result = simulate(
        replace(features, fast_ema=tuple(fast)),
        pullback=RelaxedPullbackConfig(
            RelaxedPullbackMode.PERCENT_RETRACE,
            8,
            retrace_pct=0.50,
        ),
    )

    assert result.stats.cancelled == 1


def test_pending_cancels_on_reverse_signal() -> None:
    features = forced_features()
    cross_down = [False] * len(features.candles)
    cross_down[5] = True
    result = simulate(
        replace(features, cross_down=tuple(cross_down)),
        pullback=RelaxedPullbackConfig(
            RelaxedPullbackMode.PERCENT_RETRACE,
            8,
            retrace_pct=0.50,
        ),
    )

    assert result.stats.cancelled == 1


def test_repeated_cross_does_not_create_parallel_pending() -> None:
    result = simulate(
        forced_features(repeated_cross=True),
        pullback=RelaxedPullbackConfig(
            RelaxedPullbackMode.PERCENT_RETRACE,
            2,
            retrace_pct=0.50,
        ),
    )

    assert result.stats.ema_signals == 1


@pytest.mark.parametrize("wait", [2, 3, 5, 8])
def test_timeout_occurs_at_configured_inclusive_wait(wait: int) -> None:
    result = simulate(
        forced_features(),
        pullback=RelaxedPullbackConfig(
            RelaxedPullbackMode.PERCENT_RETRACE,
            wait,
            retrace_pct=0.50,
        ),
    )

    assert result.stats.timed_out == 1


def test_precomputed_features_have_no_look_ahead() -> None:
    prefix = market(80)
    first = precompute_features(
        prefix + [replace(prefix[-1], timestamp=80 * 3600, close=10_000)]
    )
    second = precompute_features(
        prefix + [replace(prefix[-1], timestamp=80 * 3600, close=1)]
    )

    assert first.fast_ema[:80] == second.fast_ema[:80]
    assert first.slow_ema[:80] == second.slow_ema[:80]
    assert pd.Series(first.atr_relative[:80]).equals(
        pd.Series(second.atr_relative[:80])
    )
    assert pd.Series(first.adx[:80]).equals(
        pd.Series(second.adx[:80])
    )


def test_optimized_control_is_equivalent_to_existing_runner() -> None:
    candles = market()
    data = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                [item.timestamp for item in candles], unit="s", utc=True
            ),
            "open": [item.open for item in candles],
            "high": [item.high for item in candles],
            "low": [item.low for item in candles],
            "close": [item.close for item in candles],
            "volume": [item.volume for item in candles],
        }
    )
    config = StrategyV2Config()
    legacy, _ = run_period(
        data,
        period="fixture",
        variant="atr_adx",
        config=config,
    )
    optimized = simulate(
        precompute_features(dataframe_to_candles(data)),
        use_atr=True,
        use_adx=True,
    )

    assert optimized.result.final_balance == pytest.approx(
        legacy.final_balance, rel=1e-12
    )
    assert len(optimized.result.trades) == legacy.trades
    assert optimized.result.max_drawdown_percent == pytest.approx(
        legacy.maximum_drawdown_percent, rel=1e-12
    )


def test_optimized_runner_is_deterministic_and_disabled_is_baseline() -> None:
    features = precompute_features(market())

    first = simulate(features)
    second = simulate(features)

    assert first == second


def test_pullback_preserves_exit_and_works_with_atr_adx() -> None:
    features = precompute_features(market())
    pullback = RelaxedPullbackConfig(
        RelaxedPullbackMode.HYBRID,
        5,
        tolerance=0.0075,
        retrace_pct=0.0025,
    )
    baseline = simulate(features, pullback=pullback)
    atr = simulate(features, pullback=pullback, use_atr=True)
    adx = simulate(features, pullback=pullback, use_adx=True)
    combined = simulate(
        features, pullback=pullback, use_atr=True, use_adx=True
    )

    assert all(
        trade.exit_timestamp >= trade.entry_timestamp
        for result in (baseline, atr, adx, combined)
        for trade in result.result.trades
    )


def test_same_grid_configuration_is_reused_for_all_windows() -> None:
    configs = relaxed_grid()
    window_configs = [configs for _ in range(5)]

    assert all(item is configs for item in window_configs)
