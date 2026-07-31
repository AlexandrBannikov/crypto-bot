from __future__ import annotations

import argparse
from pathlib import Path
import sys
import traceback

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.telegram_config import TelegramConfig
from app.telegram_notifications import (
    TelegramClient,
    TelegramPaths,
    collect_snapshot,
    format_evening_report,
    format_morning_report,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Send a read-only crypto paper Telegram report"
    )
    result.add_argument("period", choices=("morning", "evening"))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = TelegramConfig.from_env()
        if not config.enabled:
            print("Telegram notifications are disabled")
            return 0
        paths = TelegramPaths.from_env()
        snapshot, _ = collect_snapshot(paths)
        formatter = (
            format_morning_report
            if args.period == "morning"
            else format_evening_report
        )
        message = formatter(
            snapshot, paths, timezone_name=config.timezone
        )
        TelegramClient(config.token or "").send_message(
            config.chat_id or "", message
        )
        print(f"{args.period} Telegram report sent")
        return 0
    except Exception as exc:
        print(
            f"Telegram report failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
