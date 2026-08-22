import json
from pathlib import Path

import pytest

from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.candle import Candle
from app.canonical_features import (
    CanonicalFeatureStore,
    build_feature_snapshot,
    materialize_feature_snapshots,
)
from app.market_continuity import MarketContinuityError, validate_candle_continuity
from app.runtime_versions import version_fields


HOUR = 3600


def candles(count: int = 70, *, start: int = 0) -> tuple[Candle, ...]:
    return tuple(
        Candle(start + index * HOUR, 100 + index, 101 + index,
               99 + index, 100.5 + index, 10)
        for index in range(count)
    )


def payload(*timestamps: int) -> dict:
    return {
        "retCode": 0,
        "result": {"list": [
            [str(ts * 1000), "100", "101", "99", "100", "1"]
            for ts in timestamps
        ]},
    }


def test_continuity_rejects_duplicate_gap_and_unaligned_candles() -> None:
    base = Candle(0, 100, 101, 99, 100, 1)
    with pytest.raises(MarketContinuityError, match="duplicate"):
        validate_candle_continuity((base, base), timeframe_seconds=HOUR)
    with pytest.raises(MarketContinuityError, match="gap"):
        validate_candle_continuity(
            (base, Candle(2 * HOUR, 100, 101, 99, 100, 1)),
            timeframe_seconds=HOUR,
        )
    with pytest.raises(MarketContinuityError, match="aligned"):
        validate_candle_continuity(
            (Candle(1, 100, 101, 99, 100, 1),), timeframe_seconds=HOUR,
        )
    with pytest.raises(MarketContinuityError, match="out-of-order"):
        validate_candle_continuity(
            (Candle(HOUR, 100, 101, 99, 100, 1), base),
            timeframe_seconds=HOUR,
        )


def test_continuity_reports_gap_from_persisted_cursor() -> None:
    result = validate_candle_continuity(
        candles(2, start=2 * HOUR), timeframe_seconds=HOUR,
        last_processed_timestamp=0,
    )
    assert result.unresolved_gap is True


def test_canonical_store_requires_exact_non_stale_snapshot(tmp_path: Path) -> None:
    store = CanonicalFeatureStore(tmp_path / "features.jsonl")
    history = candles()
    materialize_feature_snapshots(
        history, store=store, symbol="ETHUSDT", timeframe_seconds=HOUR,
    )
    latest = store.exact(history[-1].timestamp)
    assert latest is not None
    assert latest.feature_version == version_fields()["feature_version"]
    assert store.exact(history[-1].timestamp + HOUR) is None
    assert latest.as_score_row()["candle_timestamp"] == history[-1].timestamp


def test_canonical_store_is_idempotent_and_rejects_conflict(tmp_path: Path) -> None:
    store = CanonicalFeatureStore(tmp_path / "features.jsonl")
    snapshot = build_feature_snapshot(
        candles(), symbol="ETHUSDT", timeframe_seconds=HOUR,
    )
    assert store.append(snapshot) is True
    assert store.append(snapshot) is False
    raw = snapshot.to_dict()
    raw["market_checksum"] = "conflict"
    from app.canonical_features import CanonicalFeatureSnapshot
    with pytest.raises(ValueError, match="conflicting"):
        store.append(CanonicalFeatureSnapshot.from_dict(raw))


def test_feature_materialization_refuses_unresolved_history_gap(tmp_path: Path) -> None:
    store = CanonicalFeatureStore(tmp_path / "features.jsonl")
    first = build_feature_snapshot(
        candles(), symbol="ETHUSDT", timeframe_seconds=HOUR,
    )
    store.append(first)
    future = candles(2, start=first.candle_timestamp + 2 * HOUR)
    with pytest.raises(MarketContinuityError, match="resolve"):
        materialize_feature_snapshots(
            future, store=store, symbol="ETHUSDT", timeframe_seconds=HOUR,
        )


def test_market_feed_rejects_duplicate_gap_and_non_finite_rows() -> None:
    for response, message in (
        (payload(0, 0), "duplicate"),
        (payload(0, 2 * HOUR), "gap"),
        ({"retCode": 0, "result": {"list": [
            ["0", "nan", "101", "99", "100", "1"]
        ]}}, "finite"),
    ):
        feed = BybitMarketDataFeed(
            http_get_json=lambda *_, response=response: response,
            clock_ms=lambda: 4 * HOUR * 1000,
        )
        with pytest.raises(ValueError, match=message):
            feed.get_candles()


def test_readiness_polls_until_expected_closed_candle_arrives() -> None:
    responses = iter((payload(0), payload(HOUR, 0)))
    sleeps: list[float] = []
    feed = BybitMarketDataFeed(
        BybitMarketDataConfig(
            interval="60", readiness_timeout_seconds=10,
            readiness_poll_seconds=5,
        ),
        http_get_json=lambda *_: next(responses),
        clock_ms=lambda: 2 * HOUR * 1000 + 10_000,
        sleeper=sleeps.append,
    )
    result = feed.get_ready_candles()
    assert result[-1].timestamp == HOUR
    assert sleeps == [5]
