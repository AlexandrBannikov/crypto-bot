from app.candle import Candle
from app.scored_component_calibration import analyze, pullback_raw, replay
from app.signal_scoring import SignalScoreConfig


def candles(count: int = 100) -> tuple[Candle, ...]:
    return tuple(
        Candle(i * 3600, 100 + i * .1, 101 + i * .1, 99 + i * .1, 100.2 + i * .1, 10)
        for i in range(count)
    )


def test_replay_excludes_insufficient_data_from_component_statistics() -> None:
    market = candles()
    records = replay(market)
    report = analyze(records, market)
    assert report["excluded_insufficient_data"] == 65
    assert report["valid_setup_decisions"] == 35
    assert report["component_summary"]["cost"]["mean"] == 4.5


def test_pullback_raw_is_bounded_deterministic_and_classified() -> None:
    config = SignalScoreConfig()
    candle = Candle(0, 100, 101, 99.8, 100.1, 1)
    first = pullback_raw(candle, 100, config)
    second = pullback_raw(candle, 100, config)
    assert first == second
    assert 0 <= first["touch"] <= 1
    assert 0 <= first["near"] <= 1
    assert 0 <= first["retrace"] <= 1
    assert 0 <= first["composite"] <= 1
    assert first["zone"] == "normal_pullback"


def test_future_outcomes_are_censored_without_lookahead() -> None:
    market = candles()
    report = analyze(replay(market), market)
    correlation = report["correlations"]["pullback"]["return_24h"]
    assert correlation["sample_size"] == report["valid_setup_decisions"] - 24


def test_marginal_analysis_does_not_mutate_runtime_records() -> None:
    market = candles()
    records = replay(market)
    before = repr(records)
    report = analyze(records, market)
    assert repr(records) == before
    assert report["safety"]["runtime_decisions_changed"] is False
    assert report["safety"]["threshold_changed"] is False


def test_threshold_is_explicit_research_input() -> None:
    market = candles()
    report = analyze(replay(market), market, threshold=60)
    assert report["threshold"] == 60
