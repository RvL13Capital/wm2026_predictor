# Gate G1 — Kicktipp Pool Scoring Rules (DECISION REQUIRED)

**Status:** ⏳ AWAITING USER VERIFICATION · **Deadline:** before R32 tips (Jun 27, 2026)
**Owner of the decision:** pool participant (read the pool's settings page)
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

## Default if unverified

Per `validation/F9_OUT_OF_SAMPLE.md`, the pre-agreed default is **`120min`**
(after extra time, shootout goals excluded). S12 implements all three modes
switchable via `config.json`.

## Verified answer

- **Pool rule:** _(fill in: 90min / 120min / shootout_total)_
- **Verified by / date:** _______
- **Evidence:** _(screenshot or settings text of the pool's "Spielwertung")_
