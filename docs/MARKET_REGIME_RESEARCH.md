# Market Regime Research Framework

This is a read-only research framework for the existing Scored Candidate. It
does not change Control, Candidate, Scored Candidate, Threshold 60, score,
weights, risk, paper execution, or real trading.

## Run

The default input is the complete fixed ETH/USDT hourly history:

```bash
python scripts/regime_research.py
python scripts/regime_research.py --json
python scripts/regime_research.py --csv reports/regime_research.csv
python scripts/regime_research.py --days 365
python scripts/regime_research.py --from 2024-01-01 --to 2025-01-01
```

Date filters select reported observations but retain all earlier candles for
causal indicator warm-up. Future outcomes are censored if a complete 24-hour
horizon is unavailable. CSV is a flat regime/factor table; JSON contains all
annual, rolling, transition, heatmap, and diagnostic detail.

## Deterministic classification

There is no ML, fitting, or future information. At every closed candle after
indicator warm-up, two causal dimensions are calculated:

- trend strength from ADX(14): `<15` range, `15..<20` weak trend,
  `20..<30` moderate trend, and `>=30` strong trend;
- volatility from ATR(14)/close: `<=0.5%` low, `>=2%` high, otherwise normal.

The one and only assigned market regime is their Cartesian combination, such
as `strong_trend/normal_volatility`. This is preferable to allowing volatility
to override trend (or vice versa): precedence would hide one dimension and
confound comparisons. Thresholds are fixed and match existing project
conventions; they are not estimated from the research sample.

The framework reports candle count, history share, average hourly return,
24-hour realized volatility, ATR, ADX, and signed EMA20–EMA50 spread for every
observed composite regime.

## Factor quality

The seven existing contributions are reproduced exactly from `score_v1` and
normalized to percentage utilization. A regression test compares this
vectorized historical calculation with the existing production score function.

Within each regime, predictive quality is the existing 0–100 diagnostic:

```text
100 × max(0,
  0.7 × mean Spearman(factor utilization, future outcomes)
  + 0.3 × monotonicity of median 24h return across utilization buckets
)
```

Future outcomes are 1h, 3h, 6h, 12h, and 24h return plus 24h MFE and MAE.
For each factor the report also shows 24h return Spearman and, for observations
with at least 50% factor utilization, positive rate, mean future return, MFE,
and MAE. A `null` metric means the factor is constant or the cohort is empty;
it is not evidence of quality.

Heatmap stars encode predictive quality: `★★★★★ >=30`, `★★★★ >=20`,
`★★★ >=10`, `★★ >=5`, `★ >0`, and `— =0`. Stars compare diagnostics, not
tradable PnL and not statistical significance.

## Stability and diagnostics

- Calendar-year regime rankings cover 2022 through 2026 (partial endpoint
  years remain explicitly partial).
- Rolling lookbacks are 90, 180, and 365 days, sampled every 90 days plus the
  final dataset timestamp. This measures drift without fitting parameters.
- Every one-candle regime change is counted; the following 24h return is
  summarized by transition pair.
- Near-threshold means `60 <= score < 65`.
- A false negative means `score < 65` and future 24h return `>= +2%`.
- A false positive means `score >= 65` and future 24h return `<= 0%`.

These are hypothetical opportunity labels, not executed trades. Overlapping
24-hour outcomes are intentionally descriptive and must not be treated as
independent samples. Regimes with fewer than 200 observations and partial years
should be considered exploratory.

## Fixed-history result (2022-07-01 through 2026-07-14)

The 35,392-candle history produces 12 composite regimes. The most common are:

| Regime | Candles | Share | Leading factors (quality) |
|---|---:|---:|---|
| strong trend / normal volatility | 11,155 | 31.54% | Trend 9.98; Pullback 5.19 |
| moderate trend / normal volatility | 10,752 | 30.40% | Pullback 32.76; ADX 16.75 |
| weak trend / normal volatility | 5,564 | 15.73% | Pullback 32.07 |
| range / normal volatility | 2,822 | 7.98% | EMA Alignment 6.21 |
| moderate trend / low volatility | 1,424 | 4.03% | EMA Alignment 34.76; Volatility 30.75; Pullback 26.58 |

The remaining seven regimes each represent less than 4% of history. High
volatility is especially sparse (783 candles total), so its apparently strong
factor scores are hypotheses, not robust recommendations.

Factor leadership changes materially by regime. Pullback is strong in moderate
and weak normal-volatility trends, Trend is only weak in the most common strong
normal-volatility regime, and ADX is moderate there only in the moderate-trend
band. This supports the existence of conditional factor behavior. It does not
yet support adaptive weights: annual regime slices are volatile, overlapping
outcomes reduce effective sample size, and several cells are small.

Across annual regime cells, Pullback has the highest mean quality (20.14) and
is positive in 64.8% of cells, but also the highest dispersion (20.24).
Momentum is the least variable non-constant factor (mean 3.85, standard
deviation 7.68), but is too weak to call usefully stable. Trading Cost is
perfectly stable only because it is constant, so it has no ranking value.

Near-threshold observations total 1,019; 829 (81.4%) occur in strong trend /
normal volatility. False positives total 895; 815 (91.1%) occur in that same
regime. False negatives are broader (7,180), led by moderate trend / normal
volatility (2,251) and strong trend / normal volatility (2,145). These
concentrations suggest improving factor definitions and calibration diagnostics
inside the current score before introducing a regime-dependent strategy.

## Research conclusion

Yes: the fixed sample is consistent with different market regimes in which the
same factors rank outcomes differently. The evidence is descriptive rather
than sufficient for deployment. No adaptive weights should be implemented at
this stage. The next defensible step is out-of-sample validation with minimum
regime sample sizes, non-overlapping outcome cohorts, confidence intervals, and
multiple assets. If the conditional differences survive those checks, a
separate shadow-only adaptive experiment can be proposed; otherwise improving
the current redundant/weak factors is sufficient.
