# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FIFA World Cup 2026 prediction engine that computes mathematically optimal **Kicktipp** score tips (4/3/2 scoring) for individual matches, full-tournament Monte Carlo outcomes ("Bonusfragen" / prop questions), and per-matchday tip sheets. The core prediction path is pure Python standard library; the vectorized/quant layer (`vectorized_mc.py`, `edge_scanner.py`, `backtest_harness.py`) **requires numpy** (`pip install -r requirements.txt`). Current work program: `IMPLEMENTATION_PLAN.md`.

## Environment

- Runs on any Python 3.10+; verified on system `python3` (3.14). Invoke modules directly with `python3`.
- The bundled `venv/` was created under a previous path (`~/.gemini/antigravity/scratch/...`) and is stale — don't rely on it; system `python3` works because the code is stdlib-only.
- No `.gitignore` exists. `__pycache__/*.pyc` are committed and `temp_*.csv` / `tmp*.csv` (test artifacts written to cwd) accumulate — ignore them as noise; don't treat them as source.

## Commands

```bash
# Single-match prediction (per-match CLI; --help lists ~40 context flags)
python3 predictor.py --teamA Spain --teamB Qatar
python3 predictor.py --teamA France --teamB Brazil --phase FINAL --json
python3 predictor.py --batch data/sample_matchday.csv          # batch over a CSV
python3 predictor.py --teamA X --teamB Y --config config.json  # override model constants

# Full-tournament Monte Carlo + Bonusfragen (champion, top scorer, etc.)
python3 tournament_bonusfragen.py --sims 100000 --seed 42 --output data/run.txt
python3 tournament_bonusfragen.py --sims 10000 --odds-snapshot data/polymarket_snapshot_20260605_1230.json  # reproducible market blend
python3 tournament_bonusfragen.py --sims 10000 --fetch-odds    # live Polymarket fetch

# Per-matchday tip sheet (uses the FULL stack — see Architecture)
python3 matchday_tips.py --md 1 --simulations 1000 --seed 42 --output data/matchday1_tips.txt

# Backtest optimized vs. baseline on historical results; ablation flags isolate each feature
python3 backtest.py --csv data/wc2022.csv --details
python3 backtest.py --csv data/wc2022.csv --no-context --no-nb --no-phase --no-dc
python3 backtest_wm2018.py    # standalone historical folds (2014/2018/2022 each self-contained)

# Daily regeneration pipeline (fetch odds → 100k sims → save txt+json with provenance header)
bash resim.sh
```

### Tests

```bash
python3 tests/run_e2e.py                                   # discovers & runs ALL tests/test_*.py
python3 -m unittest tests.test_tier1_feature_coverage -v   # one module (note: dotted path, not slash)
python3 -m unittest tests.test_v4_features.SomeClass.test_x  # one test
python3 tests/gate_check.py <output_file>                  # validate provenance header + champion-prob stability of a generated output
```

- Test suite is stdlib `unittest` plus numpy for `test_vectorized_mc`. Tiered: `test_tier1`..`test_tier4` (feature → boundary → cross-feature → real-world), plus `test_v4_features`, `test_adversarial_*`, `test_solver`, `test_predictor`, `test_shin_bayesian`, `test_vectorized_mc`, `test_matchday_elo_restore`.
- The suite is green (180+ tests). The 100k-sim wall-clock budget in `test_vectorized_mc` is only asserted when `WM2026_BENCH=1` (it is hardware-dependent). Several test files write temp CSVs into the working directory.

## Architecture

Three executable layers built on one engine. Data flows **engine → solver → simulators**; everything imports `predictor`.

**`predictor.py`** — the engine and single source of truth (~2400 lines, sectioned by `# ===` headers):
1. **Inlined solver** (`solve_optimal_tip_from_grid`, `get_points`) — `solver.py` was deleted and folded in here. Do **not** recreate `solver.py`; edit predictor's section 1.
2. **Team data** — `WORLD_CUP_2026_TEAMS` (Elo + FIFA rank, English keys are canonical) and `TEAM_NAME_MAPPING` (German/alt spellings → canonical). Always resolve names through the mapping.
3. **Distributions** — Poisson, Negative Binomial (overdispersion), Dixon-Coles low-score correlation (`get_dixon_coles_adjustment`, `generate_joint_grid`).
4. **Contextual factors** — `get_adjusted_lambdas` composes altitude (`calculate_altitude_factor`), heat/humidity (`calculate_wbgt`/`calculate_thermal_factor`), travel/rest/timezone (`calculate_travel_penalty`), and host/fan support (`calculate_context_adjustments`) into adjusted λs.
5. **KO/penalty** — `generate_ko_final_grid`, `penalty_shootout_distribution` (a state-machine shootout model).
6. **Pipeline** — `predict_single_match(row: dict) -> dict` runs the whole chain and returns the grid + optimal tip + EV; `run_batch_prediction` maps it over a CSV.

**Interface contract:** the engine emits a joint score grid (`max_goals`×`max_goals`, default 12); the solver picks the tip `(t_a, t_b)` maximizing `EV = 4·P(exact) + 3·P(diff) + 2·P(tendency)`. **Scoring nuance** (`get_points`): exact = 4; correct goal-difference = 3, and per the Kicktipp "Tordifferenz" rule a non-exact draw tip on a draw result counts as correct difference (3, not 2); correct tendency = 2; else 0.

