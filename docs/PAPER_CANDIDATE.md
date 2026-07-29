# Production paper и Strategy V2 candidate

Production paper — действующий EMA paper-controller в
`scripts/run_bybit_controller.py`. Его state, режим `REGIME_FILTER_MODE=shadow`,
таймер и журналы candidate не изменяет.

Candidate paper — второй, полностью независимый LONG-only контур:

- ETHUSDT, публичные Bybit spot 1h closed candles;
- EMA20/EMA50 cross, ADX(14) не ниже 20;
- HYBRID pullback: low touch **или** close near EMA20 с tolerance `0.005`
  **или** retrace от цены cross на `0.0075`;
- ожидание не более 8 новых свечей;
- выход по EMA cross down не фильтруется;
- комиссия `0.001`, quantity `0.01`, стартовый баланс `1000 USDT`;
- только causal-расчёты. Первый запуск прогревает индикаторы и сохраняет
  текущую закрытую свечу как baseline, не создавая сделок задним числом.

## Изоляция и безопасность

Candidate использует только публичный market endpoint Bybit и `PaperExecutor`.
Он аварийно завершится, если `LIVE_TRADING_ENABLED` не равно `false`.

| Данные | Путь |
|---|---|
| State и pending pullback | `state/bybit_candidate_controller.json` |
| Закрытые сделки | `state/bybit_candidate_trades.jsonl` |
| Решения каждой свечи | `state/bybit_candidate_decisions.jsonl` |
| Advisory lock | `state/bybit_candidate.lock` |
| Runtime summary | `state/bybit_candidate_runtime.json` |
| Daily comparison | `reports/runtime/comparison/YYYY-MM-DD.json` |

## Операции

```bash
systemctl status crypto-paper-candidate.timer --no-pager
journalctl -u crypto-paper-candidate.service -n 100 --no-pager
python scripts/report_paper_comparison.py
```

Остановить только candidate:

```bash
systemctl disable --now crypto-paper-candidate.timer
systemctl disable --now crypto-paper-candidate-health.timer
systemctl disable --now crypto-paper-comparison.timer
```

Для полного удаления сначала остановите только эти три таймера, затем удалите
их candidate/comparison unit-файлы из `/etc/systemd/system`, env
`/etc/crypto-bot/paper-candidate.env` и перечисленные candidate state/report
файлы. Не удаляйте и не перезапускайте `crypto-paper.timer`, production state
или `/etc/crypto-bot/paper-shadow.env`.

Telegram-команды `/candidate` и `/comparison` только читают state. Утренний и
вечерний отчёты содержат отдельный candidate-блок; сделки контуров не
объединяются.

## Период наблюдения

Наблюдать минимум 2–4 недели: freshness/API/halts, число сигналов и
подтверждений pullback, среднее ожидание, комиссии, drawdown, win rate, profit
factor и расхождения с production на одинаковых свечах. Candidate остаётся
исследовательским paper-контуром даже при хорошем результате: короткий период,
paper execution и одна рыночная фаза не доказывают готовность к live trading.
