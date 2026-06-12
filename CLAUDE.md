# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FIFA World Cup 2026 prediction engine for a **Kicktipp** pool (4/3/2 scoring), plus a research-grade betting layer. It produces: EV-optimal score tips per match/matchday/KO-round, full-tournament Monte-Carlo answers to the pool's "Bonusfragen" (champion, semifinalists, top-scorer team, group winners), and a **paper-mode** derivative edge scanner. The living work program is `IMPLEMENTATION_PLAN.md` (step IDs S1–S24, gates G1/G2); current status lives in its "Status" section. Development happens on `main` (ops machine) plus per-session ops PR branches from sandboxed containers (e.g. live-state/injury updates), which need odds snapshots ferried to them — see the egress gotcha below.

**Pool rules (verified — gate G1, `validation/POOL_RULES.md`):** 4/3/2 scoring where a non-exact draw tip on a draw result scores 3 (Kicktipp "Tordifferenz" rule — see `get_points`), and KO games are scored **"inkl. Elfmeterschießen"** → engine convention `kicktipp_ko_convention = "shootout_total"` (no draws; 90' + ET + every converted shootout kick summed into the final score).

## Environment

- Python 3.10+ via system `python3`. **Core prediction path is stdlib-only; the quant layer (`vectorized_mc.py`, `edge_scanner.py`, `backtest_harness.py`) requires numpy**: `pip install -r requirements.txt`. On the ops Mac the system `python3` has no numpy — use `venv/bin/python3` for the quant layer (it has numpy + weasyprint; its `pip` is broken because the venv was moved — install new packages elsewhere).
- Polymarket/the-odds-api fetches need outbound network; sandboxed containers may 403 — all fetch paths degrade gracefully to Elo-only/skip.
- Env vars: `WM2026_BENCH=1` asserts the 100k-sim wall-clock budget (off by default — hardware-dependent); `WM2026_NO_MATRIX_CACHE=1` forces a cold matrix rebuild; `WM2026_NO_FRIENDLY_ELO=1` disables the post-friendlies Elo overlay; `CALLMEBOT_PHONE`/`CALLMEBOT_APIKEY` enable WhatsApp ops pushes (`utils/notify.py`, `docs/NOTIFICATIONS.md` — opt-in via `--notify` on `edge_scanner.py` / `scripts/score_predictions.py`, ad-hoc via `scripts/notify_whatsapp.py`; unconfigured = silent no-op); `WM2026_REC_STATE` overrides the recommendation-change baseline file (`utils/recommendations_state.py` — the four tip/Bonusfragen CLIs always diff against the last run and alert on any flipped recommendation).

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
python3 scripts/score_predictions.py --results data/live_state.json  # realized pts vs model EV ("luck" per matchday)
python3 scripts/log_predictions.py --kind matchday --file data/matchdayN_tips_vX.txt  # pre-register BEFORE kickoff
python3 tests/gate_check.py --bonus <bonus.txt> --matchday <tips.txt>
python3 make_tips_pdf.py data/bonusfragen_tips.json out.pdf [--differential|--master|--full]  # branded sheets; --full = all 72 fixtures + Bonusfragen; beware stale /tmp/bonus.json (the default)

# Gate-G2 odds data (templates are committed with blank odds — data/ODDS_DATA_README.md)
python3 scripts/fill_odds_theoddsapi.py --year 2022 --estimate   # The Odds API historical (2022 only; paid; run where the host is allowlisted)
python3 scripts/merge_odds.py --year 2022 --raw <downloaded.csv> --dry-run   # bulk merge with quarantine gates
python3 scripts/merge_odds.py --year 2018 --validate-only        # integrity gates over manually entered rows

# Validation / backtests
python3 backtest_real_market.py            # gate G2 vs REAL closing odds — exits 2 until data/wcXXXX_odds.csv exist
python3 backtest_kicktipp_folds.py         # F9: 192 real matches, features vs baseline
python3 recalibrate_lambda.py              # LOTO calibration grid (λ tuning is FROZEN — see below)
python3 backtest_harness.py --tournament 2022   # FEATURE ABLATION vs synthetic self-market (NOT market alpha)
```

### Tests

```bash
python3 -m unittest discover tests          # 281 tests; ~5 min (vectorized matrix precompute dominates)
python3 -m unittest tests.test_ko_convention -v        # one module (dotted path)
```

CI (`.github/workflows/ci.yml`) runs the full suite + CLI smoke tests on every PR. Key suites: `test_lambda_points_floor` (calibration regression gate, ≥295/192 pts), `test_ko_convention` (G1 conventions + CLI≡library), `test_joint_kelly` (vs brute-force E[log-growth]), `test_edge_scanner` (offline, stub matrix), `test_vectorized_mc` (incl. cache roundtrip; builds the full matrix once in `setUpClass`). Several tests write temp CSVs into cwd.

## Architecture

Everything flows through one engine; **`predictor.predict_single_match(row) -> dict` is the single pipeline** for CLI, batch, matchday and KO tips (the CLI `main()` delegates to it — never add a second solving path).

**`predictor.py`** — the engine (sectioned by `# ===` headers): inlined 4/3/2 EV solver (`solve_optimal_tip_from_grid`, `get_points`); `WORLD_CUP_2026_TEAMS` Elo (+ `data/elo_2026_post_friendlies.json` overlay at import) and `TEAM_NAME_MAPPING` (always resolve names through it); Poisson/NB + Dixon-Coles (`generate_joint_grid`, renormalized); context layer (`get_adjusted_lambdas`: altitude, WBGT/PPDA heat, travel, host/fans, squad-value VORP); KO grids — `generate_ko_final_grid` (3-layer, shootout_total), `generate_ko_120_grid` (ties retained), selected by `CONSTANTS["kicktipp_ko_convention"]`; advancement probabilities always use the 3-layer model + `penalty_shootout_distribution`. `load_config` is type-preserving (string constants stay strings).

**Two tournament engines — REMAINING, deliberate divergence (plan S11 decision pending):** `tournament_bonusfragen.py` (scalar) evolves **dynamic in-tournament Elo** ("Cinderella momentum") and keeps the **H2H tiebreak step**; `vectorized_mc.py` (numpy) uses static λ with **ET-fatigue carry-over states**. Everything else was unified in the S11 consistency pass (commit `c4647bd`): flat **MD3 ×0.87** in both engines (the only validated MD3 effect), tiebreaks = pts/GD/GF/(H2H scalar-only)/**drawing of lots** (Elo removed — not in FIFA regulations), scalar ET model on the engine constants, champion market blend renormalized (`blend_champion_probs`). **The vectorized engine is canonical for the scanner.** Do not unify the dynamics without the S11 decision (recommendation on record: fatigue canonical, retire momentum-Elo — execute post-tournament). `vectorized_mc.build_matrix()` caches the ~4-min precompute to `data/matrix_cache/*.npz` (currently `CACHE_VERSION = 2`), keyed by a SHA-256 fingerprint over every tensor input — **bump `CACHE_VERSION` whenever grid-generation logic changes upstream.**

**Tip generators:** `matchday_tips.py` (group MDs; flat ×0.87 MD3 trim — the only validated MD3 effect) and `ko_tips.py` (KO rounds; Dead-Legs fatigue via `--fatigued`). Both inject squad+injury Elo through the exception-safe `_elo_overrides` context manager and emit the provenance-headed format `scripts/log_predictions.py` parses.

**Betting layer (paper only):** `edge_scanner.py` — live Polymarket outright + 1X2 books (`odds_client.py`, liquidity-guarded), manual `--books` JSON for other derivatives; pure-model priors (never blend the market into a prior you difference against the market); **two-track calibration:** match-market pricing runs under `SCANNER_PRICING_CALIBRATION` (bg=1.25 — log-loss-optimal; tips keep frozen bg=1.0) and BTTS/exact-score books are refused as structurally unpriceable (`validation/SCORING_ENVIRONMENT_PRIOR.md`); Shin de-vig (`utils/math_utils.devig_shin` — canonical iterative, see `validation/SHIN_EVALUATION.md` for the fake-Shin post-mortem); **joint sizing per mutually exclusive book** (`kelly_mutually_exclusive`); per-leg/per-scan caps; JSONL ledger `scan_ledger/2026.jsonl`. Match-market model 1X2 always derives from `grid_90` (exchange 1X2 settles on 90', even for KO fixtures). `odds_client` excludes in-play/settled books at the fetch boundary (`is_degenerate_1x2`: any leg ≤1.02 or ≥200 — Polymarket's `closed` flag lags the final whistle).

**Support:** `schedule_context.py` + `stadium_data.py` (schedule/travel/elevation/roofs), `utils/live_state.py` (+ `scripts/validate_live_state.py`), `squad_data.py` (note: fixed 65/35 XI/bench split → depth terms are collinear with squad value until real per-player data exists — plan S23).

## Validation truths (do not regress these)

- **F9 (`validation/F9_OUT_OF_SAMPLE.md`):** over 192 real matches, DC+NB+context+phase are points-neutral and calibration-neutral. The simple Elo→Poisson→EV path carries the performance.
- **λ calibration (`validation/points_recalibration.md`):** production `elo_baseline_goals=1.0` scores **299/192** (best tested; mechanism: low λ → EV-optimal `0:0` tips under the Tordifferenz rule). **λ tuning is frozen until post-tournament — with one pre-registered exception:** the group-stage checkpoint (`scripts/lambda_checkpoint.py`, run after MD3 / before the Jun-28 KO freeze; criteria pre-registered 2026-06-11 in that doc) permits a recalibration iff its band-conditional exact-hit tripwire fires. `tests/test_lambda_points_floor.py` enforces ≥295 — any deliberate calibration change must beat the floor or update it *with a measurement in that doc*. Points and calibration are different objectives (tipping optimizes points; the betting track needs calibration).
- **Gate G2 (`backtest_real_market.py`) — VERDICT RENDERED 2026-06-11: ❌ NOT PASSED; the scanner is paper-only as a *measured conclusion*.** All 192 fixtures filled with real closing-average odds (2014: Kaggle Beat-the-Bookie 27-book averages; 2018/2022: football-data.co.uk `WorldCup2026.xlsx`), all integrity gates green. Result (`validation/backtest_real_market.txt`): model beats the close on 1/3 folds (2014 only — the upset WC; 2018/2022 markets beat the model on every proper scoring rule), aggregate flat ROI +0.12/bet with 95% CI [−0.16, +0.43] ⊇ 0. Criteria were pre-registered (≥2/3 folds AND CI > 0); do not re-litigate them mid-tournament. Never fabricate odds data. Data tooling: `make_odds_templates.py`, `merge_odds.py` (canonicalization, orientation flip, bookmaker medians, **Elo-concordance quarantine** that catches column swaps / wrong-year datasets), `fill_odds_theoddsapi.py` (2022 only — API history starts Jun 2020), `merge_odds.py --validate-only` for manual entry. `backtest_harness.py` is a feature ablation against a self-referential synthetic market — its dollar metrics are not market alpha.
- **Pre-registered 2026 record:** MD1 tips and the full Bonusfragen answer set (champion Spain, SF Spain/France/Argentina/England, Golden-Boot France, 12 group winners) are logged in `predictions_log/2026.jsonl` from clean commits, seed 42, before the Jun 11 opener. `scripts/score_predictions.py` scores the log against `live_state.json` as results arrive (realized points vs Σ-EV — variance made visible per matchday).

## Conventions & gotchas

- **Provenance discipline.** Commit code BEFORE regenerating any published output; headers carry a `(dirty)` flag; `log_predictions.py` refuses dirty artifacts; `tests/gate_check.py` validates header pairs. Pre-register tips in `predictions_log/2026.jsonl` BEFORE kickoff — that log is the post-tournament evidence base (plan S21).
- **Harness-first.** Any change that can move a tip or probability re-runs the 192-match folds before merge (the λ episode proved intuition flips sign here).
- **`.gitignore` policy:** generated tip sheets / bonusfragen outputs / snapshots / `data/matrix_cache/` stay **local**; the JSONL logs (`predictions_log/`, `scan_ledger/`) are **committed**.
- **Change freeze from Jun 28** (first KO match): only P0 fixes merge, each with the full suite + points-floor + equivalence tests green.
- **One commit per plan step ID**, message referencing the step (S-number).
- **Sandboxed container sessions** have an egress allowlist that blocks `gamma-api.polymarket.com` and `api.the-odds-api.com` (verified: "Host not in allowlist"). Fix: add them (plus `api.open-meteo.com`, `flagcdn.com`, `api.callmebot.com` for WhatsApp pushes) to the environment's network allowlist in the Claude Code settings; until then run live fetches on the ops machine (full egress) and ferry snapshots via `git add -f data/polymarket_match_odds.json` committed onto the container session's PR branch.
- **Open items:** S11 canonical-dynamics decision (recommendation: vectorized fatigue canonical; execute post-tournament); S15 third-place match M103 (absent from both engines — Golden Boot misses its goals); ~~G2 odds data~~ (supplied + verdict rendered NOT PASSED 2026-06-11); optional pool-history check of the shootout score representation (`validation/POOL_RULES.md`).
