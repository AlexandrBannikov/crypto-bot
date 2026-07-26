from __future__ import annotations

import os
from dataclasses import dataclass

from app.execution import ExecutionMode


@dataclass(frozen=True, slots=True)
class Settings:
    execution_mode: ExecutionMode
    bybit_api_key: str | None
    bybit_api_secret: str | None
    bybit_testnet: bool
    live_trading_confirmed: bool
    bybit_allow_mainnet: bool


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    return normalized


def load_settings() -> Settings:
    raw_mode = os.getenv(
        "EXECUTION_MODE",
        ExecutionMode.PAPER.value,
    ).strip().lower()

    return Settings(
        execution_mode=ExecutionMode(raw_mode),
        bybit_api_key=_optional_text(
            os.getenv("BYBIT_API_KEY")
        ),
        bybit_api_secret=_optional_text(
            os.getenv("BYBIT_API_SECRET")
        ),
        bybit_testnet=_parse_bool(
            os.getenv("BYBIT_TESTNET")
        ),
        live_trading_confirmed=_parse_bool(
            os.getenv("LIVE_TRADING_CONFIRMED")
        ),
        bybit_allow_mainnet=_parse_bool(
            os.getenv("BYBIT_ALLOW_MAINNET")
        ),
    )
