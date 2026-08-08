from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.telegram_bot import parser as bot_parser
from scripts.telegram_health import parser as health_parser


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"


def test_bot_and_health_use_isolated_state_directories() -> None:
    bot = (SYSTEMD / "crypto-telegram-bot.service").read_text(
        encoding="utf-8"
    )
    health = (SYSTEMD / "crypto-telegram-health.service").read_text(
        encoding="utf-8"
    )

    assert "StateDirectory=crypto-bot-telegram-bot\n" in bot
    assert "StateDirectory=crypto-bot-telegram-health\n" in health
    assert "StateDirectoryMode=0700\n" in bot
    assert "StateDirectoryMode=0700\n" in health
    assert "/var/lib/crypto-bot-telegram-bot/telegram_bot_state.json" in bot
    assert (
        "/var/lib/crypto-bot-telegram-health/telegram_notifications.json"
        in health
    )
    assert "StateDirectory=crypto-bot-telegram\n" not in bot
    assert "StateDirectory=crypto-bot-telegram\n" not in health


def test_script_defaults_match_isolated_state_directories() -> None:
    bot = bot_parser().parse_args([])
    health = health_parser().parse_args([])

    assert bot.bot_state_path == Path(
        "/var/lib/crypto-bot-telegram-bot/telegram_bot_state.json"
    )
    assert health.notification_state_path == Path(
        "/var/lib/crypto-bot-telegram-health/"
        "telegram_notifications.json"
    )


def test_report_services_do_not_allocate_state_directories() -> None:
    for name in (
        "crypto-telegram-morning.service",
        "crypto-telegram-evening.service",
    ):
        unit = (SYSTEMD / name).read_text(encoding="utf-8")
        assert "StateDirectory=" not in unit


def test_report_timers_use_yakutsk_local_schedule() -> None:
    morning = (SYSTEMD / "crypto-telegram-morning.timer").read_text(
        encoding="utf-8"
    )
    evening = (SYSTEMD / "crypto-telegram-evening.timer").read_text(
        encoding="utf-8"
    )

    assert "OnCalendar=*-*-* 09:00:00 Asia/Yakutsk\n" in morning
    assert "OnCalendar=*-*-* 21:00:00 Asia/Yakutsk\n" in evening


def test_yakutsk_schedule_uses_iana_timezone_without_manual_dst() -> None:
    yakutsk = ZoneInfo("Asia/Yakutsk")
    for month in (1, 7):
        morning = datetime(2026, month, 1, 9, tzinfo=yakutsk)
        evening = datetime(2026, month, 1, 21, tzinfo=yakutsk)

        assert morning.astimezone(timezone.utc).hour == 0
        assert evening.astimezone(timezone.utc).hour == 12
