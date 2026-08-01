# Setup Type Research Framework

`setup_type_research_v1` is a read-only layer over the existing historical
research stack. It never enters runtime decision-making or execution.

```text
historical candles
  -> causal indicators
  -> exact score_v1 replay
  -> deterministic market regime
  -> causal direction votes
  -> setup_type_v1 classification
  -> future outcome labels and research statistics
```

Future returns and MFE/MAE are absent from `classify_direction` and
`classify_setup`. They are attached only after classification. Score components
retain `score_version=score_v1`; setup decisions retain
`setup_version=setup_type_v1`, reasons, supporting/conflicting features, and a
rule-coverage confidence that is explicitly not a probability of profit.

## CLI

```bash
python scripts/setup_type_research.py
python scripts/setup_type_research.py --json
python scripts/setup_type_research.py --csv reports/setup_decisions.csv
python scripts/setup_type_research.py --setup-type long_trend_continuation --non-overlapping
python scripts/setup_type_research.py --from 2025-01-01 --to 2026-01-01 --json
python scripts/setup_type_research.py --direction uptrend --regime strong_trend/normal_volatility
python scripts/setup_type_research.py --trend-episodes --json
```

Supported validation flags are `--asset`, `--setup-type`, `--direction`,
`--regime`, `--non-overlapping`, `--trend-episodes`, `--score-version`, and
`--setup-version`, plus `--days`, `--from`, and `--to`. Only ETH/USDT is
accepted because the repository has no validated BTC or SOL dataset. No data is
downloaded. JSON is aggregate; CSV is decision-level with timestamp, asset,
regime, direction, setup type/version, score, threshold, 3/6/12/24h returns,
24h MFE/MAE, episode id, reasons, and causal features.

## Direction rules

Direction uses four equally explicit votes available at candle close:

1. EMA20 above/below EMA50;
2. EMA50 five-candle slope above +0.02% or below -0.02%;
3. close above/below EMA50;
4. five-candle price/swing change above +0.10% or below -0.10%.

At least three agreeing votes produce UPTREND or DOWNTREND; otherwise direction
is NEUTRAL. Mixed votes are retained as conflicts. Recent high and low use a
causal rolling 20-candle window. Crossover age comes from the current
EMA20/EMA50 direction. No future value is used.

## Setup taxonomy and fixed v1 rules

Rules were fixed before validation/test reporting and are not fitted by ML.
Rule priority is part of `setup_type_v1`.

Research features also retain candles since the last below-EMA20 pullback,
three-candle pullback-volume versus its preceding 20-candle baseline, and
current recovery-volume versus the preceding three candles. These are causal
context fields; they do not silently redefine the production pullback factor.

- `late_trend_chasing`: uptrend and price at least 3% above EMA20, or within
  0.5% of its recent high after at least five candles without a close below
  EMA20 and EMA spread at least 2.5%.
- `pullback_continuation`: uptrend structure, 1–5 closes in pullback or at least
  0.15% depth, no deep EMA violation, and positive recovery candle.
- `long_trend_continuation`: uptrend, close above EMA20, positive EMA slope,
  non-contracting spread, and 0.25–5% below recent high.
- `counter_trend_rebound`: downtrend plus strong positive current momentum and
  a fast-EMA cross or recovery at least 1% from the recent low.
- `downtrend_continuation`: downtrend without causal rebound/reversal evidence.
- `reversal_attempt`: structural contraction/cross inconsistent with the
  prevailing direction, or a strong cross in neutral context.
- `range_breakout_attempt`: neutral range context, positive momentum, and close
  within 0.75% of the recent high.
- `unclassified`: insufficient or contradictory rule evidence.

These labels describe the information available now. Outcome decomposition may
later identify any DOWNTREND observation followed by a +2% return as a
counter-trend rebound; that post-outcome label does not alter the causal setup.

## Outcomes, independence, and statistics

The report includes returns at 3/6/12/24h and MFE/MAE at 6/12/24h. Existing
labels are explicit: GOOD is score ≥65 and 24h return >0; BAD is score ≥65 and
return ≤0; MISSED is score <65 and return ≥2%. Sensitivity cohorts use return
≥1%, return ≥2%, MFE ≥2%, return ≤-1%, and MAE ≤-2%.

The default includes all hourly observations. `--non-overlapping` greedily
selects one chronologically ordered observation per 24 hours, so future windows
cannot overlap. Trend episodes run from one direction classification to the
next and report duration, first/last/best/worst score, GOOD/BAD counts, and
near-threshold counts.

