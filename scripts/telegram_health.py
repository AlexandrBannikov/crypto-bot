from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.telegram_config import TelegramConfig
from app.telegram_notifications import (
    NotificationStateStore,
    TelegramClient,
    TelegramPaths,
    collect_snapshot,
    send_transition_alerts,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Send transition-only crypto runtime alerts"
    )
    result.add_argument(
        "--notification-state-path",
        type=Path,
        default=Path(
            "/var/lib/crypto-bot-telegram-health/"
            "telegram_notifications.json"
        ),
    )
    result.add_argument("--no-network", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = TelegramConfig.from_env()
        if not config.enabled:
            print("Telegram notifications are disabled")
            return 0
        paths = TelegramPaths.from_env(
            notification_state=args.notification_state_path
        )
        snapshot, checks = collect_snapshot(
            paths, no_network=args.no_network
        )
        client = TelegramClient(config.token or "")
        sent = send_transition_alerts(
            NotificationStateStore(paths.notification_state),
            snapshot,
            checks,
            lambda text: client.send_message(config.chat_id or "", text),
        )
        print(f"Telegram health transitions sent: {sent}")
        return 0
    except Exception as exc:
        print(
            f"Telegram health check failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
