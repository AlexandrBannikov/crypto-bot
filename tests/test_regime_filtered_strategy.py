from dataclasses import dataclass

import pytest

from app.candle import Candle
from app.market_regime import (
    MarketRegime,
    MarketTrend,
    MarketVolatility,
)
from app.regime_filtered_strategy import RegimeFilteredStrategy
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_filter import TradingFilter
from app.trading_types import TradeAction


def make_candles(count: int = 3) -> list[Candle]:
    return [
        Candle(
            timestamp=index,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )
        for index in range(count)
    ]


def regime(
    trend: MarketTrend,
    volatility: MarketVolatility = MarketVolatility.NORMAL,
    confidence: float = 1.0,
) -> MarketRegime:
    return MarketRegime(trend, volatility, confidence)


class SequenceStrategy:
    def __init__(self, *signals) -> None:
        self.signals = signals

    def generate_signal(self, candles, index):
        return self.signals[index]


class SequenceDetector:
    def __init__(self, *regimes: MarketRegime) -> None:
        self.regimes = iter(regimes)
        self.seen_candles = []

    def detect(self, candles):
        self.seen_candles.append(tuple(candles))
        return next(self.regimes)


def wrap(signal, detected_regime, *, confidence=0.0):
    return RegimeFilteredStrategy(
        SequenceStrategy(signal),
        SequenceDetector(detected_regime),
        TradingFilter(minimum_confidence=confidence),
    )


@pytest.mark.parametrize(
    "volatility",
    [MarketVolatility.LOW, MarketVolatility.NORMAL],
)
def test_allows_entry_in_uptrend(volatility) -> None:
    strategy = wrap(
        Signal.BUY,
        regime(MarketTrend.TREND_UP, volatility),
    )

    assert strategy.generate_signal(make_candles(1), 0) is Signal.BUY
    assert strategy.statistics.allowed_entries == 1


@pytest.mark.parametrize(
    ("detected_regime", "reason"),
    [
        (regime(MarketTrend.RANGE), "range"),
        (regime(MarketTrend.TREND_DOWN), "downtrend"),
        (
            regime(
                MarketTrend.TREND_UP,
                MarketVolatility.HIGH,
            ),
            "high_volatility",
        ),
        (regime(MarketTrend.UNKNOWN), "unknown_regime"),
        (
            regime(
                MarketTrend.TREND_UP,
                confidence=0.4,
            ),
            "low_confidence",
        ),
    ],
)
def test_blocks_entry_and_counts_reason(
    detected_regime,
    reason,
) -> None:
    strategy = wrap(
        Signal.BUY,
        detected_regime,
        confidence=0.5,
    )

    assert (
        strategy.generate_signal(make_candles(1), 0)
        is TradeAction.HOLD
    )
    statistics = strategy.statistics
    assert statistics.blocked_entries == 1
    assert statistics.blocked_by_reason[reason] == 1
    assert sum(statistics.blocked_by_reason.values()) == 1


def test_exit_is_never_blocked_and_preserves_parameters() -> None:
    exit_signal = TradeSignal(
        action=TradeAction.CLOSE_LONG,
        stop_loss=95.0,
        trailing_stop_percent=0.1,
        break_even_r_multiple=1.5,
    )
    detector = SequenceDetector(
        regime(MarketTrend.TREND_UP),
    )
    strategy = RegimeFilteredStrategy(
        SequenceStrategy(Signal.BUY, exit_signal),
        detector,
        TradingFilter(),
    )
    candles = make_candles(2)

    strategy.generate_signal(candles, 0)
    returned = strategy.generate_signal(candles, 1)

    assert returned is exit_signal
    assert returned.stop_loss == 95.0
    assert returned.trailing_stop_percent == 0.1
    assert returned.break_even_r_multiple == 1.5
    assert len(detector.seen_candles) == 1


def test_hold_remains_hold_without_regime_detection() -> None:
    detector = SequenceDetector()
    strategy = RegimeFilteredStrategy(
        SequenceStrategy(Signal.HOLD),
        detector,
        TradingFilter(),
    )

    assert strategy.generate_signal(make_candles(1), 0) is Signal.HOLD
    assert detector.seen_candles == []


def test_allowed_entry_preserves_stop_loss() -> None:
    entry = TradeSignal(
        action=TradeAction.OPEN_LONG,
        stop_loss=95.0,
    )
    strategy = wrap(
        entry,
        regime(MarketTrend.TREND_UP),
    )

    returned = strategy.generate_signal(make_candles(1), 0)

    assert returned is entry
    assert returned.stop_loss == 95.0


def test_detector_never_receives_future_candles() -> None:
    detector = SequenceDetector(regime(MarketTrend.TREND_UP))
    strategy = RegimeFilteredStrategy(
        SequenceStrategy(Signal.HOLD, Signal.BUY, Signal.HOLD),
        detector,
        TradingFilter(),
    )
    candles = make_candles(3)

    strategy.generate_signal(candles, 0)
    strategy.generate_signal(candles, 1)

    assert detector.seen_candles == [tuple(candles[:2])]
    assert candles[2] not in detector.seen_candles[0]


@dataclass(frozen=True)
class ImmutableStrategy:
    signal: Signal

    def generate_signal(self, candles, index):
        return self.signal


def test_base_strategy_is_not_reconfigured_or_replaced() -> None:
    base = ImmutableStrategy(Signal.BUY)
    strategy = RegimeFilteredStrategy(
        base,
        SequenceDetector(regime(MarketTrend.TREND_UP)),
        TradingFilter(),
    )

    strategy.generate_signal(make_candles(1), 0)

    assert strategy.base_strategy is base
    assert base == ImmutableStrategy(Signal.BUY)


def test_allowed_and_blocked_counters_accumulate() -> None:
    detector = SequenceDetector(
        regime(MarketTrend.RANGE),
        regime(MarketTrend.TREND_UP),
    )
    strategy = RegimeFilteredStrategy(
        SequenceStrategy(
            Signal.BUY,
            Signal.BUY,
            Signal.SELL,
        ),
        detector,
        TradingFilter(),
    )
    candles = make_candles(3)

    for index in range(3):
        strategy.generate_signal(candles, index)

    statistics = strategy.statistics
    assert statistics.allowed_entries == 1
    assert statistics.blocked_entries == 1
    assert statistics.blocked_by_reason["range"] == 1
