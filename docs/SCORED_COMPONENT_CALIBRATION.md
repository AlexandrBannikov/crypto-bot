# Scored Candidate component calibration

This is a read-only research gate. It does not alter Control, Candidate,
Scored Candidate v1, the threshold-60 experiment, execution, risk, or equity.

Reproduce the fixed historical report:

```bash
python scripts/analyze_scored_components.py \
  --source historical \
  --data data/eth_usdt_1h.csv \
  --json
```

Live journals can be analyzed separately against the current closed-candle
feed:

```bash
python scripts/analyze_scored_components.py --source live-shadow \
  --journal state/scored_candidate_shadow/decisions.jsonl --threshold 65 --json
python scripts/analyze_scored_components.py --source live-shadow \
  --journal state/scored_candidate_threshold60/decisions.jsonl --threshold 60 --json
```

## Gate result

The fixed `data/eth_usdt_1h.csv` replay covers 1,000 candles from 2026-06-03
00:00 UTC through 2026-07-14 15:00 UTC. Sixty-five warm-up decisions are
excluded, leaving 935 valid setup decisions.

| Component | Mean utilization | Primary limiter | Top-2 | Top-3 |
|---|---:|---:|---:|---:|
| trend | 12.18% | 65.24% | 89.09% | 96.15% |
| ema_alignment | 36.59% | 0.00% | 45.13% | 49.73% |
| pullback | 37.24% | 23.42% | 30.70% | 46.52% |
| ADX | 48.94% | 4.49% | 12.09% | 43.64% |
| momentum | 50.61% | 6.84% | 17.97% | 40.64% |
| volatility | 61.24% | 0.00% | 5.03% | 23.32% |
| cost | 90.00% | 0.00% | 0.00% | 0.00% |

The separately aligned live reports agree: trend is primary for 71.0% of 500
decisions, Pullback for 21.4%, and ADX for 0.8%. Threshold 65 and threshold 60
have identical component statistics because they use the same scoring model;
only their entry threshold and path-dependent shadow decisions differ.

Therefore Pullback is a material secondary limiter, but it is not the primary
reason the model rarely reaches the entry threshold. The experiment gate that
requires Pullback to be the primary limiter is not satisfied.

## Current Pullback function

The contribution is:

```text
touch   = clamp((EMA20 - low) / (EMA20 * 0.0075), 0, 1)
near    = clamp(1 - abs(close - EMA20) / (EMA20 * 0.0075), 0, 1)
retrace = clamp((EMA20 - close) / (EMA20 * 0.0075), 0, 1)
score   = 20 * clamp(0.4*touch + 0.4*near + 0.2*retrace, 0, 1)
```

The function is continuous and deterministic; no binary discontinuity like
`0.99 → 2` and `1.00 → 14` was found. It is piecewise linear with derivative
kinks at clamp and absolute-value boundaries. It is not globally monotonic.
It has no explicit deep-pullback or trend-structure penalty, and its weights
make a full 20/20 contribution unreachable. The observed maximum was 15.95.

Pullback utilization buckets were: 254 decisions at 0–10%, 70 at 10–20%, 107
at 20–40%, 133 at 40–60%, 371 at 60–80%, and none above 80%. Categorization
found 101 no-pullback, 192 shallow, 185 normal, 35 deep, and 422 trend-structure
break decisions. Absence of pullback is not treated as automatically good.

## Outcome evidence

Pullback contribution has almost no useful monotonic relation to forward
returns: Spearman correlations are +0.022 (1h), +0.060 (3h), +0.042 (6h),
-0.009 (12h), and -0.058 (24h). Its 24h MFE correlation is -0.007 and MAE
correlation is -0.122. The lowest 0–10% utilization bucket was not worse than
the upper buckets: its 24h mean return was +0.562% with a 58.5% positive rate.
Thus the present Pullback component offers weak ranking information, but this
does not prove that awarding more points is safe.

ADX is less often a limiter and has more useful forward association: its
Spearman correlation is +0.082 at 6h, +0.180 at 12h, +0.207 at 24h, and +0.291
with 24h MFE.

Counterfactually replacing Pullback by its historical median would create 52
threshold crossings: mean 24h return +0.491%, 63.5% positive, mean MFE +2.425%,
mean MAE -1.409%. Replacing it by p75 creates 59 crossings: mean 24h return
+0.447%, 61.0% positive, MFE +2.409%, MAE -1.534%. Awarding the maximum creates
118 crossings but degrades the positive rate to 50.8% and MAE to -1.826%.
These are counterfactual research results, not a deployable model. Median and
p75 ADX replacements create no threshold crossings.

Estimated round-trip fees remain 10% of stop-risk under the unchanged 0.1%
per-side fee and 2% stop. Counterfactual positions do not fall below 5 USDT.

## Decision

Status: `PULLBACK_NOT_PRIMARY_LIMITER`.

No Pullback Relaxed implementation, runtime, unit, Telegram command, health
dependency, paper execution, or rollout is created. A future calibration stage
could evaluate a small, preregistered set of continuous Pullback shapes, but it
must first define an explicit deep/structure penalty and a gate focused on
good-trend subsets rather than awarding points globally.
