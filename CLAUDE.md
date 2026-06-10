# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FIFA World Cup 2026 prediction engine for a **Kicktipp** pool (4/3/2 scoring), plus a research-grade betting layer. It produces: EV-optimal score tips per match/matchday/KO-round, full-tournament Monte-Carlo answers to the pool's "Bonusfragen" (champion, semifinalists, top-scorer team, group winners), and a **paper-mode** derivative edge scanner. The living work program is `IMPLEMENTATION_PLAN.md` (step IDs S1–S24, gates G1/G2); current status lives in its "Status" section. Development happens on PR #1.

**Pool rules (verified — gate G1, `validation/POOL_RULES.md`):** 4/3/2 scoring where a non-exact draw tip on a draw result scores 3 (Kicktipp "Tordifferenz" rule — see `get_points`), and KO games are scored **"inkl. Elfmeterschießen"** → engine convention `kicktipp_ko_convention = "shootout_total"` (no draws; 90' + ET + every converted shootout kick summed into the final score).

## Environment

- Python 3.10+ via system `python3`. **Core prediction path is stdlib-only; the quant layer (`vectorized_mc.py`, `edge_scanner.py`, `backtest_harness.py`) requires numpy**: `pip install -r requirements.txt`. Ignore the stale bundled `venv/`.
- Polymarket/the-odds-api fetches need outbound network; sandboxed containers may 403 — all fetch paths degrade gracefully to Elo-only/skip.
- Env vars: `WM2026_BENCH=1` asserts the 100k-sim wall-clock budget (off by default — hardware-dependent); `WM2026_NO_MATRIX_CACHE=1` forces a cold matrix rebuild; `WM2026_NO_FRIENDLY_ELO=1` disables the post-friendlies Elo overlay.

## Commands

```bash
# Single match (CLI delegates to predict_single_match — same pipeline as batch/library)
python3 predictor.py --teamA Spain --teamB Qatar
python3 predictor.py --teamA Croatia --teamB Brazil --phase QF --json   # KO: shootout_total grid
python3 predictor.py --batch data/sample_matchday.csv

# Tip sheets (group matchdays / KO rounds; full stack: squad+injury Elo, xG form, context)
python3 matchday_tips.py --md 1 --simulations 1000 --seed 42 --output data/matchdayN_tips_vX.txt
python3 ko_tips.py --round R32 --matches "Spain vs Uruguay; France vs Germany" --fatigued "Croatia" --seed 42

# Tournament Monte Carlo / Bonusfragen
python3 tournament_bonusfragen.py --sims 100000 --seed 42 --output data/run.txt   # scalar engine
python3 vectorized_mc.py --sims 100000 --seed 42 --live-state data/live_state.json # vectorized engine
bash resim.sh                                  # daily pair (one seed, one odds snapshot)

# Edge scanner — PAPER MODE ONLY (real money is gated on G2)
python3 edge_scanner.py [--daemon] [--books manual_books.json] [--live-state data/live_state.json]

# Tournament ops (run after every final whistle — docs/LIVE_STATE.md)
python3 scripts/validate_live_state.py data/live_state.json     # typos are silent no-ops in the sims!
python3 scripts/log_predictions.py --kind matchday --file data/matchdayN_tips_vX.txt  # pre-register BEFORE kickoff
python3 tests/gate_check.py --bonus <bonus.txt> --matchday <tips.txt>

# Validation / backtests
python3 backtest_real_market.py            # gate G2 vs REAL closing odds — exits 2 until data/wcXXXX_odds.csv exist
python3 backtest_kicktipp_folds.py         # F9: 192 real matches, features vs baseline
python3 recalibrate_lambda.py              # LOTO calibration grid (λ tuning is FROZEN — see below)
python3 backtest_harness.py --tournament 2022   # FEATURE ABLATION vs synthetic self-market (NOT market alpha)
```

### Tests

```bash
python3 -m unittest discover tests          # 229 tests; ~4 min (vectorized matrix precompute dominates)
python3 -m unittest tests.test_ko_convention -v        # one module (dotted path)
```

CI (`.github/workflows/ci.yml`) runs the full suite + CLI smoke tests on every PR. Key suites: `test_lambda_points_floor` (calibration regression gate, ≥295/192 pts), `test_ko_convention` (G1 conventions + CLI≡library), `test_joint_kelly` (vs brute-force E[log-growth]), `test_edge_scanner` (offline, stub matrix), `test_vectorized_mc` (incl. cache roundtrip; builds the full matrix once in `setUpClass`). Several tests write temp CSVs into cwd.

## Architecture

Everything flows through one engine; **`predictor.predict_single_match(row) -> dict` is the single pipeline** for CLI, batch, matchday and KO tips (the CLI `main()` delegates to it — never add a second solving path).

**`predictor.py`** — the engine (sectioned by `# ===` headers): inlined 4/3/2 EV solver (`solve_optimal_tip_from_grid`, `get_points`); `WORLD_CUP_2026_TEAMS` Elo (+ `data/elo_2026_post_friendlies.json` overlay at import) and `TEAM_NAME_MAPPING` (always resolve names through it); Poisson/NB + Dixon-Coles (`generate_joint_grid`, renormalized); context layer (`get_adjusted_lambdas`: altitude, WBGT/PPDA heat, travel, host/fans, squad-value VORP); KO grids — `generate_ko_final_grid` (3-layer, shootout_total), `generate_ko_120_grid` (ties retained), selected by `CONSTANTS["kicktipp_ko_convention"]`; advancement probabilities always use the 3-layer model + `penalty_shootout_distribution`. `load_config` is type-preserving (string constants stay strings).

**Two tournament engines — KNOWN, documented divergence (plan S11, undecided):** `tournament_bonusfragen.py` (scalar; dynamic in-tournament Elo "Cinderella momentum", H2H tiebreakers) vs `vectorized_mc.py` (numpy; static λ with ET-fatigue carry-over states, lexsort tiebreakers without H2H, conditional MD3 dampening). **The vectorized engine is canonical for the scanner.** Do not "fix" one to match the other without the S11 canonical-dynamics decision. `vectorized_mc.build_matrix()` caches the ~4-min precompute to `data/matrix_cache/*.npz`, keyed by a SHA-256 fingerprint over every tensor input — **bump `CACHE_VERSION` whenever grid-generation logic changes upstream.**

**Tip generators:** `matchday_tips.py` (group MDs; flat ×0.87 MD3 trim — the only validated MD3 effect) and `ko_tips.py` (KO rounds; Dead-Legs fatigue via `--fatigued`). Both inject squad+injury Elo through the exception-safe `_elo_overrides` context manager and emit the provenance-headed format `scripts/log_predictions.py` parses.

**Betting layer (paper only):** `edge_scanner.py` — live Polymarket outright + 1X2 books (`odds_client.py`, liquidity-guarded), manual `--books` JSON for other derivatives; pure-model priors (never blend the market into a prior you difference against the market); Shin de-vig (`utils/math_utils.devig_shin` — canonical iterative, see `validation/SHIN_EVALUATION.md` for the fake-Shin post-mortem); **joint sizing per mutually exclusive book** (`kelly_mutually_exclusive`); per-leg/per-scan caps; JSONL ledger `scan_ledger/2026.jsonl`. Match-market model 1X2 always derives from `grid_90` (exchange 1X2 settles on 90', even for KO fixtures).

**Support:** `schedule_context.py` + `stadium_data.py` (schedule/travel/elevation/roofs), `utils/live_state.py` (+ `scripts/validate_live_state.py`), `squad_data.py` (note: fixed 65/35 XI/bench split → depth terms are collinear with squad value until real per-player data exists — plan S23).

## Validation truths (do not regress these)

- **F9 (`validation/F9_OUT_OF_SAMPLE.md`):** over 192 real matches, DC+NB+context+phase are points-neutral and calibration-neutral. The simple Elo→Poisson→EV path carries the performance.
- **λ calibration (`validation/points_recalibration.md`):** production `elo_baseline_goals=1.0` scores **299/192** (best tested; mechanism: low λ → EV-optimal `0:0` tips under the Tordifferenz rule). **λ tuning is frozen until post-tournament**; `tests/test_lambda_points_floor.py` enforces ≥295 — any deliberate calibration change must beat the floor or update it *with a measurement in that doc*. Points and calibration are different objectives (tipping optimizes points; the betting track needs calibration).
- **Gate G2 (`backtest_real_market.py`):** the scanner stays **paper-only** until the pre-registered real-odds verdict passes (model/blend beats the close on ≥2/3 tournaments AND flat-ROI 95% CI > 0). Never fabricate odds data; the script exits 2 until `data/wc{2014,2018,2022}_odds.csv` are supplied. `backtest_harness.py` is a feature ablation against a self-referential synthetic market — its dollar metrics are not market alpha.

## Conventions & gotchas

- **Provenance discipline.** Commit code BEFORE regenerating any published output; headers carry a `(dirty)` flag; `log_predictions.py` refuses dirty artifacts; `tests/gate_check.py` validates header pairs. Pre-register tips in `predictions_log/2026.jsonl` BEFORE kickoff — that log is the post-tournament evidence base (plan S21).
- **Harness-first.** Any change that can move a tip or probability re-runs the 192-match folds before merge (the λ episode proved intuition flips sign here).
- **`.gitignore` policy:** generated tip sheets / bonusfragen outputs / snapshots / `data/matrix_cache/` stay **local**; the JSONL logs (`predictions_log/`, `scan_ledger/`) are **committed**.
- **Change freeze from Jun 28** (first KO match): only P0 fixes merge, each with the full suite + points-floor + equivalence tests green.
- **One commit per plan step ID**, message referencing the step (S-number).
- **Open items:** S11 canonical-dynamics decision; S15 third-place match M103 (absent from both engines — Golden Boot misses its goals); G2 odds data; optional pool-history check of the shootout score representation (`validation/POOL_RULES.md`).
