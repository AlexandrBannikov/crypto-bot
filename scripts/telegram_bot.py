from __future__ import annotations

import argparse
import logging
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
    command_response,
    process_update,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Read-only Telegram command bot for crypto paper runtime"
    )
    result.add_argument(
        "--bot-state-path",
        type=Path,
        default=Path(
            "/var/lib/crypto-bot-telegram-bot/telegram_bot_state.json"
        ),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parser().parse_args(argv)
    try:
        config = TelegramConfig.from_env()
        if not config.enabled:
            print("Telegram command bot is disabled")
            return 0
        paths = TelegramPaths.from_env(
            notification_state=args.bot_state_path
        )
        store = NotificationStateStore(paths.notification_state)
        client = TelegramClient(config.token or "", timeout=35, retries=1)
        while True:
            state = store.load()
            updates = client.call(
                "getUpdates",
                {
                    "offset": state.update_offset,
                    "timeout": 25,
                    "allowed_updates": '["message"]',
                },
            )
            for update in updates or []:
                update_id = int(update.get("update_id", 0))

                def responder(command: str) -> str:
                    snapshot, _ = collect_snapshot(paths)
                    return command_response(command, snapshot, paths)

                process_update(
                    update,
                    allowed_chat_id=config.chat_id or "",
                    responder=responder,
                    sender=client.send_message,
                )
                state.update_offset = max(
                    state.update_offset, update_id + 1
                )
                store.save(state)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        logging.error(
            "Telegram command bot failed: %s", type(exc).__name__
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
