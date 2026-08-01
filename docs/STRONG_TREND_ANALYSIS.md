# Strong Trend Failure Analysis

This framework explains historical Scored Candidate outcomes inside the single
`strong_trend/normal_volatility` regime. It is analysis-only: Control,
Candidate, Scored Candidate, score, weights, threshold, risk, paper, real
trading, systemd, and strategy routing are unchanged. No new candidate exists.

## Run

```bash
python scripts/analyze_strong_trend_failures.py
python scripts/analyze_strong_trend_failures.py --json
python scripts/analyze_strong_trend_failures.py --csv reports/strong_trend.csv
python scripts/analyze_strong_trend_failures.py --days 365
python scripts/analyze_strong_trend_failures.py --from 2024-01-01 --to 2025-01-01
```

The default input is `data/eth_usdt_1h_full.csv`. Date filters select reported
signals while retaining preceding history for indicator warm-up.

## Cohorts

- GOOD: score `>=65` and future 24h return `>0`.
- BAD: score `>=65` and future 24h return `<=0`.
- MISSED: score `<65` and future 24h return `>=+2%`.
- Near-threshold: score from 60 through 70, split by positive/non-positive 24h
  return.

The cohorts intentionally answer different questions and do not partition all
regime candles. Outcomes overlap, so confidence intervals are descriptive and
must not be interpreted as independent-trade inference.

## Causal features

All features use only the current and earlier candles:

- EMA spread: signed `(EMA20-EMA50)/close`;
- EMA slope: three-candle EMA20 percentage change;
- ADX slope: three-candle ADX difference;
- ATR expansion: three-candle ATR percentage change;
- momentum: candle close-open return;
- pullback depth: positive distance from candle low to EMA20;
- pullback duration: consecutive closes below EMA20;
- distance from recent high: close versus causal rolling 20-candle high;
- trend age/candles after crossover: candles in the current EMA20/EMA50
  direction, including both upward and downward trends;
- candle body and upper/lower wick: percentage of high-low range;
- volume and volume/SMA20, when supplied by the historical file.

ADX dynamics are rising above `+0.5`, falling below `-0.5`, otherwise flat.
EMA spread dynamics use a three-candle change of `±0.05` percentage points.
ATR dynamics use a three-candle change of `±2%`.

GOOD/BAD comparison includes mean, median, population standard deviation,
p10/p25/p50/p75/p90, Cohen's d, and an analytical 95% confidence interval for
the difference of means.

## Full-history results

Period: 2022-07-04 through 2026-07-12. The regime contains 11,155 complete
24-hour observations:

| Cohort | Count | Mean 24h return |
|---|---:|---:|
| GOOD | 821 | +3.32% |
| BAD | 815 | -2.02% |
| MISSED | 2,145 | +4.53% |

Among threshold signals, GOOD and BAD are almost evenly split. This is the
central failure: strong ADX and near-max EMA alignment raise many observations
to a similar score, but those saturated components barely distinguish the next
24-hour direction.

### GOOD versus BAD

No measured feature has a medium effect. The largest absolute effects are:

| Feature | GOOD mean | BAD mean | Cohen's d | Interpretation |
|---|---:|---:|---:|---|
| EMA spread | 2.59% | 2.44% | +0.183 | Wider separation is modestly better |
| Pullback depth | 0.36% | 0.25% | +0.176 | GOOD has somewhat deeper pullbacks |
| Distance from recent high | -2.10% | -1.87% | -0.172 | BAD is slightly closer to the high |
| Pullback duration | 0.65 | 0.48 | +0.116 | Duration adds weak information |
| ATR expansion | +2.61% | +1.29% | +0.114 | Expansion is weakly favorable |
| Raw volume | 8,637 | 7,821 | +0.113 | Higher activity is weakly favorable |
| ADX slope | -1.26 | -0.83 | -0.099 | Falling ADX is not a BAD separator |

Momentum, volume ratio, trend age, candle anatomy, absolute ADX, absolute ATR,
EMA slope, and distance from EMA all have `|d| <0.06` (momentum is only 0.051)
and are nearly useless as standalone separators in this sample.

### False negatives

MISSED primary limiters are Trend (1,476), Pullback (570), and Momentum (99).
Mean threshold deficit is 17.80 points, so most misses are not marginal 64-point
setups. The neutral regime definition measures strength but not direction;
many strong downtrend observations therefore receive little or no long Trend
contribution and later qualify as +2% reversal misses. This explains a large
part of the apparent false-negative concentration and argues against simply
lowering the threshold.

### False positives and near-threshold

BAD has slightly higher mean Volatility (+1.29 utilization points) and Momentum
(+1.25) than GOOD, while ADX and EMA Alignment are saturated in both groups.
This is weak component overvaluation, not evidence for a single bad factor.

There are 1,557 score-60–70 observations: 742 good and 815 bad. Their largest
effects remain small: volume `d=0.131`, pullback depth `0.126`, momentum
`-0.104`, ATR `-0.103`, ATR expansion `0.099`, and pullback duration `0.098`.
Score proximity alone does not expose a clean boundary.

### Hypotheses

Trend age is non-monotonic: mean 24h return is +0.60% at age 1–5, -0.41% at
11–20, +0.66% at 41–50, and +0.26% beyond 50. The simple hypothesis “old is
worse” is rejected.

Long pullbacks (`>=6` closes below EMA20) average -0.31%, compared with +0.34%
when duration is zero. But GOOD/BAD threshold signals show only a small duration
effect, so duration needs joint analysis with trend direction and depth.

ADX falling averages +0.16% versus -0.02% for rising ADX. EMA expanding is
+0.16% versus approximately zero when contracting. ATR expanding, flat, and
contracting are almost indistinguishable (+0.04% to +0.07%). Thus a blanket ADX
falling or ATR contracting penalty is not supported.

## Recommendations for a future v2 research candidate

Do not implement changes from this result alone. Reasonable next experiments:

1. Test EMA spread magnitude jointly with spread expansion/contraction.
2. Test pullback depth jointly with duration and trend direction.
3. Test distance from the recent high plus volume as anti-chasing/context
   features.
4. Rework saturated ADX and EMA Alignment diagnostics: both score GOOD and BAD
   almost equally and cannot rank outcomes well inside this regime.
5. Separate continuation opportunities from counter-trend reversal misses
   before evaluating false negatives.
6. Validate with non-overlapping outcomes, multiple assets, minimum sample
   sizes, and genuine out-of-sample periods.

Do not add a simple old-trend, falling-ADX, or ATR-contraction penalty. The fixed
history does not support those rules.
