# Scored Candidate Factor Research

`app/factor_research.py` is an analysis-only framework for measuring whether
the existing Scored Candidate factors rank future market outcomes. It does not
change factors, thresholds, decisions, runtime state, execution, or risk.

Run the fixed historical dataset:

```bash
python scripts/factor_research.py
python scripts/factor_research.py --json
python scripts/factor_research.py --csv reports/factor_research.csv
python scripts/factor_research.py --days 30
python scripts/factor_research.py --from 2026-06-15 --to 2026-07-01
```

Date filters select setup timestamps while preserving earlier candles for EMA,
ADX, and other indicator warm-up. Future outcomes are censored when the dataset
does not contain the complete requested horizon.

## Predictive quality

The score is deliberately not a PnL optimization metric. It is bounded to
0–100 and combines:

```text
100 × max(0,
  0.7 × mean predictive Spearman correlation
  + 0.3 × monotonicity of median 24h return across utilization buckets
)
```

Predictive Spearman inputs are returns at 1h, 3h, 6h, 12h, and 24h plus 24h
MFE and MAE. Positive MAE correlation means higher factor values are associated
with less-negative adverse excursion. Bucket monotonicity asks whether median
24h outcome generally improves from the 0–20% bucket through 80–100%.

Interpretation:

- 30 or above: strong within this sample;
- 15–30: moderate;
- 5–15: weak;
- below 5: negligible or adversely ranked.

A zero does not mean the market variable has no value. It means the current
factor contribution does not provide positive monotonic ranking under this
metric. Results must be checked on separate periods and walk-forward windows.

## Framework outputs

For Trend, EMA Alignment, ADX, Pullback, Momentum, Volatility, and Trading Cost
the report contains:

- contribution and utilization distributions, min/max/mean/median/std and
  p10/p25/p50/p75/p90;
- five fixed utilization buckets with count, average/median return, positive
  rate, MFE, MAE, downside p10, and worst result;
- Spearman correlations for every return and excursion horizon;
- a factor correlation matrix and pairs with absolute correlation at least
  0.80;
- leave-one-factor-out importance: the change in total-score Spearman ranking
  after removing one contribution, without ML or refitting;
- best and worst 24h cohorts;
- score 55–64 near misses;
- false negatives (`score < 65`, future 24h return at least +2%);
- false positives (`score >= 65`, future 24h return at most 0%).

“Trades” in cohort labels mean hypothetical setup opportunities. The framework
does not simulate fills or create trades.

## Current fixed-sample result

On `data/eth_usdt_1h.csv` (1,000 candles, 935 valid setups), the ranking is:

| Rank | Factor | Predictive quality | Mean leave-one-out importance |
|---:|---|---:|---:|
| 1 | ADX | 33.74 | +0.0794 |
| 2 | Pullback | 11.28 | +0.0124 |
| 3 | Trend | 0.00 | −0.0174 |
| 4 | EMA Alignment | 0.00 | −0.0545 |
| 5 | Momentum | 0.00 | −0.0186 |
| 6 | Volatility | 0.00 | +0.0004 |
| 7 | Trading Cost | 0.00 | 0.0000 |

ADX is the only strong factor in this sample. Its 40–60% and 80–100% buckets
have mean 24h returns of +1.18% and +1.06%, compared with −0.13% and −0.57%
in the bottom two buckets. Pullback is weak: its 24h Spearman correlation is
negative, although its bucket medians have limited positive ordering.

Trend and EMA Alignment are almost duplicates (Spearman 0.988). Removing EMA
Alignment improves ranking more than removing any other factor, which is a
warning that the current pair double-counts a signal that was not predictive
in this period. Trading Cost is constant at 90% utilization and cannot rank
setups at all.

The result is not stable enough for configuration changes: on the final seven
days Trend ranks first while ADX falls to zero. The appropriate next step is
anchored walk-forward factor stability analysis across the full historical
dataset, not weight tuning on this single 1,000-candle sample.
