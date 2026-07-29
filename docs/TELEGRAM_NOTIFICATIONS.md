# Crypto-bot Telegram notifications

The Telegram integration is a separate, read-only operational contour. It
does not run inside the paper controller, cannot submit orders, and writes
only its own state. The command bot keeps its polling offset under
`/var/lib/crypto-bot-telegram-bot/`; the health service keeps transition and
cooldown state under `/var/lib/crypto-bot-telegram-health/`. The two
`DynamicUser` services never share a writable state directory.

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

Production runtime access is limited through the
`crypto-bot-runtime` supplementary group. The `state` directory is owned by
`root:crypto-bot-runtime` with mode `2750`; only the operational runtime state
and shadow decision journal are group-readable (`0640`). The controller lock
stays private (`0600`) and is neither configured nor inspected by Telegram.

## Components

- `telegram_bot.py` long-polls commands `/start`, `/status`, `/trades`,
  `/decision`, `/mode`, `/candidate`, `/comparison`, and `/help`.
- `telegram_report.py morning|evening` builds a report first and sends it
  afterwards.
- `telegram_health.py` checks health every five minutes and sends only state
  transitions. Repeated failures are deduplicated and cooldown-protected.
- `telegram_notifications.json` contains alert transition state only.
- `telegram_bot_state.json` contains the independent `getUpdates` offset.

The bot and health units use separate `StateDirectory=` values with mode
`0700`. Morning and evening report services are stateless and do not declare a
state directory. This prevents one dynamic user from changing ownership of
another service's files.

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
`/comparison` формирует компактное read-only сравнение production и candidate
с момента запуска candidate. Оно показывает метрики обоих контуров, deltas,
agreement rate и до трёх последних расхождений. Длинный ответ разбивается не
более чем на четыре Telegram-сообщения. Команда использует тот же allowlisted
chat id и ничего не записывает в trading state или журналы.

## Cash balance, equity и открытая позиция

Вечерний отчёт разделяет денежные средства и результат стратегии:

- `cash balance` — свободные USDT после покупки;
- `position market value` — количество ETH, умноженное на последнюю уже
  полученную runtime-цену;
- `equity` — `cash balance + position market value`;
- `realized PnL` — результат только закрытых сделок;
- `unrealized PnL` — результат текущей открытой позиции;
- `total PnL` — `realized PnL + unrealized PnL`;
- `total return` — `total PnL / initial balance * 100`.

Cash balance падает при покупке ETH, потому что часть USDT превращается в ETH.
Само это снижение не является убытком. Результат открытой позиции показывает
unrealized PnL, а общий текущий результат — equity и total PnL.

Для LONG используются формулы:

```text
position market value = quantity * current price
unrealized PnL = quantity * (current price - entry price)
unrealized return = (current price - entry price) / entry price * 100
distance to stop = current price - stop price
distance to stop % = distance to stop / current price * 100
```

Controller является LONG spot-моделью. Чистый snapshot-калькулятор умеет
показывать SHORT из исследовательских абстракций: unrealized PnL равен
`quantity * (entry price - current price)`, а equity равна initial balance плюс
realized и unrealized PnL. LONG spot-формула к SHORT collateral не применяется.

Пример при открытой позиции:

```text
Production account:
cash balance 980.74 USDT
position market value 19.12 USDT
equity 999.86 USDT
realized PnL 0.00 USDT
unrealized PnL -0.38 USDT
total return -0.038%

Production open position:
side LONG
quantity 0.01 ETH
entry price 1950.00 USDT
current price 1912.45 USDT
position age 9h 0m
stop-loss 1885.00 USDT
distance to stop 27.45 USDT / 1.435%
```

Пример при FLAT:

```text
Production account:
cash balance 1000.00 USDT
position market value 0.00 USDT
equity 1000.00 USDT
Production open position: FLAT
```

Цена берётся из последней уже записанной runtime/decision-свечи. Генерация
отчёта не делает отдельный запрос к Bybit; при отсутствии цены выводится `N/A`.
JSON comparison report содержит `generated_at`, `period`, `market`,
`production`, `candidate`, `comparison`, `health` и `decision_agreement`.
