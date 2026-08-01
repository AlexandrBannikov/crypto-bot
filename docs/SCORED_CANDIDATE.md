# Scored Candidate (shadow-only)

`scored_candidate_v1` is an isolated research contour. It evaluates each
closed ETHUSDT 1h candle with a deterministic `signal_score` from 0 to 100;
the score is a ranking of setup factors, not a win/profit probability.

The flow is:

```text
candles → SignalScore → RiskAllocation → stop-aware PositionSizer → shadow journal
```

Control and the existing candidate are not changed. No orders, cash changes,
paper trades or equity snapshots are produced by the shadow runner.

Run locally or in a controlled paper environment:

```bash
python scripts/run_scored_candidate_shadow.py
python scripts/diagnose_scored_candidate.py --days 7 --json
```

Default allocation is the conservative power curve:

```text
minimum_entry_score = 65
full_risk_score = 93
minimum_risk_fraction = 0.10
maximum_risk_fraction = 1.00
curve_exponent = 2.0
```

The fraction applies to the existing maximum risk per trade (default 1%),
never to an unrestricted percentage of capital. Existing stop, capital,
commission and minimum-order guards remain authoritative. Invalid indicators,
stale/insufficient data, invalid stops and zero allocation are hard blocks.

Configuration is intentionally separate and can be supplied through:

Runtime files are isolated under `state/scored_candidate_shadow/`: `runtime.json`,
`decisions.jsonl`, and `runtime.lock`. The systemd timer runs after every hourly
candle close and the feed rejects the still-open candle.

`SCORED_MINIMUM_ENTRY_SCORE`, `SCORED_FULL_RISK_SCORE`,
`SCORED_MINIMUM_RISK_FRACTION`, `SCORED_MAXIMUM_RISK_FRACTION`,
`SCORED_ALLOCATION_CURVE`, `SCORED_CURVE_EXPONENT`,
`SCORED_RISK_MODEL_VERSION`, and `SCORED_CANDIDATE_DECISION_PATH`.

Backtest and walk-forward approval are still required before any paper
execution contour is considered. Real trading and automatic promotion are not
part of this implementation.
