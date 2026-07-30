# Диагностика EMA-стратегии

Диагностика предназначена для сбора причин редких сделок. Она выключена
по умолчанию и не меняет контрольную paper-стратегию: EMA 20/50,
stop loss 2%, комиссия 0.1%. Сигналы, как и раньше, исполняются на открытии
следующей свечи.

## Включение в paper trading

Перед запуском `scripts/run_bybit_paper.py` задайте переменные окружения:

```bash
export PAPER_DIAGNOSTICS_ENABLED=true
export PAPER_DIAGNOSTICS_PATH=state/strategy_diagnostics.jsonl
export PAPER_DIAGNOSTICS_SAVE_ALL_CANDLES=true
export PAPER_DIAGNOSTICS_RETENTION_DAYS=30
export PAPER_DIAGNOSTICS_SESSION_ID=paper-2026-07
```

Дополнительно доступны `PAPER_DIAGNOSTICS_SYMBOL` (по умолчанию
`ETHUSDT`) и `PAPER_DIAGNOSTICS_TIMEFRAME` (по умолчанию `60`).
При `PAPER_DIAGNOSTICS_SAVE_ALL_CANDLES=false` сохраняются только решения
`hold`, то есть свечи без сделки. Значение retention `0` отключает очистку.
Повторная обработка сочетания session/symbol/timeframe/strategy/timestamp
не создаёт вторую запись.

JSONL хранит timestamp и close, позицию, решение, параметры стратегии,
индикаторы, выполненные и невыполненные условия, основную причину и
идентификатор запуска. Файл создаётся с правами `0640`.

## Коды причин

Коды являются значениями `ReasonCode` и стабильны для машинной обработки:

- `insufficient_history` — EMA ещё не прогреты;
- `fast_ema_not_above_slow`, `fast_ema_not_below_slow` — направление EMA
  не соответствует входу/выходу;
- `no_bullish_ema_cross`, `no_bearish_ema_cross` — нового пересечения нет;
- `price_trend_not_confirmed` — цена не прошла порог подтверждения;
- `trend_strength_too_low` — разница EMA меньше заданного порога;
- `position_already_open`, `position_absent` — сигнал несовместим с позицией;
- `risk_filter_blocked`, `signal_already_processed` — стабильные коды для
  runtime/risk-интеграций;
- `stop_loss_not_reached`, `no_entry_signal`, `no_exit_signal` — причина
  удержания;
- `buy_signal`, `sell_signal` — торговое условие выполнено.

`primary_reason` — главная причина решения. `reason_codes` содержит все
невыполненные условия, поэтому сумма процентов причин может быть больше
100%: одна свеча может быть заблокирована несколькими условиями.

## Отчёт по paper-журналу

```bash
PYTHONPATH=. venv/bin/python scripts/run_strategy_diagnostics.py \
  --journal state/strategy_diagnostics.jsonl \
  --output reports/paper_diagnostic_summary.json
```

Сокращённый пример:

```text
Strategy diagnostic summary
Processed candles: 720
Decisions: buy=2, sell=2, hold=716
Position events: open=2, close=2
Maximum period without signal: 311 candles (1119600 seconds)
Blocking reasons:
  no_bullish_ema_cross: 402 (55.83%)
  fast_ema_not_above_slow: 284 (39.44%)
```

## Сравнение параметров

```bash
PYTHONPATH=. venv/bin/python scripts/run_strategy_diagnostics.py \
  --data data/eth_usdt_1h_full.csv \
  --output reports/strategy_diagnostics.json
```

Запускаются пять заранее заданных вариантов: контрольный EMA 20/50,
быстрый 10/30, медленный 40/100, ослабленный 15/40 без дополнительных
порогов и усиленный 20/50 с подтверждением цены 0.25% и минимальной
разницей EMA 0.10%. Все варианты используют один набор свечей, баланс
1000 USDT и комиссию 0.1%.

Отчёт содержит доходность, просадку, закрытые сделки, win rate, profit
factor, комиссии, среднее время позиции, средний интервал между входами,
месяцы без сделок, причины блокировки и помесячную доходность. Данные
делятся хронологически 70/30 на train/test. Маркер `TRAIN+/TEST-` прямо
показывает положительный train и отрицательный test.

Не следует выбирать вариант только по `full %`. Сравнивайте test-результат,
просадку, число сделок и долю стабильных месяцев. Один период не
доказывает будущую прибыльность; следующий шаг для кандидата — существующий
walk-forward анализ проекта.
