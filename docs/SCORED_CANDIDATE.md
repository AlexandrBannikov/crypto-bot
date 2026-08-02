# Scored Candidate (shadow-only)

`scored_candidate_v1` is an isolated research contour. It evaluates each
closed ETHUSDT 1h candle with a deterministic `signal_score` from 0 to 100;
the score is a ranking of setup factors, not a win/profit probability.

## Entry Score explainability

Entry Score describes one concrete entry setup. It is distinct from Strategy
Confidence, which describes historical sample adequacy, performance, risk,
stability, data quality and operational maturity. Strategy Laboratory shows
Entry Score only in a diagnostic section; it is not a direct promotion-review
input.

The unchanged thresholds are 65 (entry allowed with reduced risk) and 80 (the
reporting label `strong`). Below 65, HOLD with zero allocation is expected. The
existing sizing curve remains authoritative: it begins at 10% of base risk at
65 and reaches 100% at 93. Therefore the 80 strong-entry label does not imply
100% allocation.

The seven real components and maxima are `trend` (25), `ema_alignment` (15),
`adx` (20), `pullback` (20), `momentum` (10), `volatility` (5), and `cost` (5).
Their weighted values come from `evaluate_signal`; reporting does not reproduce
the scoring formula. Total is their sum. The sum is reconciled to total score
with tolerance 0.000001. A mismatch creates a warning but cannot change the
decision.

A limiter is an available component whose deficit `(maximum - weighted score)`
is at least 10% of its maximum. Limiters sort by absolute deficit and then by
stable scoring order; the first three are reported. Positive factors are the
first three non-zero components at least 60% complete, sorted by completion.
Unavailable components are excluded from both rankings.

```json
{
  "total_score": 34.373621,
  "max_score": 100,
  "entry_threshold": 65,
  "strong_entry_threshold": 80,
  "distance_to_entry": -30.626379,
  "decision": "HOLD",
  "risk_allocation_pct": 0.0,
  "score_band": "below_entry",
  "allocation_rule_id": "risk_curve_v1",
  "score_consistent": true,
  "calculation_version": "score_breakdown_v1"
}
```

Read-only inspection:

```bash
python scripts/show_scored_candidate.py --latest
python scripts/show_scored_candidate.py --components
python scripts/show_scored_candidate.py --json
python scripts/show_scored_candidate.py --aggregate 24h
python scripts/show_scored_candidate.py --aggregate 7d
python scripts/show_scored_candidate.py --aggregate all
```

Old JSONL records are never rewritten. Records without breakdowns, strong
thresholds, allocation amounts or baseline amounts render as N/A. A score such
as 34 correctly remains HOLD because it is below 65. This report is not a
recommendation to tune thresholds: component observations should accumulate
and be analysed statistically before any separate strategy-change proposal.

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

## Experiment A: threshold 60

`scored_candidate_v1_score60` is an optional, journal-only shadow contour. It
uses the same ETHUSDT spot 1h closed-candle feed, score configuration, power
allocation curve, 1% base risk, 2% stop distance and 0.1% fee assumption as
`scored_candidate_v1`. Its only configuration delta is:

```text
minimum_entry_score: 65 → 60
```

It never reads or writes Control, Candidate, paper execution, trades, equity or
the threshold-65 runtime files. Its files are:

```text
state/scored_candidate_threshold60/runtime.json
state/scored_candidate_threshold60/decisions.jsonl
state/scored_candidate_threshold60/runtime.lock
```

On first start, the runner fetches enough closed candles to match the exact
timestamp range already present in the threshold-65 journal. Later cycles use
the same rolling 500-candle feed as threshold 65. The comparison reports any
score/component mismatch, so results must not be interpreted unless that count
is zero.

```bash
python scripts/run_scored_threshold60_shadow.py
python scripts/diagnose_scored_threshold60.py --days 7 --json
python scripts/compare_scored_thresholds.py --json
python scripts/check_scored_threshold60_health.py
```

The comparison aligns both journals by candle close, reports decisions,
allocation and economic diagnostics, isolates entries with `60 <= score < 65`,
and calculates 3h/6h/12h/24h close returns plus 24h MFE and MAE from closed
candles. `--minimum-order-value` defaults to 5 USDT and can be overridden for
the current instrument rules. Estimated commission is round-trip notional at
the unchanged 0.1% fee rate per side.

The Telegram command `/score_compare` exposes the local read-only comparison
to the single configured owner chat. It is deliberately absent from morning
and evening reports. The experiment health command is optional: missing state
reports `disabled` and exits successfully, so production health remains OK.
