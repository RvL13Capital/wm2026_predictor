# Project: World Cup 2026 Prediction Engine & Quant Suite

**Goal:** maximize Kicktipp points in a real pool (4/3/2 scoring, KO games scored
"inkl. Elfmeterschießen" — gate G1, `validation/POOL_RULES.md`), answer the pool's
Bonusfragen via tournament Monte Carlo, and — strictly evidence-gated — scan
derivative markets for edge. The living work program is
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) (steps S1–S24, gates G1/G2);
the audit trail lives in [`validation/`](validation/) and the forensic/review
documents. Tournament: Jun 11 – Jul 19, 2026.

## Architecture (current)

- **`predictor.py`** — the engine and single pipeline (`predict_single_match`):
  Elo→λ (production `elo_baseline_goals=1.0`, points-validated), Poisson/NB +
  Dixon-Coles grid, context layer (altitude/WBGT·PPDA/travel/host/squad), KO
  grids per scoring convention (`shootout_total` default; `120min`/`90min`
  implemented), inlined 4/3/2 EV solver. CLI, batch, and tip generators all
  delegate here — there is exactly one solving path.
- **Tournament engines:** `tournament_bonusfragen.py` (scalar; dynamic
  in-tournament Elo) and `vectorized_mc.py` (numpy; ET-fatigue carry-over,
  bitmask third-place routing, fingerprint-keyed matrix cache). Their dynamics
  deliberately differ — unification awaits the S11 canonical-dynamics decision;
  the vectorized engine is canonical for the scanner.
- **Deliverable generators:** `matchday_tips.py` (group MDs), `ko_tips.py`
  (KO rounds, Dead-Legs fatigue), both with provenance headers consumed by
  `scripts/log_predictions.py` (pre-registered prediction log).
- **Betting layer (paper-only until G2):** `edge_scanner.py` — live Polymarket
  books, Shin de-vig (`utils/math_utils`), **joint** Kelly per mutually
  exclusive book, per-leg/per-scan caps, JSONL scan ledger.
- **Ops:** `resim.sh` (deterministic daily pair), `docs/LIVE_STATE.md` +
  `scripts/validate_live_state.py`, CI in `.github/workflows/ci.yml`
  (229 tests).

## Milestones

| # | Name | Status / evidence |
|---|------|-------------------|
| 1 | E2E Testing Track (Tiers 1–4, `TEST_INFRA.md`) | DONE (Conv: 4606a3e4) |
| 2 | Advanced Probability Engine (NB + Dixon-Coles + context) | DONE (Conv: 4f3269e2 / 5e253a0d) |
| 3 | Kicktipp Solver (4/3/2 EV maximization) | DONE (Conv: 5ec5b1fc) |
| 4 | Backtesting Suite (WC2022 vs baseline) | DONE (Conv: 1c17fbc0) — verdict superseded by F9, see R4 below |
| 5 | E2E Validation & Adversarial Hardening | DONE (Conv: 1ff89a9c) |
| 6 | In-Play Oracle & Path-Dependent Fatigue | DONE (Conv: f91688cd) — `m_id` override path fixed in S1 |
| 7 | Walk-Forward Harness vs Synthetic Elo Market | DONE (Conv: f91688cd) — relabeled FEATURE ABLATION in S16 (self-referential baseline; not market alpha) |
| 8 | Forensic audits & honest validation (F9, Shin post-mortem, λ recalibration) | DONE 2026-06-06..10 — `FORENSIC_RECHECK_V4_2026-06-06.md`, `validation/F9_OUT_OF_SAMPLE.md`, `validation/SHIN_EVALUATION.md`, `validation/points_recalibration.md` |
| 9 | External code review → phased plan | DONE 2026-06-10 — `IMPLEMENTATION_PLAN.md`, PR #1 |
| 10 | **Phase 0** (S1–S9): tournament-critical fixes, CI, deterministic resim, pre-registered MD1 tips | DONE 2026-06-10, before the opener |
| 11 | **Phase 1** (S10, S12–S14, S19): λ points-floor gate, KO convention + CLI/library unification, matrix cache, KO-λ decontamination, `ko_tips.py` | DONE 2026-06-10 — S15 optional open; S11 awaiting canonical-dynamics decision |
| 12 | **Phase 2** (S16–S18): G2 real-odds harness, paper scanner with joint Kelly + caps + ledger, live-state validator/runbook | DONE 2026-06-10 — **gate G2 awaiting `data/wc{2014,2018,2022}_odds.csv`** |
| 13 | Phase 3 (S20): KO-stage operations under change freeze (from Jun 28) | PENDING — daily loop per `docs/LIVE_STATE.md` |
| 14 | Phase 4 (S21–S24): post-tournament evaluation, fitted DC pipeline, per-player data, packaging | PENDING (elective, after Jul 19) |

