from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.candle import Candle
from app.config import PaperStrategyConfig, PaperStrategyMode
from app.market_regime import MarketRegime, MarketRegimeDetector
from app.regime_filtered_strategy import classify_entry_block_reason
from app.signal_normalizer import normalize_signal
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_filter import TradingFilter
from app.trading_types import TradeAction


class RegimeDetector(Protocol):
    def detect(self, candles: Sequence[Candle]) -> MarketRegime:
        ...


@dataclass(frozen=True, slots=True)
class DetectorDiagnostics:
    parameters_fingerprint: str
    parameters: dict[str, float | int]
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class PaperStrategyDecision:
    baseline_signal: TradeSignal
    filtered_signal: TradeSignal
    execution_signal: TradeSignal
    mode: PaperStrategyMode
    regime: str | None
    confidence: float | None
    entry_allowed: bool | None
    blocked: bool
    blocked_reason: str | None
    detector_diagnostics: DetectorDiagnostics


class PaperStrategyRouter:
    """Route one paper signal without owning trading state."""

    def __init__(
        self,
        config: PaperStrategyConfig,
        *,
        fast_ema_period: int = 20,
        slow_ema_period: int = 50,
        detector: RegimeDetector | None = None,
        trading_filter: TradingFilter | None = None,
    ) -> None:
        self.config = config
        self.detector_parameters = {
            "fast_ema_period": fast_ema_period,
            "slow_ema_period": slow_ema_period,
            "adx_period": config.adx_period,
            "adx_threshold": config.adx_threshold,
            "atr_period": config.atr_period,
            "low_volatility_threshold": (
                config.low_volatility_threshold
            ),
            "high_volatility_threshold": (
                config.high_volatility_threshold
            ),
            "minimum_confidence": config.minimum_confidence,
        }
        encoded = json.dumps(
            self.detector_parameters,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.parameters_fingerprint = hashlib.sha256(encoded).hexdigest()
        self.detector = detector or MarketRegimeDetector(
            fast_ema_period=fast_ema_period,
            slow_ema_period=slow_ema_period,
            adx_period=config.adx_period,
            adx_threshold=config.adx_threshold,
            atr_period=config.atr_period,
            low_volatility_threshold=(
                config.low_volatility_threshold
            ),
            high_volatility_threshold=(
                config.high_volatility_threshold
            ),
        )
        self.trading_filter = trading_filter or TradingFilter(
            minimum_confidence=config.minimum_confidence
        )

    def route(
        self,
        signal: Signal | TradeSignal | TradeAction,
        candles: Sequence[Candle],
    ) -> PaperStrategyDecision:
        if not candles:
            raise ValueError("candles must not be empty")
        baseline = normalize_signal(signal)
        diagnostics = DetectorDiagnostics(
            parameters_fingerprint=self.parameters_fingerprint,
            parameters=dict(self.detector_parameters),
        )
        if (
            baseline.action
            not in {TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT}
            or self.config.mode is PaperStrategyMode.BASELINE
        ):
            return PaperStrategyDecision(
                baseline_signal=baseline,
                filtered_signal=baseline,
                execution_signal=baseline,
                mode=self.config.mode,
                regime=None,
                confidence=None,
                entry_allowed=None,
                blocked=False,
                blocked_reason=None,
                detector_diagnostics=diagnostics,
            )

        try:
            regime = self.detector.detect(candles)
            allowed = self.trading_filter.allow_entry(regime)
            filtered = (
                baseline
                if allowed
                else TradeSignal(action=TradeAction.HOLD)
            )
            reason = (
                None
                if allowed
                else classify_entry_block_reason(regime).value
            )
            diagnostics = DetectorDiagnostics(
                parameters_fingerprint=self.parameters_fingerprint,
                parameters=dict(self.detector_parameters),
            )
            regime_name = (
                f"{regime.trend.value}/{regime.volatility.value}"
            )
            confidence = regime.confidence
        except Exception as exc:
            allowed = False
            filtered = TradeSignal(action=TradeAction.HOLD)
            reason = "detector_error"
            regime_name = None
            confidence = None
            diagnostics = DetectorDiagnostics(
                parameters_fingerprint=self.parameters_fingerprint,
                parameters=dict(self.detector_parameters),
                error_type=type(exc).__name__,
            )

        execution = (
            baseline
            if self.config.mode is PaperStrategyMode.SHADOW
            else filtered
        )
        return PaperStrategyDecision(
            baseline_signal=baseline,
            filtered_signal=filtered,
            execution_signal=execution,
            mode=self.config.mode,
            regime=regime_name,
            confidence=confidence,
            entry_allowed=allowed,
            blocked=not allowed,
            blocked_reason=reason,
            detector_diagnostics=diagnostics,
        )
