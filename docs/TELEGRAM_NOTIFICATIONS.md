# Crypto-bot Telegram notifications

The Telegram integration is a separate, read-only operational contour. It
does not run inside the paper controller, cannot submit orders, and writes
only its own notification and polling-offset state under
`/var/lib/crypto-bot-telegram/`.

Use a dedicated Telegram bot token. Do not reuse a token belonging to the VPN
bot or any other long-polling process: Telegram permits only one reliable
`getUpdates` consumer per bot token.

## Configuration

Copy `deploy/crypto-telegram.env.example` to
`/etc/crypto-bot/telegram.env`, keep ownership with root and set mode `0600`.
The committed example contains no token or chat ID.

Required variables:

- `CRYPTO_TELEGRAM_ENABLED=false` keeps all sending disabled by default.
- `CRYPTO_TELEGRAM_BOT_TOKEN` is the dedicated crypto-bot token.
- `CRYPTO_TELEGRAM_CHAT_ID` is the only owner allowed to use commands.
- `CRYPTO_TELEGRAM_TIMEZONE=Asia/Yekaterinburg`.
- `CRYPTO_TELEGRAM_MORNING_TIME=09:00`.
- `CRYPTO_TELEGRAM_EVENING_TIME=21:00`.

The safe runtime values and artifact paths in the example are a non-secret
read-only mirror of the paper deployment. They must stay aligned with
`paper-shadow.env`; exchange credentials must never be copied into
`telegram.env`.

## Components

- `telegram_bot.py` long-polls commands `/start`, `/status`, `/trades`,
  `/decision`, `/mode`, and `/help`.
- `telegram_report.py morning|evening` builds a report first and sends it
  afterwards.
- `telegram_health.py` checks health every five minutes and sends only state
  transitions. Repeated failures are deduplicated and cooldown-protected.
- `telegram_notifications.json` contains alert transition state only.
- `telegram_bot_state.json` contains the independent `getUpdates` offset.

Unauthorized chat IDs are ignored. The log records only the numeric chat ID,
never the received message text. Messages are plain text; Telegram
Markdown/HTML parsing is not enabled.

## systemd installation

The committed units are deployment templates and are not installed or enabled
automatically. They use `DynamicUser=yes`, a private state directory, and a
read-only system view.

After adding a dedicated token and owner chat ID, validate before activation:

```bash
chmod 600 /etc/crypto-bot/telegram.env
systemd-analyze verify deploy/systemd/crypto-telegram-*.service \
  deploy/systemd/crypto-telegram-*.timer
```

Only after an explicit deployment approval, copy the units, reload systemd,
start the command bot, and enable the three timers. Do not change
`crypto-paper.timer`, `REGIME_FILTER_MODE=shadow`, or
`LIVE_TRADING_ENABLED=false`.

## Failure isolation

Telegram requests have bounded timeouts and retries. A Telegram failure makes
only the relevant Telegram unit fail; it does not call or mutate the trading
controller. Production controller state, trade journal, decision journal, and
last-candle marker are opened read-only. Notification state uses atomic file
replacement and is kept outside trading state.