GOOD/BAD comparisons occur only inside each setup type. They include sample
size, mean/median/std/percentiles, Cohen's d, and a deterministic 1,000-resample
bootstrap CI. `MIN_SETUP_SAMPLES=30`; smaller sides receive
`INSUFFICIENT_DATA`. SciPy is not a project dependency, so no Mann–Whitney
result is fabricated; the report states `UNAVAILABLE_NO_SCIPY_DEPENDENCY`.

## Fixed-history result

Period: 2022-07-03 through 2026-07-14; 35,327 scored observations, 1,472
non-overlapping observations, and 4,120 direction episodes.

| Setup type | Count |
|---|---:|
| Downtrend continuation | 10,892 |
| Long trend continuation | 9,116 |
| Reversal attempt | 4,898 |
| Unclassified | 4,329 |
| Counter-trend rebound (causal current-candle form) | 3,126 |
| Pullback continuation | 2,028 |
| Late trend chasing | 866 |
| Range breakout attempt | 72 |

Direction distribution is 16,025 UPTREND, 15,359 DOWNTREND, and 3,943
NEUTRAL. Mixed indicator evidence is retained for explainability rather than
silently forced into a direction.

### Strong-trend/normal-volatility focus

The focus contains the original 11,155 observations and 693 non-overlapping
ones. Its 2,145 MISSED decompose into:

| Outcome decomposition | Count | Share |
|---|---:|---:|
| Counter-trend rebound (DOWNTREND) | 1,299 | 60.6% |
| True missed long continuation | 519 | 24.2% |
| True missed pullback continuation | 31 | 1.4% |
| Reversal rebound | 113 | 5.3% |
| Unclassified/other | 183 | 8.5% |

Thus only 550 (25.6%) are causal long/pullback continuation setups. The prior
false-negative count overstates continuation misses by roughly four times.

The 815 BAD signals decompose into 165 late chasing, 112 failed pullback
continuations, 81 exhausted continuations, 281 reversal attempts against the
position, and 176 unclassified. There are no supported downtrend-misclassified
or range false-breakout cells in this focused threshold cohort.

Across all regimes, score 60–70 contains 1,839 observations: 890 positive and
949 non-positive. Long continuations account for 301 GOOD versus 394 BAD;
reversal attempts 299 versus 298; pullback continuations 121 versus 122; and
late chasing 99 versus 102. The near-threshold band therefore has no clean
setup-type separator either.

Across all regimes, non-overlapping selection reduces MISSED from 7,180 to 310
and BAD from 895 to 32. Eighty-two trend episodes contain multiple false
positives; the worst contains 35. Neighboring hourly labels therefore greatly
inflate apparent sample size.

### Within-type separation

All four threshold-active types have at least 30 GOOD and BAD observations,
but effects remain small:

- long continuation: largest `d=0.167` (EMA spread), bootstrap CI for the mean
  difference includes zero;
- late chasing: EMA spread `d=0.297`, CI `[+0.082,+0.490]`; distance from recent
  high `d=-0.218`;
- pullback continuation: distance from EMA `d=-0.332`, spread change `-0.302`,
  ADX slope `-0.290`;
- reversal attempt: EMA spread `d=0.270`, distance from high `-0.235`, spread
  change `-0.214`.

Counter-trend rebound, downtrend continuation, range breakout, and unclassified
threshold comparisons are `INSUFFICIENT_DATA` on at least one outcome side.

### Out-of-sample stability

The fixed classifier is reported without retuning:

| Split | Observations | Long continuation mean 24h | Chasing mean 24h |
|---|---:|---:|---:|
| Train: 2022-07–2024-12 | 21,894 | +0.20% | +0.50% |
| Validation: 2025 | 8,760 | -0.15% | +1.05% |
| Test: 2026 | 4,649 | -0.10% | -0.57% |

Pullback continuation similarly moves from +0.22% to +0.07% to -0.39%.
Taxonomy coverage persists yearly, but outcome meaning is unstable. Rolling
90/180/365-day tables in JSON show the same drift. Therefore the classifier is
useful for cleaning labels and episode analysis, but not ready as a trading
filter.

## Data quality and conclusion

Data status is `OK_WITH_WARNINGS`: zero duplicate timestamps, zero hourly gaps,
zero invalid types, zero score-version mismatches, and 24 unavailable 24h
outcomes at the endpoint. Twenty-six warm-up rows have missing indicators and
are excluded before scored decisions. Of 35,327 observations, 33,855 have a
24h window overlapping another observation, which is why non-overlap results
are mandatory.

Research status: `COUNTER_TREND_MISSED_OVERSTATED`. This does not mean the
classifier is ready for execution. `READY_FOR_V2_EXPERIMENT_DESIGN` is not
justified because continuation/chasing performance changes sign out of sample.
The next step should be an episode-level, non-overlapping refinement of the
anti-chasing definition on additional assets—not a Scored Candidate v2 shadow
experiment yet.
