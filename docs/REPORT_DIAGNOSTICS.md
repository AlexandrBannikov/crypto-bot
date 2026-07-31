# Отчёты и диагностика

Утренний отчёт разделяет cash balance и equity. Cash — свободный остаток
после открытия позиции; equity включает рыночную стоимость позиции.
Realised PnL относится только к закрытым сделкам, unrealised PnL — к открытой
позиции. Если цены входа или рынка нет, значение показывается как `N/A`, а не
как ноль.

`Health` содержит общий статус и причины. Недоступность `systemctl` — это
диагностический `UNKNOWN`/warning и не доказывает неисправность торгового
цикла; состояние heartbeat и paper state проверяются отдельно. Для часовых
свечей timestamp считается временем открытия, поэтому freshness вычисляется
от времени закрытия.

`Решения стратегии` — события журнала решений, а `сделки` — фактически
зафиксированные paper trades. Candidate ADX + HYBRID Pullback сохраняет
компактный `reason_code` (например `adx_below_threshold`,
`pullback_not_detected`, `trend_not_confirmed`, `entry_allowed`). Отсутствие
сделок у candidate имеет статус `INSUFFICIENT_DATA`, а не считается успехом.

Read-only диагностика:

```bash
python scripts/diagnose_candidate.py --hours 12
python scripts/diagnose_candidate.py --days 7 --json
python scripts/check_equity_history.py --mode production
python scripts/check_equity_history.py --mode candidate --json
python scripts/repair_equity_history.py --mode production --dry-run --deduplicate-exact
```

Канонический ключ equity snapshot — `environment + strategy_name +
candle_close_timestamp`. `created_at_utc` и `snapshot_reason` сохраняются для
аудита, но не создают второй snapshot того же закрытого периода. Repair CLI
по умолчанию только строит план. Изменение базы требует `--apply`, создаёт
SQLite-safe backup и блокируется при timestamp conflicts:

```bash
python scripts/repair_equity_history.py --mode production \
  --deduplicate-exact --apply
```

Пропущенные периоды не интерполируются. Gap остаётся в истории и получает
диагностическую классификацию.

Performance Guard только сообщает статус (`HEALTHY`, `WARNING`, `DEGRADED`,
`INSUFFICIENT_DATA`); он не останавливает торговлю, не меняет параметры и не
продвигает candidate. Параметры:

`MARKET_DATA_WARNING_AGE_MINUTES`, `MARKET_DATA_CRITICAL_AGE_MINUTES`,
`PERFORMANCE_GUARD_ENABLED`, `PERFORMANCE_MIN_CLOSED_TRADES`,
`PERFORMANCE_WARNING_DRAWDOWN_PCT`, `PERFORMANCE_CRITICAL_DRAWDOWN_PCT`,
`PERFORMANCE_MAX_HOURS_WITHOUT_SNAPSHOT`.
