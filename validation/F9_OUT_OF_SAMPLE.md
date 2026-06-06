# F9 — Honest Out-of-Sample Validation (2014 + 2018 + 2022)

**Date:** 2026-06-06 · **Closes:** F9 (forensic audit) / R4 acceptance criterion
**Harness:** [`backtest_kicktipp_folds.py`](../backtest_kicktipp_folds.py) · **Raw output:** [`backtest_folds_2014_2018_2022.txt`](backtest_folds_2014_2018_2022.txt)

## Why this replaces the old conclusion

The prior analysis ([`backtest_engine_real.md`](backtest_engine_real.md)) conceded the optimized
engine *loses* on real WC2022 data (99 vs 104 Kicktipp pts) but kept the engine on the grounds
that it is "mathematically superior over tens of thousands of games, as proven in the Monte-Carlo
simulation." **That argument is circular**: a Monte-Carlo run that samples match outcomes from the
model's *own* probability grids only measures the model's self-consistency — it cannot validate the
model against reality. R4 ("optimized achieves higher total points than the baseline on historical
data") was therefore never honestly demonstrated.

The audit asked for the correct test: **per-match Kicktipp backtests on additional out-of-sample
folds (2014 + 2018), aggregated over ≥3 tournaments.** This is that test.

## Method

- **192 real matches** (64 each from WC2014, WC2018, WC2022).
- **No lookahead.** Lambdas come only from each team's **pre-tournament** Elo (the `PRE_WM20XX_ELO`
  snapshots already in `backtest_wm20XX.py`).
- **Scoreline convention:** official result, standard Kicktipp — 90 min for group games, after extra
  time for knockouts, **penalty-shootout goals excluded** (a shootout game is scored as the ET draw).
  Uniform across all three folds (`data/wc{2014,2018,2022}_results.csv`).
- **Both models start from identical Elo lambdas**, so the only difference is the engine's added
  probabilistic complexity:
  - **Baseline** — independent Poisson (ρ=0, α=0)
  - **Optimized** — Dixon-Coles (ρ=−0.05) + Negative Binomial (α=0.05)
- Each model emits its **EV-optimal 4/3/2 tip** and is scored against the real result.

Scorelines for 2014/2018 were compiled from the public match record; knockout rounds and a sample of
groups were cross-checked against Wikipedia per-group pages. **That cross-check corrected two
transcription errors** (2014 third place is NED 3–0 BRA, not a Belgium game; 2018 R16 is BEL 3–2 JPN,
not 2–2). 2022 was derived from `data/wc2022_full.csv` with the five shootout games converted from the
repo's penalty-inflated scores back to the ET draw.

## Result

| Fold | Baseline | Optimized | Δ (opt − base) |
|------|---------:|----------:|---------------:|
| WC2014 (64) | 104 | 104 | **0** |
| WC2018 (64) | 103 | 103 | **0** |
| WC2022 (64) | 84  | 84  | **0** |
| **Aggregate (192)** | **291** | **291** | **0** |

The optimized model produced the **exact same tip as the baseline on all 192 matches** — identical
points, identical exact/diff/tendency/miss breakdown.

This is not a bug. The grids genuinely differ (max |Δprob| ≈ 0.012 per cell; P(draw) rises ≈0.01
under Dixon-Coles + NB), but at the project's parameter values (ρ=−0.05, α=0.05) those perturbations
**never move the arg-max of the 4/3/2 expected value.** The EV-optimal tip is dominated by the
Elo-derived lambdas; the draw-correlation and overdispersion corrections reshape the tails without
flipping which scoreline maximizes expected Kicktipp points.

### Context layer (secondary probe, WC2022 group matches, 90-min results)

| Model | Points (48 matches) |
|-------|--------------------:|
| Optimized core (no context) | 59 |
| + context (travel / weather / host) | 61 (**+2**) |

+2 points over 48 matches is within noise, and it came by trading one exact hit for two
diff/tendency hits. Combined with the committed single-fold ablation on the original WC2022 setup
(context −3, NB −2, phase ±0 vs baseline), **every added feature is neutral-to-negative on real
Kicktipp points.**

## Verdict

**R4 is NOT met on real out-of-sample data.** Over three World Cups the added probabilistic
complexity yields **zero** Kicktipp-point advantage (Dixon-Coles + Negative Binomial are tip-neutral;
the context layer is marginal and within noise). The earlier "Monte-Carlo proves superiority"
defense is withdrawn as circular.

Important scope note: this measures **Kicktipp-point yield only**. It does **not** measure
probabilistic calibration (Brier score, log-loss), which a points metric structurally cannot capture
and under which Dixon-Coles + NB may still be better. So the honest statement is narrow and correct:
*the complexity is not justified by Kicktipp points; if it is justified at all, it is on calibration
grounds that this backtest does not test — and that should be measured explicitly rather than asserted.*

## Update (2026-06-06) — calibration measured and ρ/α tuned

Both follow-ups are now done. Harness: [`backtest_calibration_tuning.py`](../backtest_calibration_tuning.py);
raw output: [`backtest_calibration_tuning.txt`](backtest_calibration_tuning.txt). Same 192 matches.

### Calibration — is DC + NB better *calibrated* (the metric points can't see)?

