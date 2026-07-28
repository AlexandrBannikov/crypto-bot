# Strategy v2 research filters

Strategy v2 is an offline research contour. It is not imported by the paper
controller and does not read production environment variables.

The baseline is `EMACrossStrategy(20, 50)` executed by the existing
`BacktestEngine` with an initial balance of 1000 USDT and a fee rate of 0.001
per operation. All variants use the same engine and position sizing.

## Entry filters

`ATRVolatilityFilter` computes `ATR / close` from candles up to and including
the current candle. Both configured bounds are inclusive:

```text
minimum_relative_atr <= ATR / close <= maximum_relative_atr
```

`ADXStrengthFilter` checks trend strength without choosing its direction. Its
threshold is inclusive:

```text
ADX >= minimum_adx
```

Filters receive only the current and previous candles, apply only to new
entries, and are composed with explicit AND logic. Exit signals are returned
unchanged. A disabled filter is omitted from the composition, so the disabled
variant preserves the exact baseline result.

Every filter returns a structured reason: `allowed`, `blocked_by_atr`,
`blocked_by_adx`, `insufficient_history`, or `invalid_indicator_value`.

`PullbackEntryFilter` is a stateful, LONG-only research filter. An EMA cross-up
arms one pending entry instead of entering immediately. `LOW_TOUCH` confirms
on one of the next `max_wait_bars` candles when `low <= EMA20` and the candle
closes above EMA20. `CLOSE_TOUCH` requires a close at or below EMA20 followed
by a close back above it. The cross candle cannot confirm itself. Loss of
`EMA20 > EMA50`, a contrary exit, or a repeated cross cancels the pending
event; expiry of the inclusive wait window records a timeout.

Pullback decisions use `waiting_pullback`, `pullback_confirmed`,
`pullback_timeout`, and `pullback_cancelled`. ATR and ADX are evaluated on the
confirmation candle and remain an explicit AND condition. Exits are never
filtered.

The project ATR and ADX use `ewm(alpha=1/period, adjust=False)` smoothing.
Their initial seed is therefore slightly different from classic Wilder
arithmetic-mean seeding. A fixed OHLC reference test records this difference;
the implementation is intentionally unchanged for this experiment.

## Reproducible experiment

Run:

```bash
python scripts/compare_strategy_v2_filters.py
```

The command evaluates `baseline`, `atr`, `adx`, and `atr_adx` on full, train,
and out-of-sample periods, followed by fixed-parameter rolling walk-forward
windows. It writes only to `reports/strategy_v2/`:

- `comparison_full_train_oos.csv`
- `walk_forward_windows.csv`
- `summary.json`
- `metadata.json`

No Strategy v2 option is connected to production paper execution.

The pullback factorial and sensitivity experiment is run separately:

```bash
python scripts/compare_strategy_v2_pullback.py
```

It evaluates eight fixed variants on full/train/OOS data and walk-forward
windows. The primary pullback is `max_wait_bars=5`, `LOW_TOUCH`; sensitivity
also evaluates waits 3, 5, and 8 with both touch modes. It writes
`pullback_comparison.csv`, `pullback_walk_forward_windows.csv`,
`pullback_summary.json`, and updates only the research `metadata.json`.
