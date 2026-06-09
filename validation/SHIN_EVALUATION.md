# Shin's Method — Integrity Evaluation & Hotfix Post-Mortem

**Date:** 2026-06-09 · **Scope:** de-vig layer (`utils/math_utils.py`) and the market→edge path (`edge_scanner.py`)
**Commit under review:** `c461b30 "feat: implement analytical Shin de-vigging and Bayesian blending"`
**Companion evidence:** `F9_OUT_OF_SAMPLE.md` (why added complexity has not paid off on the real objective)

**Kurzfazit (DE):** Das ausgelieferte „Shin's Method" war *nicht* Shins Schätzer, sondern eine quadratische
Ersatzformel; das gemeldete `z` („Insider-Anteil") war bedeutungslos (~0.90 statt real ~0.03). Der
Edge-Scanner verglich faire Modell-Wahrscheinlichkeiten gegen **vig-behaftete** Marktquoten. Beides ist mit
diesem Hotfix behoben (kanonischer iterativer Shin + Buch-De-Vig). Der echte Genauigkeitshebel bleibt die
**Elo→λ-Rekalibrierung** (siehe F9), nicht die De-Vig-Politur.

---

## Verdict

The intent — de-vig market odds before trusting them — is correct practice. The **implementation was not**,
and it did not move the project toward a more accurate system on any measured objective. Three findings,
then the SWOT, the anti-patterns it flags, and the hotfix that was applied.

---

## Finding 1 — The shipped estimator was not Shin's Method

`utils/math_utils.py` used a home-made quadratic map

```
z   = (Σπ² − 1) / (Σπ² − Σπ)
p_i = (1 − z)·π_i² + z·π_i        # then renormalised
```

This is **not** Shin (1993). The genuine estimator inverts the square-root model
`p_i = (√(z² + 4(1−z)·π_i²/B) − z) / (2(1−z))` with `z` solved so `Σp_i = 1`. There is **no closed form for
3+ outcomes** — it must be solved iteratively — so the commit's "analytical / exact analytic solution"
label was false. Tell-tale: at `z=0` genuine Shin reduces to proportional normalisation (`p_i ∝ π_i`); the
quadratic reduces to `p_i ∝ π_i²`, a different transform.

The probabilities were *roughly* right at small overround, but the reported `z` — sold as the headline
feature ("estimated proportion of insider trading") — was garbage. Verified numerically against an
independent bisection solver:

| 1X2 odds | booksum | shipped `z` (quadratic) | **canonical Shin `z`** | shipped P(home) | canonical P(home) |
|---|---:|---:|---:|---:|---:|
| 2.50 / 3.20 / 2.80 | 1.0696 | 0.898 | **0.035** | 0.3756 | 0.3760 |
| 1.20 / 7.00 / 15.00 | 1.0429 | 0.868 | **0.022** | 0.8149 | 0.8139 |
| 1.80 / 3.60 / 4.50 | 1.0556 | 0.910 | **0.028** | 0.5334 | 0.5343 |

A `z` of ~0.9 implies "90 % of volume is insiders" on a routine football line — nonsensical. The output
probabilities sat within 0.1–0.4 pp of canonical Shin (so downstream damage was small), but the parameter
was meaningless and the method mislabelled. **The correct iterative solver already existed in
`scratch/test_shin.py`** — the right code was written, then the wrong code shipped.

## Finding 2 — Shin sat where it barely matters, and was absent where it counts

- **Kicktipp path (`predict_single_match`)**: `market_z` is computed then only stored in the result dict
  (`predictor.py:2100`); nothing consumes it. Per F9, sub-1 pp probability perturbations **never move the
  EV-optimal 4/3/2 tip**. With the default `market_weight=0.8` and the usual absence of `volume`/`time_to_kickoff`,
  the "Bayesian precision-weighted blend" silently collapses to a fixed 80/20 linear blend. Net: the de-vig
  *method* is ≈ irrelevant to the tips.
- **Betting path (`edge_scanner`)**: computed `edge = p_mod − 1/decimal_odds` — a fair model probability minus
  a **vig-inflated** implied probability, never de-vigged. The README claimed the scanner used Shin's Method;
  the code never called it. This biases every edge by the overround.
- **Default live source (Polymarket)** bypasses `strip_vig_shin` entirely (tournament-winner odds →
  sqrt Bradley-Terry → fixed `draw_factor=0.27`).

## Finding 3 — Unvalidated, and the "validation" was circular

There was no backtest of de-vig vs. plain normalisation on *any* objective. `backtest_harness.py` evaluates the
engine against a **"Synthetic Elo Market" = vanilla Elo + 5 % overround** — the same self-referential benchmark
F9 already withdrew as circular. A Brier Skill Score against a market synthesised from the engine's own Elo
measures self-consistency, not real-world alpha.

---

## SWOT

**Strengths** — Correct instinct (naive normalisation carries favourite–longshot bias; Shin is legitimate,
well-cited). Output probabilities acceptable at low vig; zero-vig fallback correct. Clean, stdlib-only,
deterministic, tested. The correct solver already lived in `scratch/`. Log-space precision-weighted blending
(trust the market more with higher volume / closer to kickoff) is conceptually sound.

**Weaknesses** — Not Shin (wrong functional form); `z` meaningless; docstring + commit + README mislabelled →
false confidence; tests asserted only "sum = 1" and the code's own arithmetic, never correctness vs. canonical
Shin. `edge_scanner` did not de-vig. Polymarket bypasses Shin. Bayesian-blend constants (α, β, γ) unvalidated and
usually dormant.

**Opportunities** — Promote the canonical solver from `scratch/` (done). Redirect effort to the real accuracy
lever F9 pinpointed: the **over-scaled Elo→λ** mapping. De-vig the wide multi-outcome outright/group books
correctly (where overround is largest and matters most).

**Threats** — False confidence: trusting `z` as a "late-money / insider" signal when it is noise. The whole
market/edge stack rests on circular validation; "0.00 % risk of ruin" holds only if the model probabilities are
correct — the unproven premise. Scope creep enlarges the money-losing surface.

---

## Anti-patterns this episode marks (permanent flags)

1. **Mathematical convenience over correctness.** A "closed-form / analytic" label was attached to a home-made
   quadratic because the real estimator required iteration — while the correct iterative solver sat unused in
   `scratch/`. Convenience beat correctness, and tests + docstrings locked the error in.
2. **Circular validation.** Testing the engine against a "market" synthesised from the engine's own Elo. Already
   called out and withdrawn in F9; it reappeared in `backtest_harness`. Self-consistency is not accuracy.
3. **Scope creep.** `ORIGINAL_REQUEST.md` is a Kicktipp 4/3/2 EV maximiser. The suite drifted into "institutional
   quant trading" (Kelly sizing, exchange scanner, "0.00 % risk of ruin") — precisely the surface where the
   de-vig had to be right, and where it was both wrong and unused.

---

## Hotfix applied (2026-06-09)

- **Fix A — `utils/math_utils.py`:** quadratic removed; canonical Shin (Newton–Raphson + bisection fallback)
  ported from `scratch/test_shin.py`. `strip_vig_shin((π_h,π_d,π_a)) → ((p_h,p_d,p_a), z)` signature preserved;
  added N-way `devig_book(implied, method="shin"|"basic")`. Tests rewritten to assert **canonical** values
  (`z≈0.0348`, `P=0.3760/0.2900/0.3339`) plus a regression guard requiring `z<0.10` on normal odds — locking out
  the old `z≈0.90`.
- **Fix B — `edge_scanner.py`:** every market book is de-vigged before differencing; **`edge = p_mod −
  p_mkt_devigged`**. Flagging uses the de-vigged edge; Kelly/EV sizing uses the *raw* decimal odds (what actually
  pays). Mock lines restructured into complete, internally-consistent books (Field buckets for multinomial /
  per-group, two-sided binary reach lines) and clearly labelled ILLUSTRATIVE STATIC pending a live feed.
- **Incidental:** `vectorized_mc.py` was missing `from typing import Tuple` — an import-breaking `NameError` that
  prevented the scanner from importing at all. Added the import.
- **Docs:** removed the false "analytic / exact" Shin claims from `README.md` and docstrings.

## Status after fix

- `tests/test_shin_bayesian.py`: **12/12 green** against canonical values (was 10/10 green against the *wrong*
  behaviour).
- `edge_scanner` de-vig verified: vig removed before differencing (e.g. Reach-R16 Spain 87.0 % → 84.5 %; outright
  longshots shaded down; Field excluded from edges).
- **Known/open (not in this scope):** `vectorized_mc`'s 100k-sim path is heavy — a full end-to-end scan is slow;
  it is not part of the unittest suite. Flagged, not fixed here.

## Next — the real accuracy lever (Step C)

F9's non-penalty-xG analysis shows the core Elo→λ has genuine margin skill (npxG-margin r ≈ +0.57) but is
**over-scaled** (bias +0.31; MAE −5.7 % vs. a naive constant — it overstates favourites). De-vig sophistication
does not move Kicktipp points; **recalibrating `elo_baseline_goals` / `elo_scale_factor` against historical npxG
does.** That is the "zielgenaueres System," and it is the next task.
