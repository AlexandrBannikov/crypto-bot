# Paper strategy modes

`scripts/run_bybit_controller.py` supports three paper-only strategy
modes through `PAPER_STRATEGY_MODE` or the higher-priority
`--strategy-mode` CLI option:

- `baseline` (default) preserves the legacy paper execution path.
- `filtered` applies the market-regime filter only to new entries.
- `shadow` executes the baseline decision and records the filtered
  decision separately without changing positions, balance, fees, or
  the trade journal.

The filter is fail-closed for new entries: detector/filter errors block
an entry in `filtered` mode. Exits and stop-loss actions bypass the
filter. In `shadow` mode, detector errors never block baseline
execution.

Configuration variables:

- `REGIME_ADX_PERIOD` (default `14`)
- `REGIME_ADX_THRESHOLD` (default `20`)
- `REGIME_ATR_PERIOD` (default `14`)
- `REGIME_LOW_VOLATILITY_THRESHOLD` (default `0.005`)
- `REGIME_HIGH_VOLATILITY_THRESHOLD` (default `0.02`)
- `REGIME_MINIMUM_CONFIDENCE` (default `0`)
- `SHADOW_DIAGNOSTICS_PATH` (default
  `state/shadow_decisions.jsonl`)
- `SHADOW_DIAGNOSTICS_ENABLED` (default `true`)

Shadow diagnostics are append-only JSON Lines. A sidecar state file
stores the last deduplication key; an incomplete final JSONL record is
repaired safely after a crash. Both files belong under generated
`state/` storage and must not be committed.

Generate a summary with:

```bash
python scripts/report_shadow_decisions.py
```
