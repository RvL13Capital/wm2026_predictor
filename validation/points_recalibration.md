# λ Recalibration — Points Validation of the Production Config (S10)

**Date:** 2026-06-10 · **Closes:** review finding C1 / plan step S10
**Harness:** same 192 real matches as F9 (WC2014+2018+2022, pre-tournament Elo,
no lookahead, `data/wc20XX_results.csv`), EV-optimal 4/3/2 tips under the
**corrected Tordifferenz rule** (commit `14510ad`: non-exact draw tip on a draw
result = 3 points). Regression guard: `tests/test_lambda_points_floor.py`.

## Why this document exists

Commit `13da0cd` recalibrated `elo_baseline_goals` 1.35 → **1.00** "based on
npxG MAE". Two problems with that rationale:

1. **npxG is the wrong target for a goals model** — it excludes penalty goals,
   and `validation/backtest_xg_calibration.txt` itself annotates the +0.31 bias
   as *expected* for that reason. Minimizing MAE against npxG bakes a downward
   bias into predicted goal totals.
2. The value **1.00 was never inside its own validation harness**: the LOTO-CV
   grid in `recalibrate_lambda.py` was `BG = [1.15, 1.25, 1.35, 1.45]`
   (now extended to include 1.00).

The external code review predicted 1.00 would therefore *lose* Kicktipp points.
**Measurement reversed that prediction** — documented here so the decision
rests on the points objective, not on anyone's reasoning.

## Measurement (192 matches, EV-optimal tips, current scorer)

| Config (bg / sf / ρ / α) | Points | /match | exact | diff | tend | zero | per fold (14/18/22) |
|---|---:|---:|---:|---:|---:|---:|---|
| old default 1.35 / 1600 / −0.05 / 0.05 | 291 | 1.516 | 25 | 29 | 52 | 86 | 104 / 103 / 84 |
| **PRODUCTION 1.00 / 1600 / −0.05 / 0** | **299** | **1.557** | 25 | 33 | 50 | 84 | 113 / 102 / 84 |
| review-recommended 1.25 / 1600 / 0 / 0 | 289 | 1.505 | 24 | 29 | 53 | 86 | 105 / 101 / 83 |
| npxG-OLS fit 0.91 / 1856 / −0.05 / 0 | 253 | 1.318 | 18 | 31 | 44 | 99 | 94 / 81 / 78 |

Paired bootstrap (10,000 resamples), production vs old default:
**+8.1 points, 95% CI [−16, +33], P(production > old) = 0.73** — the best
tested config, though not statistically significant.

## Mechanism

Lower λ inflates model draw probability. Under the corrected Tordifferenz rule
a `0:0` tip pays 4 on 0:0 and **3 on any other draw**, so the EV-optimal tip
flips to `0:0` in near-even matchups — 28 of 192 tips under production vs ~0
under the old default. Real WC draw rates (~23–29% in group play) reward this.
Equivalently: a probabilistically *worse-calibrated* λ can produce *better*
tips, because the 4/3/2 payoff is asymmetric. This is also why the log-loss-
selected LOTO picks (bg 1.25, `validation/recalibration.txt`) disagree with the
points ranking — **calibration and points are different objectives**; tipping
optimizes points, the betting track (plan S16/S17) needs calibration.

## Decision

- `elo_baseline_goals = 1.00` **stays** — right value, originally wrong
  rationale, now points-validated.
- The extreme npxG-OLS config (0.91/1856) is **rejected** (−46 points): the
  review's core critique of npxG-targeting stands, even though 1.00 survived.
- **Further λ tuning is frozen until after the tournament** (the residual
  differences in the 1.0–1.35 band are inside the bootstrap noise; expected
  gain from more tuning ≈ 0 with high variance).
- `tests/test_lambda_points_floor.py` enforces a **≥ 295 floor** on the frozen
  192-match set so no future config edit can silently regress the points
  objective. If you change the calibration deliberately, you must beat the
  floor or update the test *with a measurement in this file*.
