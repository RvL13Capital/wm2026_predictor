# Gate G1 — Kicktipp Pool Scoring Rules (RESOLVED)

**Status:** ✅ VERIFIED 2026-06-10 — pool scores knockout games **"inkl. Elfmeterschießen"** → engine convention **`shootout_total`**
**Owner of the decision:** pool participant (answer given in session)
**Engineering dependency:** `IMPLEMENTATION_PLAN.md` step S12 (`kicktipp_ko_convention`)

## The question

In the Kicktipp pool settings ("Spielregeln" → "Spielwertung"), how are knockout
matches scored? Kicktipp offers three conventions:

| Setting | Meaning | Engine convention key |
|---|---|---|
| "nach 90 Minuten" | the 90-minute result counts; draws are real outcomes in KO games | `90min` |
| "nach Verlängerung" | the 120-minute result counts; a shootout game is scored as the ET draw | `120min` |
| (pool counts shootout) | shootout outcome folded into the result | `shootout_total` |

## Why it is decisive

The production KO grid (`predictor.generate_ko_final_grid`) currently models
`shootout_total`: it forces P(draw)=0 and **adds every converted shootout kick
to the final score**. Under the `120min` convention — which is what the repo's
own honest backtests use (`backtest_kicktipp_folds.py`, "penalty-shootout goals
are NOT counted (a shootout game is scored as the ET draw)") — roughly **12–15%
of KO matches end as scored draws that the current grid assigns probability
zero**, and any non-draw tip on those games is a guaranteed 0 points.
Historically ~4–5 of the 32 knockout matches per World Cup go to penalties.

## Verified answer

- **Pool rule:** `shootout_total` — "inkl. Elfmeterschießen"
- **Verified by / date:** pool participant, 2026-06-10 (in session)

## Consequences

1. **The production KO grid is the correct model for this pool.**
   `generate_ko_final_grid` (no draws; all goals from 90' + ET + every
   converted shootout kick summed into the final score) matches the pool's
   outcome space. `kicktipp_ko_convention` defaults to `shootout_total`.
2. **The predictor CLI's KO path was the wrong one for this pool** — it
   solved tips on the phase-adjusted 90-minute grid (draws retained,
   P(draw)≈34% on a close QF) instead of the 3-layer grid. Fixed by S12's
   CLI/library unification: `main()` now routes through
   `predict_single_match`, so there is exactly one KO code path.
3. The honest historical backtests (`backtest_kicktipp_folds.py`,
   F9) score shootout games as ET draws (`120min`) because that is how the
   historical datasets record results. This is a **dataset convention**, not
   the pool's; for like-for-like 2026 evaluation, S21 must score KO games
   under `shootout_total` using shootout-inflated actuals.

## Residual check (optional, 2 min)

Kicktipp's numeric representation under "inkl. Elfmeterschießen" is modeled
here as *all shootout goals added* (e.g. 2022 final: 3:3 + 4:2 pens → 7:5).
If the pool ran in 2022/2024, open one historical shootout game in the pool
and confirm the entered scoreline matches this convention. If the pool shows
a different representation (e.g. winner +1 goal), update
`kicktipp_ko_convention` handling in S12 accordingly.

---

## Draw scoring tier (RESOLVED 2026-06-24)

**Status:** ✅ VERIFIED 2026-06-24 — the goal-difference (3) tier **EXCLUDES draws**.
**Owner of the decision:** pool participant (answer given in session).

### The question
Under 4/3/2 scoring, when you tip a draw and the result is a draw but with the
**wrong score** (e.g. tip 0:0, result 1:1), do you get the goal-difference 3
(both GD = 0) or only the tendency 2?

### Verified answer
- **2 points** — the goal-difference tier does NOT apply to draws. A correct-but-
  inexact draw scores tendency (2). An exact draw still scores 4. Correct GD on a
  **non-draw** (e.g. tip 2:1, result 3:2) still scores 3.

### Consequences
1. `predictor.get_points` returns `pts_diff` only when `diff_actual == diff_tip
   and diff_actual != 0`; a non-exact draw-on-draw falls through to `pts_tend`.
2. The analytic solver `solve_optimal_tip_from_grid` draw branch uses
   `p_t*(pts_exact-pts_tend) + prob_draw*pts_tend` (no GD bonus on draws).
3. Production constants score **289/192** (was 299 under the old draw=3 rule);
   `tests/test_lambda_points_floor.py` floor re-baselined to 285.
4. EV-optimal tips shift: cagey-favorite games that previously optimized to `0:0`
   (to bank 3 on any draw) now flip to a decisive scoreline; only genuinely
   draw-likely games keep `0:0`. **λ re-optimization vs the corrected objective is
   a post-tournament item** (the low-λ→0:0 rationale is now weaker).