Means over 192 matches, **lower is better**:

| metric | baseline (Poisson) | optimized (DC+NB) | Δ |
|--------|-------------------:|------------------:|---:|
| 1×2 Brier | 0.5713 | 0.5721 | **+0.0009 (worse)** |
| 1×2 RPS (order-aware) | 0.2023 | 0.2025 | **+0.0003 (worse)** |
| 1×2 log-loss | 0.9709 | 0.9716 | **+0.0007 (worse)** |
| exact-score log-loss | 2.9082 | 2.9085 | **+0.0004 (worse)** |

The calibration justification is **not supported**: a paired bootstrap over the 192 matches shows
every one of these deltas is **statistically indistinguishable from zero** (all 95% CIs span 0;
|t| < 0.7 — e.g. 1×2 log-loss Δ = +0.0007, 95% CI [−0.0033, +0.0045]). So DC+NB neither help nor hurt
calibration detectably — the earlier "a hair worse" reading was within sampling noise and is
withdrawn. **Caveat on power:** these metrics score the model against the single realized scoreline,
which is one noisy draw from the match. A lower-variance target — non-penalty xG — would give a far
more sensitive test (see note below); it has not been run.

### ρ/α grid search — does *any* setting beat baseline?

- **In-sample (overfit ceiling, all 192):** best-by-points is ρ=−0.10, **α=0.00** → 295 pts (+4 vs
  baseline 291). Note the optimum **turns the Negative Binomial off**; points fall monotonically as
  α rises (291→285). Best-by-RPS *is the baseline* (ρ=0, α=0) — no config improves calibration even
  with hindsight.
- **Leave-one-tournament-out CV (honest):** tuning on two World Cups and evaluating on the third
  → **287 pts (−4 vs baseline)** when tuned for points, and **RPS 0.2038 (+0.0015, worse)** when
  tuned for RPS. The in-sample +4 does not generalize — it was overfitting.

### Bottom line

On this 3-tournament out-of-sample evidence, **no setting of the existing ρ/α machinery beats the
independent-Poisson baseline — on points *or* calibration — and the Negative Binomial actively hurts
both.** The simplest Elo→Poisson→EV path is, by every measured criterion, at least as good as the
full engine and simpler. (Caveat: 3 folds is low-powered CV; the honest claim is "no benefit
demonstrable," not "benefit impossible.")

### Recommendation

1. **For tip generation, default to the baseline**: independent Poisson from Elo, **Negative Binomial
   off (α=0)**, Dixon-Coles ρ at most a small negative (it neither helps nor hurts within noise),
   context/phase off until they earn their place. This is a model *simplification* the evidence
   supports — not a tuning win to chase.
2. Keep DC/NB available as options, but stop asserting they improve results; they don't, here.
3. Treat the Monte-Carlo "champion probabilities" as a *scenario* tool, never as model validation.

### Higher-power test — non-penalty xG (StatsBomb open data, WC2018 + WC2022)

The scoreline is one noisy draw; **non-penalty xG (npxG)** is a much lower-variance estimate of each
team's true scoring rate, so it tests the λ estimate directly. Built `build_xg_data.py` from StatsBomb
open data (free; no 2014 coverage, so 2018+2022 = 128 matches); analysis in
[`backtest_xg_calibration.py`](../backtest_xg_calibration.py) → [`backtest_xg_calibration.txt`](backtest_xg_calibration.txt).

Routing first: **DC + Negative Binomial change the distribution's *shape*, not its *mean*** — npxG is
a mean estimate, so it's blind to them; the (null) exact-score log-loss above remains their test. **The
context layer changes λ (the mean)**, so npxG is the high-power test for it.

**Part 1 — base Elo→λ vs npxG (256 team-rows):**
- Real but moderate skill: npxG-**margin** correlation **+0.57** (per-team r +0.47). The Elo model does
  know who creates more chances — a signal the points/scoreline test was too coarse to show.
- But λ is **over-scaled**: bias +0.31 and MAE skill **−5.7% vs a naive constant** (it overstates
  favorites). Part of +0.31 is the goals-vs-npxG definitional offset; the rest is genuine over-
  confidence. **Actionable: recalibrate the Elo→λ mapping (`elo_baseline_goals` / `elo_scale_factor`).**

**Part 2 — does context move λ closer to npxG (WC2022)?**
- Per-team MAE: core 0.628 → context 0.596 (Δ −0.033, t=−3.1) — looks significant…
- …but on the **bias-invariant margin** (λ_a−λ_b vs npxg_a−npxg_b): core 0.849 → context 0.837
  (Δ −0.011, **t=−0.47, within chance**), and context slightly *lowers* the margin correlation
  (+0.569 → +0.553). **The per-team "win" was just context pulling the over-scaled λ down toward npxG,
  not real signal.** Context adds no detectable outcome information even on this low-variance target.

**Net:** the lower-variance target confirms the core λ has genuine (if moderate) skill and is over-
scaled — but does **not** rescue the context layer or DC/NB. Caveats: Russia/Qatar are mild, so this
tests travel+host, not the altitude/heat curves that matter for 2026; those need extreme-condition xG
(high-altitude qualifiers, hot venues) that StatsBomb open data does not cover. xG must come from a
real source — never fabricated.