## Requirements — honest status

- **R1 Advanced probability engine** — implemented (NB2, standard DC-1997 τ with
  NB generalization, renormalized grids). **Evidence verdict (F9): the added
  complexity is points- and calibration-neutral over 192 real matches**; it
  remains available behind defaults and is being evidence-tested live in 2026.
- **R2 Context factors** — implemented (altitude curves, WBGT with PPDA
  vulnerability and roof overrides, travel/rest/timezone, host/fans, squad
  value). Evidence: no detectable outcome signal on the bias-invariant margin
  (`validation/backtest_xg_calibration.txt`); the 2026 prediction log (S7/S21)
  is the first real test of the heat/altitude curves.
- **R3 Kicktipp solver** — implemented and exact, including the Tordifferenz
  draw rule (non-exact draw tip on a draw = 3). EV decomposition is O(N²+T²).
- **R4 "Optimized beats baseline on historical points"** — **NOT MET** (F9:
  291–291 over 192 matches; circular MC defense withdrawn). What *did* pay:
  the λ recalibration to 1.0 (**299/192**, `validation/points_recalibration.md`),
  now protected by a CI points floor (≥295). λ tuning frozen until
  post-tournament.
- **R5 In-play oracle & fatigue** — implemented; the match-id override path was
  broken (crash/stale reuse) until S1; live-state files are now validated
  before use (S18).
- **R6 Market backtest** — the synthetic-market harness is a feature ablation
  (era-cleaned of 2026 tables in S16). The real test is
  `backtest_real_market.py` with a **pre-registered verdict**: real-money use
  only if model/blend log-loss beats the de-vigged close on ≥2/3 tournaments
  AND flat-ROI 95% CI > 0. Until then the scanner is paper-only by
  construction (no execution path exists).

## Decision log / open gates

| Item | Status |
|---|---|
| **G1** pool KO scoring rule | ✅ RESOLVED 2026-06-10: `shootout_total` ("inkl. Elfmeterschießen"). Residual: 2-min check of a historical shootout game's entered scoreline (`validation/POOL_RULES.md`) |
| **G2** real-odds alpha gate | ⏳ AWAITING DATA (`data/wc{2014,2018,2022}_odds.csv`); expected outcome per plan: NOT PASSED → paper-only, recorded as loss prevention |
| **S11** canonical in-tournament dynamics | ⏳ DECISION NEEDED: scalar dynamic Elo vs vectorized fatigue carry-over (then unify MD3 regime, ET model, tiebreakers + equivalence test) |
| λ calibration | 🔒 FROZEN at 1.0 until post-tournament (points floor in CI) |
| S15 third-place match M103 | Optional — absent from both engines (Golden Boot misses its goals) |

## Operations (tournament window)

After every final whistle: update `data/live_state.json` → `scripts/validate_live_state.py` →
re-sim (`resim.sh` / `vectorized_mc.py --live-state`) → next tips (`matchday_tips.py` /
`ko_tips.py`) → `scripts/log_predictions.py` **before kickoff** → paper scan
(`edge_scanner.py`). Change freeze from Jun 28: P0 fixes only, full suite green.
