# Implementation Plan — WC2026 Predictor (post-review)

**Date:** 2026-06-10 (T−1 day before the opening match) · **Basis:** code-level review at commit `b9d3397` plus new measurements (192-match λ backtest with paired bootstrap; KO split-brain demo Croatia–Brazil).
**Hard calendar (from `data/fifa_2026_schedule.json`):** Group Jun 11–27 · R32 Jun 28–Jul 3 · R16 Jul 4–7 · QF Jul 9–10 · SF Jul 14–15 · Third Jul 18 · Final Jul 19.

The plan is sequenced by **deadline, then dependency, then value**. Two decision gates (G1, G2) are user decisions; everything else is engineering.

---

## 0. Ground rules (apply to every step)

1. **Branch discipline.** All work on `claude/happy-brown-u5niwi` (or short-lived branches merged into it). One commit per step ID below; commit *before* regenerating any published output (the repo's own "phantom history" rule; `tests/gate_check.py` enforces headers).
2. **Harness-first for accuracy changes.** Any change that can move a tip or a probability re-runs the 192-match folds (`backtest_kicktipp_folds.py` / the S10 regression test) *before* merge. The λ measurement this week proved that reasoned intuition flips sign here; only the harness decides.
3. **Validated defaults.** Feature defaults follow the evidence on record: λ baseline 1.0 stays (points-validated 299/192); ρ=−0.05 stays (tip-neutral, harmless); NB α stays 0; context stays on for 2026 ops (unvalidated but the only chance to collect evidence — see S7/S21).
4. **Change freeze from Jun 28** (first KO match): only P0 bug fixes merge during the knockout phase, each with the regression suite green.

---

## 1. Timeline overview

| Phase | Window | Theme | Steps |
|---|---|---|---|
| 0 | **Today, Jun 10** | Tournament-critical correctness + ops bootstrap | S1–S9 |
| 1 | Jun 11–21 (MD1–MD2) | Consistency, KO cutover prep, caching | S10–S15, S19 |
| 2 | Jun 22–27 (MD3, pre-R32) | Betting decision gate, scanner (paper), live-state ops | S16–S18 |
| 3 | Jun 28–Jul 19 (KO) | Operations under change freeze | S20 |
| 4 | Jul 20+ | Strategic rebuild, evaluation, hygiene | S21–S24 |

Effort totals: Phase 0 ≈ 1 dev-day · Phase 1 ≈ 5–7 dev-days · Phase 2 ≈ 5–7 dev-days · Phase 3 ≈ 0.5 h/day ops · Phase 4 ≈ 3–6 elective weeks.

## Status (updated 2026-06-11)

- **Phase 0 — ✅ COMPLETE** (S1–S9 all merged; CI green on first run; MD1 tips pre-registered in `predictions_log/2026.jsonl` before the opener).
- **Gate G1 — ✅ RESOLVED**: pool scores KO games "inkl. Elfmeterschießen" → `shootout_total`.
- **Phase 1:** S10 ✅ · S12 ✅ · S13 ✅ · S14 ✅ · S19 ✅ · S15 open (optional) · **S11 ✅ except the dynamics decision**: flat MD3 ×0.87 in BOTH engines, drawing-of-lots tiebreaks (Elo removed), scalar ET model unified onto the engine constants, champion blend renormalized — only the deliberate scalar-dynamic-Elo vs vectorized-fatigue divergence (and H2H scalar-only) remains, pending the decision.
- **Gate G2 — ✅ DATA SUPPLIED / ❌ VERDICT NOT PASSED (2026-06-11):** all 192 real closing-odds rows filled free (2014 Beat-the-Bookie via Kaggle API; 2018/2022 football-data.co.uk `WorldCup2026.xlsx`), integrity gates green. Pre-registered verdict: model beats the close 1/3 folds (2014 only), ROI CI [−0.16,+0.43] ⊇ 0 → **scanner stays paper-only, now as a measurement, not a pending question.**
- **λ-freeze amendment (2026-06-11, pre-registered on opener day):** the blanket post-tournament λ freeze now carries ONE sanctioned exception — the group-stage checkpoint (`scripts/lambda_checkpoint.py`, run after MD3 / before the Jun-28 KO freeze). Band-conditional exact-hit tripwire (z ≤ −1.645, n ≥ 20) pre-registered in `validation/points_recalibration.md`; if it fires, recalibration is permitted under the standing floor/harness rules.
- **Ops:** MD1 tips AND the full Bonusfragen answer set pre-registered in `predictions_log/2026.jsonl` before the Jun 11 opener (clean provenance, seed 42). S24 partial: dead root scripts deleted.
- **Phase 2:** S17 ✅ (scanner: live Polymarket books + manual `--books` JSON, joint Kelly — brute-force-verified — per-leg/per-scan caps, paper ledger `scan_ledger/2026.jsonl`; live fetch untestable from the dev container, 403 by network policy) · S16 ✅ **harness** (`backtest_real_market.py`, pre-registered verdict logic + ET-draw settlement, plumbing-tested) — **gate G2 ✅ data supplied / ❌ verdict NOT PASSED (2026-06-11** — see the dedicated Status bullet below**)** · S16 era-clean ✅ (`backtest_harness.py` 2026-table leakage removed, report relabeled FEATURE ABLATION) · S18 ✅ (`docs/LIVE_STATE.md` + `utils/live_state.py` + `scripts/validate_live_state.py`).
- **S11 design note:** MD3-regime/ET-model/tiebreaker unification and the champion-blend renormalization remain straightforward, **but a strict scalar↔vectorized equivalence test is blocked by a deliberate model divergence**: the scalar engine evolves dynamic in-tournament Elo ("Cinderella momentum", K=30/40) while the vectorized engine instead carries ET-fatigue states. Unifying requires a decision on which dynamic is canonical (or porting fatigue into the scalar / dynamic Elo into the vectorized engine). Decide before implementing; until then the two engines are *documented* as different models and the vectorized engine is the one feeding `edge_scanner`.

---

## Phase 0 — Today (Jun 10), before the opener

### S1 · Fix the `m_id` live-state path (B1) — P0, ~1 h
- **Files:** `vectorized_mc.py :: _sample_match_cdf` (ln 396–449); `tests/test_vectorized_mc.py`.
- **Change:** initialize `val_a = val_b = None` at the top of each `unique_setups` iteration; in the `m_id` branch set `val_a, val_b = score[0], score[1]`; guard the apply-block with `if score is not None and val_a is not None`. Document the semantic: an `m_id`-keyed override forces that score for the slot pair in **bracket orientation** across all sims.
- **Tests (DoD):** (a) override keyed by `"M73"` yields exactly that score; (b) regression for stale-value reuse — one call containing two setups, the first name-keyed, the second `m_id`-keyed, asserts the second does **not** inherit the first's score.
- **Risk:** none; currently the path crashes or corrupts.

### S2 · `try/finally` around the global Elo mutation (B8) — P0, ~30 min
- **Files:** `matchday_tips.py` (ln 165–179).
- **Change:** wrap mutate → `predict_single_match` → restore in `try/finally` (restore in `finally`).
- **DoD:** test that injects an exception from a mocked `predict_single_match` and asserts the global table is restored.

### S3 · Honest dependencies & docs (B2, B9) — P0, ~30 min
- **Files:** `requirements.txt`, `README.md`, `predictor.py :: get_points` docstring (ln 88–94), `CLAUDE.md`.
- **Change:** declare `numpy` as a core dependency (keep pandas as the optional test extra); fix README — remove `file:///Users/...` links, correct "176 tests" → 178, annotate the 4.2 s claim (machine-specific; ~4 min one-off precompute; 14.6 s measured on the reference container), delete the "risk of ruin at 0.00 %" sentence; fix the `get_points` docstring to the implemented draw rule (non-exact draw-on-draw = `pts_diff`); sync CLAUDE.md's scoring note.
- **DoD:** fresh venv → `pip install -r requirements.txt` → `python3 -m unittest discover tests` collects 178.

### S4 · Hardware-independent test suite — P0, ~1 h
- **Files:** `tests/test_vectorized_mc.py :: test_performance_benchmark`.
- **Change:** gate the wall-clock assert behind `os.environ.get("WM2026_BENCH") == "1"`; always print sims/sec; keep the shape asserts unconditional.
- **DoD:** full suite green on this container (178/178).

### S5 · CI — P0, ~1–2 h
- **Files:** `.github/workflows/ci.yml` (new).
- **Change:** on push/PR — Python 3.11, `pip install -r requirements.txt`, `python -m unittest discover tests` (bench skipped), plus a CLI smoke test (`python3 predictor.py --teamA Spain --teamB Qatar --json`).
- **DoD:** green run on this branch. Rationale: both shipped failure classes (fake Shin green-tested; undeclared numpy) are exactly what CI catches.

### S6 · Deterministic daily resim — P0, ~30 min
- **Files:** `resim.sh`.
- **Change:** `SEED=$RANDOM` evaluated **once**, passed to both the txt and json runs so the pair is one simulation.
- **DoD:** both output headers carry the same seed.

### S7 · Pre-registered prediction log (start tonight) — P0, ~1–2 h
- **Files:** `scripts/log_predictions.py` (new), `predictions_log/2026.jsonl` (committed).
- **Change:** after generating any matchday/bonusfragen output, append JSONL: `{utc, commit(+dirty flag), seed, command, matchday/phase, per-match: tip, p_home/p_draw/p_away, λs}`. Entries are committed **before** kickoff.
- **DoD:** MD1 entry committed before the Jun 11 opener. This is the only mechanism that ever turns the altitude/heat/PPDA layer into evidence (no historical analog exists — repo's own note).

### S8 · **Gate G1 — verify the pool's KO scoring rule** — ✅ RESOLVED 2026-06-10
- **Verified answer:** the pool scores KO games **"inkl. Elfmeterschießen"** → convention **`shootout_total`** (`validation/POOL_RULES.md`).
- **Consequence:** the production 3-layer KO grid is the *correct* tipping target for this pool; S12's default flips from `120min` to `shootout_total`, and the urgent part of S12 becomes the **CLI/library unification** — the CLI's 90-minute KO path is the wrong grid for this pool.

### S9 · Clean-tree MD1 regeneration — P0, ~30 min (after S1–S3 are merged)
- **Action:** commit everything, regenerate MD1 tips (`matchday_tips.py --md 1 --seed <fixed>`), run `tests/gate_check.py`, log via S7, submit.
- **DoD:** provenance header cites a clean commit containing the generating code.

---

## Phase 1 — Jun 11–21 (group stage, MD1–MD2)

### S10 · Close the λ-calibration question (C1, revised by measurement) — P1, ~0.5 day
- **Files:** `validation/points_recalibration.md` (new), `recalibrate_lambda.py`, `tests/` (new regression).
- **Change:** (a) document the measured table — production (1.00, ρ−0.05): **299/192** vs old default 291, recommended-1.25 289, npxG-OLS 253; paired bootstrap +8.1, 95 % CI [−16, +33] — and the mechanism (28 EV-optimal `0:0` tips under the corrected draw rule); (b) add `1.00` to the `BG` grid in `recalibrate_lambda.py` so the production value is inside its own validation harness; (c) add a CI regression test: production config must score ≥ 295 on the frozen 192-match dataset, so no future config edit silently loses points.
- **Explicitly out of scope:** changing `config.json`. Production 1.0 stays; further λ tuning has <20 % chance of a significant gain and is banned until after the tournament.

### S11 · Engine consistency pass (B4–B6, B10) — P1, ~1–2 days
- **Files:** `vectorized_mc.py`, `tournament_bonusfragen.py`, `tests/test_engine_equivalence.py` (new).
- **Changes:**
  1. **One MD3 regime:** the validated flat ×0.87 (`validation/md3_regime_backtest.py`) replaces both conditional ×0.85 variants (`vectorized_mc.py` ln 230–235, 493–518; `tournament_bonusfragen.py :: simulate_group` ln 834–857). Removes the wrong "PTS==0 = eliminated" assumption (false in the 48-team format).
  2. **One ET model:** delete the rogue `1.2 + (elo−1700)/800` mapping in `_simulate_ko_match` (ln 1023–1030); sample ET goals from the engine's own layer (λ_adj × `et_time_fraction` × `et_fatigue_factor`).
  3. **One tiebreaker:** drop Elo from both engines; order = pts, GD, GF, head-to-head (scalar already has it; vectorized resolves exact (pts,gd,gf) ties — rare — by scalar fallback on the affected sims, or by lots with the deviation documented in both files).
  4. Renormalize the champion market blend (`vectorized_mc.py` ln 695–705); hoist the `squad_data` import out of the pair loop (ln 263).
- **DoD:** new cross-engine equivalence test — same Elo table and config, N = 20 000, scalar vs vectorized: max |Δ champion prob| < 1.5 pp, max |Δ stage-reach prob| < 2 pp. This test is the deliverable; it makes future divergence impossible to ship silently.

### S12 · KO convention switch + CLI/library unification (C2) — P1, ~2–3 days, **hard deadline Jun 27**
- **G1 resolved 2026-06-10:** the pool scores **`shootout_total`** ("inkl. Elfmeterschießen") — the production 3-layer KO grid is the *correct* tipping target. The urgent item is therefore #4 below: the **CLI's KO path uses the 90-minute grid (wrong for this pool)**.
- **Files:** `predictor.py` (`CONSTANTS`, `load_config`, `generate_ko_120_grid` new, `predict_single_match`, `main()`), `config.json`, tests.
- **Changes:**
  1. New constant `kicktipp_ko_convention ∈ {"90min", "120min", "shootout_total"}`; **default `"shootout_total"` per G1**. `load_config` becomes type-preserving (string defaults stay strings).
  2. `generate_ko_120_grid(config)`: Layers 1+2 of the existing 3-layer builder with ties **retained as draws** (no shootout-goal addition) — for `120min` pools and for the F9-convention historical harnesses. `"90min"` = the phase-adjusted `grid_90`.
  3. `predict_single_match` KO branch selects the tipping grid by convention. **Advancement probabilities** stay on the 3-layer grid + `_penalty_win_prob` — winner-probability and tip-target are explicitly separate concerns.
  4. **Unify CLI and library** (the fourth split-brain, demonstrated: CLI shows P(draw)=34 % where the library shows 0 % for the same QF): `main()` delegates to `predict_single_match` so there is exactly one KO code path — under G1 this *corrects the CLI*, not the library.
- **Tests (DoD):** convention matrix — `"shootout_total"` byte-identical to today's library path and zero draw mass; `"120min"` admits draw tips and caps per-side goals at 90'+ET (no shootout inflation); `"90min"` equals the phase-adjusted group-style solve; CLI and library agree for the same inputs (subprocess test).
- **Expected effect:** library tips unchanged (already correct); CLI KO tips now target the pool's actual outcome space; S21 evaluation gains the convention switch it needs to score 2026 like-for-like.

### S13 · Precomputer persistence — P1, ~1 day
- **Files:** `vectorized_mc.py :: MatrixPrecomputer` (+ `save`/`load`), callers (`edge_scanner.py`, `run_monte_carlo`).
- **Change:** serialize the tensors to `.npz` with a JSON sidecar keyed by hash of (Elo table incl. injury/squad adjustments, `CONSTANTS`, schedule, code version marker); load on hash match, rebuild otherwise.
- **DoD:** warm start < 10 s (vs ~4 min measured cold); identity test — cached arrays equal freshly built ones.

### S14 · KO-λ decontamination (B3) — P1, ~0.5 day
- **Files:** `vectorized_mc.py :: _build_baseline_tensors` / `_build_knockout_matrix`.
- **Change:** stop overwriting `lam_a/lam_b` with group-fixture context (ln 227–228); store group-match grids in their own structure so `_build_knockout_matrix` always reads the clean host-only baseline.
- **DoD:** unit test — for a same-group pair, KO-input λ equals the baseline λ within 1e-6 (today it embeds MD-specific rest/travel/market context for 4 of 6 fixtures per group).

### S15 · Third-place match M103 (B7) — P2 (optional), ~0.5 day
- **Change:** track SF losers in both engines; sample M103 with `THIRD` phase before M104; include its goals in Golden-Boot tallies.
- **DoD:** bracket test counts 32 KO fixtures incl. M103.

### S19 · KO tip generator — P1, ~1 day, deadline Jun 27
- **Files:** `ko_tips.py` (new; `matchday_tips.py` only covers GROUP).
- **Change:** per-round tip sheet (`--round R32 …`) through `predict_single_match` under the S12 convention, with schedule context, real fatigue states from logged ET results, and `--odds-snapshot` support; logs via S7.
- **DoD:** R32 sheet generated from a clean tree on Jun 27 evening, gate-checked, logged.

---

## Phase 2 — Jun 22–27 (MD3 window, pre-R32)

### S16 · **Gate G2 — real-odds historical backtest** — P1 for the *decision*, ~2–4 days
- **Files:** `data/wc{2014,2018,2022}_odds.csv` (new), `backtest_real_market.py` (new).
- **Data sourcing order:** (1) public Kaggle international-football odds datasets; (2) oddsportal archive export; (3) Betfair historical data; (4) fallback — manual entry of closing 1X2 for the 192 matches (~1 day, fully feasible).
- **Method:** Shin-devig the closes (`utils/math_utils.devig_shin` — verified correct); compare model vs market on log-loss / Brier / RPS; simulate flat-stake and 0.25-Kelly betting at the recorded prices with bootstrap CIs, per tournament fold. No 2026-era tables in historical folds (drop `SQUAD_VALUES` / 2022-informed `PENALTY_STRENGTH` there — the C5 leakage).
- **Pre-registered gate G2:** real-money use of the scanner is permitted **only if** model (or model-market blend) log-loss beats the market close on ≥ 2 of 3 tournaments **and** flat-stake ROI's 95 % CI excludes 0. Expected outcome: **fails (~75 % likely)** → betting stays paper-only; that outcome is recorded as a success (loss prevention), per `validation/SHIN_EVALUATION.md`'s own threat analysis.
- **Also:** retire `backtest_harness.py`'s dollar metrics — keep its Brier feature-ablation, delete or clearly relabel ROI/Sharpe against the synthetic self-market.

### S17 · Edge scanner productionization (paper mode) — P2, ~2–3 days
- **Files:** `edge_scanner.py`, `utils/` (joint Kelly), `scan_ledger/` (new).
- **Changes:**
  1. Replace `_fetch_market_books` static books with `PolymarketClient` feeds (outrights via `get_wc_winner_probabilities`; per-match 1X2 via `get_match_1x2_probabilities`); drop synthetic reach/group books unless real lines exist.
  2. **Joint Kelly for mutually exclusive books** (the one wrong piece of betting math): standard simultaneous-Kelly — sort legs by `p·o` descending; include leg *k* while `p_k·o_k > R` where `R = (1 − Σ_inc p_i) / (1 − Σ_inc 1/o_i)`; stake `f_i = p_i − R/o_i`; then apply the 0.25 fraction. Unit-test against a brute-force optimizer on 3-outcome cases.
  3. Risk controls: per-market cap ≤ 5 % bankroll, global open exposure ≤ 20 %, liquidity floor reusing `THIN_LIQUIDITY`.
  4. Persistence: JSONL scan ledger (timestamp, market, leg, p_mod, p_fair, odds, stake, action) + paper P&L tracker.
- **DoD:** daemon runs 24 h against live Polymarket without exception; ledger complete; **no real-money pathway exists unless G2 passed.**

### S18 · Live-state ops runbook — P2, ~0.5 day
- **Files:** `docs/LIVE_STATE.md` (new), `scripts/validate_live_state.py` (new).
- **Change:** schema (`{"Mexico vs South Africa": [2,0]}` and `m_id` form), update cadence (after each FT), validator that rejects unknown team names/ids (today's failure mode is silent); wire into resim and the scanner.

---

## Phase 3 — Jun 28–Jul 19 (knockout): operate under change freeze

### S20 · Daily operations loop — ~0.5 h/day
- After each round: update `live_state.json` (S18) → `resim.sh` (cached precompute, S13) → KO tips for the next round (S19) → log (S7) → paper scan (S17).
- Record real ET/shootout occurrences to drive fatigue states (the mechanism `backtest_harness.py :: went_to_extra_time_real` uses, now fed live).
- Only P0 hotfixes merge; each re-runs the full suite + S10 regression + S11 equivalence test.

---

## Phase 4 — Jul 20+ (post-tournament, elective)

### S21 · Tournament post-mortem & physio-layer evidence — ~3 days
Score every S7-logged prediction: points by phase, reliability curves, and the first-ever conditional test of the 2026-specific layer (hot/altitude/long-travel matches vs others — Brier deltas with CIs). Publish `validation/WC2026_POSTMORTEM.md`. This dataset is the project's most valuable asset for 2030.

### S22 · Fitted attack/defense Dixon-Coles pipeline — ~2–3 weeks, behind a research flag
MLE attack/defense ratings with time-decay on ~5 years of internationals; market-anchored absolute totals (reuse `_fit_poisson_mean`). Promote only if it beats the Elo-only core on the (now 192 + 2026) folds **and** on calibration. Prior: ~30 % chance it helps points, ~60 % it helps calibration.

### S23 · Real per-player squad data, or delete the depth terms — ~1–2 weeks
As shipped, `squad_data.py`'s fixed 65/35 split makes every depth term collinear with squad value (information-free). Either ingest real XI/bench valuations and lineups, or collapse the terms into the single squad-value coefficient they mathematically are. **Scope extended 2026-06-11 (`validation/SQUAD_VALUE_AGE_BIAS.md`):** age-normalize market values before the value→Elo/λ mapping and replace the `change_pct` "form" term with a results-based signal — value *change* is age-curve-contaminated (Ecuador's overlay is 65% form term, Canada's 100%; Croatia's value-Elo is erased by aging depreciation). Measured impact today is bounded (no group-winner flips, ≤±10% relative champion-prob; Croatia −21%), so post-tournament work, not a freeze exception.

### S24 · Packaging & hygiene — ~2–3 days
`pyproject.toml`; delete dead root scripts (`verify_solver_equivalence.py`, `test_tournament_sim.py`, `temp_verify.py`, `test_wiki.py`, `fetch_github.py`); rewrite `CLAUDE.md`/`PROJECT.md` to the current architecture; `logging` instead of prints; fix the Elo-table rank anomalies (Iran/Czechia, Haiti/Ghana); type-check pass on the core modules.

---

## Dependencies & gates

```
S1..S7 (independent) ──► S9 (MD1 ships)
S8 (G1: pool rule) ─────► S12 (KO convention) ──► S19 (KO tips, ≤ Jun 27)
S11 (equivalence test) ─► change freeze safety (Phase 3)
S13 (cache) ────────────► S17 (scanner latency), S20 (daily ops)
S16 (G2: real-odds gate) ► real-money decision for S17 (default: paper only)
S7 (logging) ───────────► S21 (post-mortem) ──► S22/S23 promotion decisions
```

## Risk register (top 5)

| Risk | Likelihood | Mitigation |
|---|---|---|
| ~~G1 unanswered before Jun 27~~ → **resolved 2026-06-10**: pool = `shootout_total` | — | Residual: confirm Kicktipp's numeric representation against a historical shootout game in the pool (see `validation/POOL_RULES.md`) |
| Polymarket schema drift breaks the feed mid-tournament | Medium | `_extract_game_1x2` already defensive; S17 adds schema-mismatch alerts + scanner degrades to model-only with a loud warning |
| Mid-tournament hotfix breaks determinism/equivalence | Low–Med | Change freeze + S10/S11 tests are merge-blocking in CI |
| Real-odds data for 2014 unobtainable | Low | 2018+2022 (128 matches) suffice for G2; manual-entry fallback budgeted |
| Live-state typo silently corrupts a resim | Medium | S18 validator rejects unknown names; S1 closes the silent-reuse path |

## Definition of success per phase

- **Phase 0:** suite 178/178 green in CI; MD1 tips shipped from a clean commit with a logged, pre-registered record; the in-play path cannot crash.
- **Phase 1:** one engine behavior (equivalence test green); KO tips target the verified scoring convention; warm restarts in seconds; production λ choice is inside its own validation harness with a points floor in CI.
- **Phase 2:** a pre-registered, real-market verdict on alpha (either answer is success); a scanner that runs live in paper mode with correct joint sizing and a complete ledger.
- **Phase 3:** every round tipped on time, logged, reproducible; zero unreviewed changes.
- **Phase 4:** a scored 2026 evidence base; complexity that survived it promoted, the rest deleted.
