from dataclasses import dataclass
from enum import Enum
import math
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    symbol: str = "ETH/USDT"
    timeframe: str = "1h"
    start_balance: float = 1000.0
    fee_rate: float = 0.001

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("Торговая пара не может быть пустой")

        if not self.timeframe.strip():
            raise ValueError("Таймфрейм не может быть пустым")

        if self.start_balance <= 0:
            raise ValueError(
                "Стартовый баланс должен быть больше нуля"
            )

        if not 0 <= self.fee_rate < 1:
            raise ValueError("Некорректная комиссия")


DEFAULT_CONFIG = BacktestConfig()


class PaperStrategyMode(str, Enum):
    BASELINE = "baseline"
    FILTERED = "filtered"
    SHADOW = "shadow"


@dataclass(frozen=True, slots=True)
class PaperStrategyConfig:
    mode: PaperStrategyMode = PaperStrategyMode.BASELINE
    adx_period: int = 14
    adx_threshold: float = 20.0
    atr_period: int = 14
    low_volatility_threshold: float = 0.005
    high_volatility_threshold: float = 0.02
    minimum_confidence: float = 0.0
    shadow_diagnostics_path: Path = Path(
        "state/shadow_decisions.jsonl"
    )
    shadow_diagnostics_enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.mode, PaperStrategyMode):
            raise ValueError(
                "mode must be baseline, filtered, or shadow"
            )
        if self.adx_period <= 0:
            raise ValueError("REGIME_ADX_PERIOD must be positive")
        if self.atr_period <= 0:
            raise ValueError("REGIME_ATR_PERIOD must be positive")
        thresholds = (
            self.adx_threshold,
            self.low_volatility_threshold,
            self.high_volatility_threshold,
            self.minimum_confidence,
        )
        if not all(math.isfinite(value) for value in thresholds):
            raise ValueError("regime thresholds must be finite")
        if self.adx_threshold < 0:
            raise ValueError("REGIME_ADX_THRESHOLD must not be negative")
        if self.low_volatility_threshold < 0:
            raise ValueError(
                "REGIME_LOW_VOLATILITY_THRESHOLD must not be negative"
            )
        if self.high_volatility_threshold <= 0:
            raise ValueError(
                "REGIME_HIGH_VOLATILITY_THRESHOLD must be positive"
            )
        if (
            self.low_volatility_threshold
            >= self.high_volatility_threshold
        ):
            raise ValueError(
                "REGIME_LOW_VOLATILITY_THRESHOLD must be lower than "
                "REGIME_HIGH_VOLATILITY_THRESHOLD"
            )
        if not 0 <= self.minimum_confidence <= 1:
            raise ValueError(
                "REGIME_MINIMUM_CONFIDENCE must be between 0 and 1"
            )
        if (
            self.shadow_diagnostics_enabled
            and not str(self.shadow_diagnostics_path).strip()
        ):
            raise ValueError(
                "SHADOW_DIAGNOSTICS_PATH must not be empty when enabled"
            )

    @classmethod
    def from_env(
        cls,
        *,
        mode_override: str | None = None,
    ) -> "PaperStrategyConfig":
        mode_value = mode_override or os.environ.get(
            "PAPER_STRATEGY_MODE",
            PaperStrategyMode.BASELINE.value,
        )
        try:
            mode = PaperStrategyMode(mode_value.strip().lower())
        except (AttributeError, ValueError) as exc:
            allowed = ", ".join(item.value for item in PaperStrategyMode)
            raise ValueError(
                f"invalid PAPER_STRATEGY_MODE; expected one of: {allowed}"
            ) from exc

        return cls(
            mode=mode,
            adx_period=_env_int("REGIME_ADX_PERIOD", 14),
            adx_threshold=_env_float("REGIME_ADX_THRESHOLD", 20.0),
            atr_period=_env_int("REGIME_ATR_PERIOD", 14),
            low_volatility_threshold=_env_float(
                "REGIME_LOW_VOLATILITY_THRESHOLD", 0.005
            ),
            high_volatility_threshold=_env_float(
                "REGIME_HIGH_VOLATILITY_THRESHOLD", 0.02
            ),
            minimum_confidence=_env_float(
                "REGIME_MINIMUM_CONFIDENCE", 0.0
            ),
            shadow_diagnostics_path=Path(
                os.environ.get(
                    "SHADOW_DIAGNOSTICS_PATH",
                    "state/shadow_decisions.jsonl",
                )
            ),
            shadow_diagnostics_enabled=_env_bool(
                "SHADOW_DIAGNOSTICS_ENABLED", True
            ),
        )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