**`tournament_bonusfragen.py`** — Monte Carlo simulator of the entire bracket. Owns tournament data (`GROUPS`, `HOST_TEAMS`, `INJURY_ELO_ADJUSTMENTS`, `SQUAD_MARKET_VALUES`) and the extra strength layers (`compute_squad_elo_adjustments`, `compute_xg_form_multipliers`). `precompute_grids` → `simulate_tournament` (group → third-place → KO) → `run_monte_carlo` aggregates Bonusfragen probabilities. Blends market odds when `--fetch-odds`/`--odds-snapshot` is given.

**`matchday_tips.py`** — the "full stack" deliverable generator. Composes `predictor` *plus* `tournament_bonusfragen`'s extra layers (squad value, injury, xG form) and `schedule_context` (rest/travel/elevation). Squad/injury adjustments are injected via the `_elo_overrides` context manager, which **temporarily mutates the global `predictor.WORLD_CUP_2026_TEAMS` Elo dict** and restores it in a `finally` block (exception-safe). Per-match determinism uses `match_seed = seed + match_index`.

**Supporting modules:**
- `odds_client.py` — Polymarket / the-odds-api fetching → 1x2 probabilities → λ (`odds_to_lambdas`, `blend_lambdas` in predictor).
- `schedule_context.py` + `stadium_data.py` — FIFA 2026 schedule, stadium elevations/coords, `haversine_distance`, `tz_difference` → per-match travel/rest/elevation context. `build_schedule.py` / `build_real_schedule.py` regenerate the schedule JSON.
- `config.json` — tunable model constants (elevation/thermal/travel/host coefficients, KO ρ multipliers). `predictor.load_config` overrides only keys already present in `CONSTANTS`, coercing to float.

## Conventions & gotchas

- **Provenance discipline.** Generated outputs carry a header (timestamp / seed / git commit / command); `tests/gate_check.py` enforces it. Do **not** generate committed outputs from a dirty tree — past dirty-tree runs produced outputs citing commits that didn't contain the generating code (the "phantom history" problem). Commit code before regenerating, and reseed deterministically.
- **Output versioning.** `data/` holds versioned families (`bonusfragen_*`, `matchday1_tips_v3/v4/v5.txt`, timestamped `polymarket_snapshot_*.json`). New runs add a new version rather than overwriting.
- **Dead scripts at repo root** reference modules that were removed (`solver.py`, `tournament_sim.py`) or use `pandas`: `verify_solver_equivalence.py`, `test_tournament_sim.py`, `test_wiki.py`, `temp_verify.py`. They are not part of the live stack — don't use them as references for current behavior.
- **Project status** lives in `PROJECT.md` (milestone table) and the most recent `FORENSIC_RECHECK_*.md` audit. The repo is mid-"V5". The following audited defects are now **fixed in the worktree** (uncommitted): host status in `matchday_tips.py` (`"host"`→`"True Home"`, fan share as decimals); `Congo DR` aliases in `TEAM_NAME_MAPPING`; the silent odds-parse `except` now warns; the Bonusfragen KO shootout uses `predictor.penalty_shootout_distribution` + `PENALTY_STRENGTH` via `tbf._penalty_win_prob` (no more coinflip clamp); `market_probs` is wired end-to-end through a shared `tbf.apply_market_odds_to_row` (matchday gained `--odds-snapshot`); provenance headers carry a `-dirty` flag (`tbf.git_commit_label`); `.gitignore` added and `*.pyc` untracked.
- **F9 (validation honesty) — resolved**: two honest harnesses over the same 192 real matches (2014+2018+2022, pre-tournament Elo, no lookahead; datasets `data/wc20XX_results.csv`). `backtest_kicktipp_folds.py`: optimized **ties** baseline on points (291–291) — DC+NB never move the EV-optimal tip. `backtest_calibration_tuning.py`: DC+NB are marginally **worse** on all calibration metrics (Brier/RPS/log-loss/exact-log-loss), and leave-one-tournament-out tuning of ρ/α **loses** to baseline on points (−4) and RPS (+0.0015); Negative Binomial monotonically hurts points. **Net: R4 not met on any measured criterion; the simple Elo→Poisson→EV path is at least as good.** Circular MC defense withdrawn (`validation/backtest_engine_real.md`); full writeup `validation/F9_OUT_OF_SAMPLE.md`. A lower-variance follow-up against **non-penalty xG** (StatsBomb open data, 2018+2022; `build_xg_data.py` → `data/wc20XX_xg.csv` → `backtest_xg_calibration.py`) found the core Elo→λ has real margin skill (npxG-margin r≈+0.57) but is **over-scaled** (overstates favorites; MAE worse than a constant) → recalibrate `elo_baseline_goals`/`elo_scale_factor`; context showed a per-team MAE gain that **disappeared on the bias-invariant margin** (confound, not signal). **Status of those recommendations**: the Elo→λ recalibration **was applied** (`elo_baseline_goals` 1.35 → 1.00, commit 13da0cd) and subsequently **points-validated** on the same 192 matches (299 pts vs 291 old default; paired bootstrap +8.1, 95% CI [−16, +33] — best tested config, though within noise). NB stays off by default (α=0); ρ=−0.05 remains (tip-neutral per F9). Further λ tuning is frozen until after the tournament (see `IMPLEMENTATION_PLAN.md` S10). (Altitude/heat curves remain untestable on free xG — no 2014, no qualifiers.)
