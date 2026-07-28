from dataclasses import replace

import pandas as pd
import pytest

from app.candle import Candle
from app.ema_cross_strategy import EMACrossStrategy
from app.engine import BacktestEngine
from app.strategy_v2_filters import (
    ADXFilterConfig,
    ADXStrengthFilter,
    ATRFilterConfig,
    ATRVolatilityFilter,
    AllEntryFilters,
    EntryFilterDecision,
    EntryFilterReason,
    ResearchEntryFilteredStrategy,
)
from app.trading_types import TradeAction


def candles(count: int = 60) -> list[Candle]:
    return [
        Candle(
            timestamp=index * 3600,
            open=100 + index * 0.2,
            high=102 + index * 0.2,
            low=98 + index * 0.2,
            close=100 + index * 0.2,
            volume=10 + index,
        )
        for index in range(count)
    ]


def patch_last(monkeypatch, name: str, value: float) -> None:
    monkeypatch.setattr(
        f"app.strategy_v2_filters.{name}",
        lambda frame, period: pd.Series(
            [float("nan")] * (len(frame) - 1) + [value]
        ),
    )


def test_disabled_filters_are_identical_to_baseline() -> None:
    market = candles(80)
    baseline = BacktestEngine().run(
        market, EMACrossStrategy(2, 5)
    )
    filtered = BacktestEngine().run(
        market,
        ResearchEntryFilteredStrategy(
            EMACrossStrategy(2, 5),
            AllEntryFilters(
                (
                    ATRVolatilityFilter(ATRFilterConfig()),
                    ADXStrengthFilter(ADXFilterConfig()),
                )
            ),
        ),
    )

    assert filtered == baseline


@pytest.mark.parametrize("relative_atr", [0.005, 0.012, 0.020])
def test_atr_inclusive_range_allows(
    monkeypatch, relative_atr: float
) -> None:
    market = candles(20)
    patch_last(
        monkeypatch,
        "atr",
        relative_atr * market[-1].close,
    )
    decision = ATRVolatilityFilter(
        ATRFilterConfig(enabled=True)
    ).evaluate(market, len(market) - 1)

    assert decision.allowed is True
    assert decision.reason is EntryFilterReason.ALLOWED


@pytest.mark.parametrize("relative_atr", [0.0049, 0.0201])
def test_atr_outside_range_blocks(
    monkeypatch, relative_atr: float
) -> None:
    market = candles(20)
    patch_last(
        monkeypatch,
        "atr",
        relative_atr * market[-1].close,
    )
    decision = ATRVolatilityFilter(
        ATRFilterConfig(enabled=True)
    ).evaluate(market, len(market) - 1)

    assert decision.allowed is False
    assert decision.reason is EntryFilterReason.BLOCKED_BY_ATR


def test_atr_warmup_is_structured() -> None:
    market = candles(5)
    decision = ATRVolatilityFilter(
        ATRFilterConfig(enabled=True, period=14)
    ).evaluate(market, len(market) - 1)

    assert decision.allowed is False
    assert decision.reason is EntryFilterReason.INSUFFICIENT_HISTORY


@pytest.mark.parametrize("value", [20.0, 35.0])
def test_adx_inclusive_threshold_allows(
    monkeypatch, value: float
) -> None:
    patch_last(monkeypatch, "adx", value)
    market = candles(30)
    decision = ADXStrengthFilter(
        ADXFilterConfig(enabled=True, minimum_adx=20)
    ).evaluate(market, len(market) - 1)

    assert decision.allowed is True
    assert decision.reason is EntryFilterReason.ALLOWED


def test_adx_below_threshold_blocks(monkeypatch) -> None:
    patch_last(monkeypatch, "adx", 19.99)
    market = candles(30)
    decision = ADXStrengthFilter(
        ADXFilterConfig(enabled=True, minimum_adx=20)
    ).evaluate(market, len(market) - 1)

    assert decision.allowed is False
    assert decision.reason is EntryFilterReason.BLOCKED_BY_ADX


def test_adx_warmup_is_structured() -> None:
    market = candles(10)
    decision = ADXStrengthFilter(
        ADXFilterConfig(enabled=True, period=14)
    ).evaluate(market, len(market) - 1)

    assert decision.allowed is False
    assert decision.reason is EntryFilterReason.INSUFFICIENT_HISTORY


class FixedFilter:
    enabled = True

    def __init__(self, name: str, allowed: bool) -> None:
        self.name = name
        self.allowed = allowed
        self.calls = 0

    def evaluate(self, market, index):
        self.calls += 1
        return EntryFilterDecision(
            self.name,
            self.allowed,
            (
                EntryFilterReason.ALLOWED
                if self.allowed
                else EntryFilterReason.BLOCKED_BY_ATR
            ),
        )


def test_combination_evaluates_all_filters_with_and_logic() -> None:
    first = FixedFilter("first", False)
    second = FixedFilter("second", True)

    result = AllEntryFilters((first, second)).evaluate(candles(1), 0)

    assert result.allowed is False
    assert first.calls == 1
    assert second.calls == 1


class ExitStrategy:
    def generate_signal(self, market, index):
        return TradeAction.CLOSE_LONG


def test_filters_never_block_exits() -> None:
    blocker = FixedFilter("blocker", False)
    strategy = ResearchEntryFilteredStrategy(
        ExitStrategy(), AllEntryFilters((blocker,))
    )

    assert (
        strategy.generate_signal(candles(1), 0)
        is TradeAction.CLOSE_LONG
    )
    assert blocker.calls == 0


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ATRVolatilityFilter(
            ATRFilterConfig(enabled=True, period=3)
        ),
        lambda: ADXStrengthFilter(
            ADXFilterConfig(enabled=True, period=3)
        ),
    ],
)
def test_filter_has_no_look_ahead(factory) -> None:
    prefix = candles(20)
    first = prefix + [
        replace(prefix[-1], timestamp=20 * 3600, close=10_000)
    ]
    second = prefix + [
        replace(prefix[-1], timestamp=20 * 3600, close=1)
    ]

    one = factory().evaluate(first, len(prefix) - 1)
    two = factory().evaluate(second, len(prefix) - 1)

    assert one == two


def test_atr_and_adx_fixed_reference_values() -> None:
    from app.indicators import adx, atr

    close = [
        100, 102, 101, 104, 103, 106, 108, 107, 109, 111,
        110, 113, 112, 115, 117, 116, 119, 121, 120, 123,
        122, 125, 127, 126, 129, 131, 130, 133, 132, 135,
        137, 136, 139, 141, 140, 143, 142, 145, 147, 146,
    ]
    frame = pd.DataFrame(
        {
            "high": [
                value + (1.0 if index % 3 else 1.8)
                for index, value in enumerate(close)
            ],
            "low": [
                value - (1.2 if index % 4 else 2.0)
                for index, value in enumerate(close)
            ],
            "close": close,
        }
    )

    assert atr(frame, 14).iloc[-1] == pytest.approx(
        3.432573297014559
    )
    assert adx(frame, 14).iloc[-1] == pytest.approx(
        53.80058456426732
    )
    # Classic Wilder SMA seeding gives 3.4091388272580097 and
    # 53.9387137749703 on this fixture. The small, explicit difference
    # comes from the project's adjust=False EWM seed and is preserved.

