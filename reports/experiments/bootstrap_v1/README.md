# Historical bootstrap v1

Source: `data/eth_usdt_1h.csv`; 1000 hourly candles from 2026-06-03 00:00 UTC through 2026-07-14 15:00 UTC. Both experiments used 1000 USDT, 0.1% per-side commission, 1% stop-aware risk, a 2% stop and no leverage. This validates the pipeline; it is not live-performance evidence.

| Experiment | Decisions | Closed trades | Final equity | Return | Max DD | Fees | Avg MFE | Avg MAE | Avg hold | Sample |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Control Baseline | 1000 | 8 | 1015.93 | +1.59% | 5.69% | 7.94 | 21.48 | -8.72 | 61.12 h | VERY_INSUFFICIENT |
| Relaxed Signal | 1000 | 11 | 130.03 | -87.00% | 87.79% | 4.60 | 6.03 | -4.19 | 46.27 h | INSUFFICIENT |

Both ended with an open position, so final equity differs from cash. The relaxed result is intentionally retained as a negative research result; parameters were not tuned after observing it. Scored Allocation was not replayed because its execution contour remains disabled pending independent validation.
