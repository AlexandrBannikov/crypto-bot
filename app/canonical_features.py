"""Persistent, exact-timestamp feature and score snapshots for each candle."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence

from app.candle import Candle
from app.market_continuity import MarketContinuityError, validate_candle_continuity
from app.runtime_versions import FEATURE_VERSION, STRATEGY_LOGIC_VERSION
from app.signal_scoring import SignalScoreConfig, evaluate_signal


@dataclass(frozen=True, slots=True)
class CanonicalFeatureSnapshot:
    candle_timestamp: int
    candle_close_timestamp: int
    symbol: str
    timeframe_seconds: int
    market_checksum: str
    score_total: float
    components: dict[str, float]
    indicators: dict[str, float | None]
    hard_blocks: tuple[str, ...]
    entry_eligible: bool
    bearish_ema_cross: bool
    feature_version: str = FEATURE_VERSION
    strategy_logic_version: str = STRATEGY_LOGIC_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["hard_blocks"] = list(self.hard_blocks)
        return payload

    def as_score_row(self) -> dict[str, Any]:
        if self.entry_eligible:
            decision = "ENTER_LONG"
        elif self.bearish_ema_cross:
            decision = "EXIT_LONG"
        else:
            decision = "HOLD"
        return {
            **self.to_dict(),
            "decision": decision,
            "action": decision,
            "signal_score": self.score_total,
            "score": self.score_total,
            "score_components": self.components,
            "score_version": self.feature_version,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "CanonicalFeatureSnapshot":
        if not isinstance(payload, dict):
            raise ValueError("canonical feature snapshot must be an object")
        values = dict(payload)
        values["hard_blocks"] = tuple(values.get("hard_blocks", ()))
        try:
            snapshot = cls(**values)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid canonical feature snapshot: {exc}") from exc
        if snapshot.feature_version != FEATURE_VERSION:
            raise ValueError("canonical feature version mismatch")
        return snapshot


def market_checksum(candle: Candle) -> str:
    raw = "|".join(
        str(value)
        for value in (
            candle.timestamp, candle.open, candle.high,
            candle.low, candle.close, candle.volume,
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_feature_snapshot(
    causal_candles: Sequence[Candle],
    *,
    symbol: str,
    timeframe_seconds: int,
    score_config: SignalScoreConfig = SignalScoreConfig(),
    entry_threshold: float = 65.0,
) -> CanonicalFeatureSnapshot:
    continuity = validate_candle_continuity(
        causal_candles, timeframe_seconds=timeframe_seconds,
    )
    if not continuity.candles:
        raise ValueError("at least one candle is required")
    score = evaluate_signal(continuity.candles, score_config)
    candle = continuity.candles[-1]
    indicators = dict(score.indicators)
    previous_fast = indicators.get("previous_ema_fast")
    previous_slow = indicators.get("previous_ema_slow")
    current_fast = indicators.get("ema_fast")
    current_slow = indicators.get("ema_slow")
    bearish_cross = all(
        value is not None
        for value in (previous_fast, previous_slow, current_fast, current_slow)
    ) and bool(previous_fast >= previous_slow and current_fast < current_slow)
    components = {
        name: float(getattr(score, f"{name}_score"))
        for name in (
            "trend", "ema_alignment", "adx", "pullback",
            "momentum", "volatility", "cost",
        )
    }
    return CanonicalFeatureSnapshot(
        candle_timestamp=candle.timestamp,
        candle_close_timestamp=candle.timestamp + timeframe_seconds,
        symbol=symbol.strip().upper(),
        timeframe_seconds=timeframe_seconds,
        market_checksum=market_checksum(candle),
        score_total=float(score.total_score),
        components=components,
        indicators=indicators,
        hard_blocks=tuple(score.hard_blocks),
        entry_eligible=(
            score.total_score >= entry_threshold and not score.hard_blocks
        ),
        bearish_ema_cross=bearish_cross,
    )


class CanonicalFeatureStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read_all(self) -> tuple[CanonicalFeatureSnapshot, ...]:
        if not self.path.exists():
            return ()
        snapshots: list[CanonicalFeatureSnapshot] = []
        previous: int | None = None
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1,
        ):
            if not line.strip():
                continue
            try:
                snapshot = CanonicalFeatureSnapshot.from_dict(json.loads(line))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(
                    f"corrupt canonical feature line {line_number}: {exc}"
                ) from exc
            if previous is not None:
                if snapshot.candle_timestamp == previous:
                    raise MarketContinuityError("duplicate canonical feature snapshot")
                if snapshot.candle_timestamp < previous:
                    raise MarketContinuityError("out-of-order canonical feature snapshot")
                if snapshot.candle_timestamp - previous != snapshot.timeframe_seconds:
                    raise MarketContinuityError("canonical feature snapshot gap")
            snapshots.append(snapshot)
            previous = snapshot.candle_timestamp
        return tuple(snapshots)

    def exact(self, candle_timestamp: int) -> CanonicalFeatureSnapshot | None:
        matches = [
            item for item in self.read_all()
            if item.candle_timestamp == candle_timestamp
        ]
        return matches[0] if matches else None

    def append(self, snapshot: CanonicalFeatureSnapshot) -> bool:
        existing = self.read_all()
        if existing:
            last = existing[-1]
            if snapshot.candle_timestamp == last.candle_timestamp:
                if snapshot != last:
                    raise ValueError("conflicting canonical feature snapshot")
                return False
            expected = last.candle_timestamp + last.timeframe_seconds
            if snapshot.candle_timestamp != expected:
                raise MarketContinuityError(
                    f"canonical feature snapshot gap: {last.candle_timestamp} "
                    f"-> {snapshot.candle_timestamp}"
                )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(snapshot.to_dict(), handle, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True


def materialize_feature_snapshots(
    candles: Sequence[Candle],
    *,
    store: CanonicalFeatureStore,
    symbol: str,
    timeframe_seconds: int,
    score_config: SignalScoreConfig = SignalScoreConfig(),
    entry_threshold: float = 65.0,
) -> tuple[CanonicalFeatureSnapshot, ...]:
    ordered = validate_candle_continuity(
        candles, timeframe_seconds=timeframe_seconds,
    ).candles
    existing = store.read_all()
    last_timestamp = existing[-1].candle_timestamp if existing else None
    if last_timestamp is not None:
        future = [item for item in ordered if item.timestamp > last_timestamp]
        if future and future[0].timestamp != last_timestamp + timeframe_seconds:
            raise MarketContinuityError("market history cannot resolve feature gap")

    produced: list[CanonicalFeatureSnapshot] = []
    for index, candle in enumerate(ordered):
        if last_timestamp is not None and candle.timestamp <= last_timestamp:
            continue
        snapshot = build_feature_snapshot(
            ordered[: index + 1], symbol=symbol,
            timeframe_seconds=timeframe_seconds, score_config=score_config,
            entry_threshold=entry_threshold,
        )
        store.append(snapshot)
        produced.append(snapshot)
    return tuple(produced)
