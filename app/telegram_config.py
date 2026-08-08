from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import os
from zoneinfo import ZoneInfo


def _boolean(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _clock(name: str, default: str) -> time:
    raw = os.environ.get(name, default)
    try:
        return time.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must use HH:MM format") from exc


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    enabled: bool = False
    token: str | None = None
    chat_id: str | None = None
    timezone: str = "Asia/Yakutsk"
    morning_time: time = time(9, 0)
    evening_time: time = time(21, 0)

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise ValueError(
                "CRYPTO_TELEGRAM_TIMEZONE must be a valid timezone"
            ) from exc
        if self.enabled and not self.token:
            raise ValueError(
                "CRYPTO_TELEGRAM_BOT_TOKEN is required when Telegram is enabled"
            )
        if self.enabled and not self.chat_id:
            raise ValueError(
                "CRYPTO_TELEGRAM_CHAT_ID is required when Telegram is enabled"
            )

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        return cls(
            enabled=_boolean("CRYPTO_TELEGRAM_ENABLED", False),
            token=os.environ.get("CRYPTO_TELEGRAM_BOT_TOKEN") or None,
            chat_id=os.environ.get("CRYPTO_TELEGRAM_CHAT_ID") or None,
            timezone=os.environ.get(
                "CRYPTO_TELEGRAM_TIMEZONE", "Asia/Yakutsk"
            ),
            morning_time=_clock(
                "CRYPTO_TELEGRAM_MORNING_TIME", "09:00"
            ),
            evening_time=_clock(
                "CRYPTO_TELEGRAM_EVENING_TIME", "21:00"
            ),
        )
