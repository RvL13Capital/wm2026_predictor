# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FIFA World Cup 2026 prediction engine for a **Kicktipp** pool (4/3/2 scoring), plus a research-grade betting layer. It produces: EV-optimal score tips per match/matchday/KO-round, full-tournament Monte-Carlo answers to the pool's "Bonusfragen" (champion, semifinalists, top-scorer team, group winners), and a **paper-mode** derivative edge scanner. The living work program is `IMPLEMENTATION_PLAN.md` (step IDs S1–S24, gates G1/G2); current status lives in its "Status" section. Development happens on `main` (ops machine) plus per-session ops PR branches from sandboxed containers (e.g. live-state/injury updates), which need odds snapshots ferried to them — see the egress gotcha below.

**Pool rules (verified — gate G1, `validation/POOL_RULES.md`):** 4/3/2 scoring where a non-exact draw tip on a draw result scores **2** (the TENDENCY points, NOT pts_diff — operator-verified 2026-06-27 against real Kicktipp results, **correcting** the earlier "Tordifferenz includes draws" assumption; the 3-pt Tordifferenz bonus applies only to DECISIVE results — see `get_points` + the draw branch of `solve_optimal_tip_from_grid`), and KO games are scored **"inkl. Elfmeterschießen"** → engine convention `kicktipp_ko_convention = "shootout_total"` (no draws; 90' + ET + every converted shootout kick summed into the final score).

## Environment

- Python 3.10+ via system `python3`. **Core prediction path is stdlib-only; the quant layer (`vectorized_mc.py`, `edge_scanner.py`, `backtest_harness.py`) requires numpy**: `pip install -r requirements.txt`. On the ops Mac the system `python3` has no numpy — use `venv/bin/python3` for the quant layer (it has numpy + weasyprint; its `pip` is broken because the venv was moved — install new packages elsewhere).
- Polymarket/the-odds-api fetches need outbound network; sandboxed containers may 403 — all fetch paths degrade gracefully to Elo-only/skip.
- Env vars: `WM2026_BENCH=1` asserts the 100k-sim wall-clock budget (off by default — hardware-dependent); `WM2026_NO_MATRIX_CACHE=1` forces a cold matrix rebuild; `WM2026_NO_FRIENDLY_ELO=1` disables the post-friendlies Elo overlay; `CALLMEBOT_PHONE`/`CALLMEBOT_APIKEY` (+ `CALLMEBOT_RECIPIENTS` = `phone:apikey,…` for multiple targets) enable WhatsApp ops pushes (`utils/notify.py`, `docs/NOTIFICATIONS.md` — opt-in via `--notify` on `edge_scanner.py` / `scripts/score_predictions.py`, ad-hoc via `scripts/notify_whatsapp.py`; unconfigured = silent no-op); `WM2026_REC_STATE` overrides the recommendation-change baseline file (`utils/recommendations_state.py` — the four tip/Bonusfragen CLIs always diff against the last run and alert on any flipped recommendation).

## Commands

```bash
# Single match (CLI delegates to predict_single_match — same pipeline as batch/library)
python3 predictor.py --teamA Spain --teamB Qatar
python3 predictor.py --teamA Croatia --teamB Brazil --phase QF --json   # KO: shootout_total grid
python3 predictor.py --batch data/sample_matchday.csv

# Tip sheets (group matchdays / KO rounds; full stack: squad+injury Elo, xG form, context)
python3 matchday_tips.py --md 1 --simulations 1000 --seed 42 --output data/matchdayN_tips_vX.txt
python3 ko_tips.py --round R32 --matches "Spain vs Uruguay; France vs Germany" --fatigued "Croatia" --seed 42

# Isolated read-only overlays (NEVER feed the main tips; each imports the engine one-way, mutates nothing)
python3 fatigue_ko_tips.py --round R32   # KO heat@kickoff-hour × travel × congestion → tip shifts/flips (fatigue_tips.py = group MDs)

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
python3 make_tips_pdf.py data/bonusfragen_tips.json out.pdf [--differential|--master|--full] [--md=N]  # branded sheets; --md=N picks the matchday (default 1); --full = all 72 fixtures + Bonusfragen; beware stale /tmp/bonus.json (the default)

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

**Tip generators:** `matchday_tips.py` (group MDs; flat ×0.87 MD3 trim — the only validated MD3 effect; injects rest/travel/altitude via `schedule_context`) and `ko_tips.py` / `scripts/prematch_alert.build_ko_row` (KO rounds; Dead-Legs ET fatigue via `--fatigued`). **The KO path now carries rest/travel/altitude too:** `build_ko_row` calls the exception-safe `ko_travel_context` (prev-match→this-venue rest/miles/tz from the live FIFA calendar, + altitude >1000 m), so KO main tips mirror the group context layer — in R32 the long rests (4–9 d) make it ~0, but it bites in R16/QF. Both inject squad+injury Elo through `_elo_overrides` and emit the provenance-headed format `scripts/log_predictions.py` parses.

**Isolated read-only overlays** — separate side engines that consume the main tip's λ and **never feed back** (one-directional; import the engine, mutate nothing): `ou_total_*` (re-slave the goal total to the market O/U, preserving the signed difference, never capped; the **tendency-preserving coin-flip** variant `ou_total_engine.ou_tendency_preserving_tip`/`ou_adjusted_from_extras` re-slaves to the market's coin-flip line — the interpolated O/U line where P(over)=0.5 — but **never flips the tip's tendency** (a draw stays a draw), with a per-line liquidity guard `OU_MIN_LINE_LIQUIDITY`; T-45 backtest: the naive rescale loses **−3/31** in the group by forfeiting points-rich 0:0 tips, the tendency-preserving one scores **+1/31** group / **+1/6** KO — apply it in **both** phases), `weather_*` (heat-only), and the differential fatigue pair `fatigue_tips.py` (group MDs) + `fatigue_ko_tips.py` (`--round R32|…`, KO). Since travel/rest now live in the **core** KO λ (above), the KO overlay applies only the **increment** the core lacks: heat[kickoff-hour open-meteo forecast] × congestion (don't re-apply travel → double-count). It rebuilds the **shootout_total** grid via `fatigue_engine.fatigue_adjusted_ko_tip` (no draws — `fatigue_adjusted_tip`'s 90' draw-allowed grid is group-only). Each gates flips on `MIN_EV_MARGIN`; venue/altitude come from the live FIFA calendar `Stadium` (authoritative), not `data/fifa_2026_schedule.json` (the buggy placeholder).

**Betting layer (paper only):** `edge_scanner.py` — live Polymarket outright + 1X2 books (`odds_client.py`, liquidity-guarded), manual `--books` JSON for other derivatives; pure-model priors (never blend the market into a prior you difference against the market); **two-track calibration:** match-market pricing runs under `SCANNER_PRICING_CALIBRATION` (bg=1.25 — log-loss-optimal; tips keep frozen bg=1.0) and BTTS/exact-score books are refused as structurally unpriceable (`validation/SCORING_ENVIRONMENT_PRIOR.md`); Shin de-vig (`utils/math_utils.devig_shin` — canonical iterative, see `validation/SHIN_EVALUATION.md` for the fake-Shin post-mortem); **joint sizing per mutually exclusive book** (`kelly_mutually_exclusive`); per-leg/per-scan caps; JSONL ledger `scan_ledger/2026.jsonl`. Match-market model 1X2 always derives from `grid_90` (exchange 1X2 settles on 90', even for KO fixtures). `odds_client` excludes in-play/settled books at the fetch boundary (`is_degenerate_1x2`: any leg ≤1.02 or ≥200 — Polymarket's `closed` flag lags the final whistle).

**Support:** `schedule_context.py` + `stadium_data.py` (schedule/travel/elevation/roofs), `utils/live_state.py` (+ `scripts/validate_live_state.py`), `squad_data.py` (note: fixed 65/35 XI/bench split → depth terms are collinear with squad value until real per-player data exists — plan S23).

## Validation truths (do not regress these)

- **F9 (`validation/F9_OUT_OF_SAMPLE.md`):** over 192 real matches, DC+NB+context+phase are points-neutral and calibration-neutral. The simple Elo→Poisson→EV path carries the performance.
- **λ calibration (`validation/points_recalibration.md`):** production `elo_baseline_goals=1.0` scores **289/192** under the corrected draws=2 scoring (was **299** under the wrong draws=3 rule). **⚠ CAVEAT (2026-06-27):** λ=1.0 was originally tuned to *exploit* the wrong draws=3 rule (low λ → many `0:0` tips, each worth 3 on any draw); under the verified draws=2 rule those draw tips are worth less, so **λ=1.0 may no longer be points-optimal** — a measured post-tournament recalibration candidate. **λ tuning is frozen until post-tournament — with one pre-registered exception:** the group-stage checkpoint (`scripts/lambda_checkpoint.py`; criteria pre-registered 2026-06-11) permits a recalibration iff its band-conditional exact-hit tripwire fires (NB: that checkpoint also ran under draws=3 — re-evaluate). `tests/test_lambda_points_floor.py` enforces **≥285** — any deliberate calibration change must beat the floor or update it *with a measurement in that doc*. Points and calibration are different objectives (tipping optimizes points; the betting track needs calibration).
- **Gate G2 (`backtest_real_market.py`) — VERDICT RENDERED 2026-06-11: ❌ NOT PASSED; the scanner is paper-only as a *measured conclusion*.** All 192 fixtures filled with real closing-average odds (2014: Kaggle Beat-the-Bookie 27-book averages; 2018/2022: football-data.co.uk `WorldCup2026.xlsx`), all integrity gates green. Result (`validation/backtest_real_market.txt`): model beats the close on 1/3 folds (2014 only — the upset WC; 2018/2022 markets beat the model on every proper scoring rule), aggregate flat ROI +0.12/bet with 95% CI [−0.16, +0.43] ⊇ 0. Criteria were pre-registered (≥2/3 folds AND CI > 0); do not re-litigate them mid-tournament. Never fabricate odds data. Data tooling: `make_odds_templates.py`, `merge_odds.py` (canonicalization, orientation flip, bookmaker medians, **Elo-concordance quarantine** that catches column swaps / wrong-year datasets), `fill_odds_theoddsapi.py` (2022 only — API history starts Jun 2020), `merge_odds.py --validate-only` for manual entry. `backtest_harness.py` is a feature ablation against a self-referential synthetic market — its dollar metrics are not market alpha.
- **Pre-registered 2026 record:** MD1 tips and the full Bonusfragen answer set (champion Spain, SF Spain/France/Argentina/England, Golden-Boot France, 12 group winners) are logged in `predictions_log/2026.jsonl` from clean commits, seed 42, before the Jun 11 opener. `scripts/score_predictions.py` scores the log against `live_state.json` as results arrive (realized points vs Σ-EV — variance made visible per matchday).

## Conventions & gotchas

- **Provenance discipline.** Commit code BEFORE regenerating any published output; headers carry a `(dirty)` flag; `log_predictions.py` refuses dirty artifacts; `tests/gate_check.py` validates header pairs. Pre-register tips in `predictions_log/2026.jsonl` BEFORE kickoff — that log is the post-tournament evidence base (plan S21).
- **Harness-first.** Any change that can move a tip or probability re-runs the 192-match folds before merge (the λ episode proved intuition flips sign here).
- **`.gitignore` policy:** generated tip sheets / bonusfragen outputs / snapshots / `data/matrix_cache/` stay **local**; the JSONL logs (`predictions_log/`, `scan_ledger/`) are **committed**.
- **Change freeze from Jun 28** (first KO match): only P0 fixes merge, each with the full suite + points-floor + equivalence tests green.
- **One commit per plan step ID**, message referencing the step (S-number).
- **Sandboxed container sessions** have an egress allowlist that blocks `gamma-api.polymarket.com` and `api.the-odds-api.com` (verified: "Host not in allowlist"). Fix: add them (plus `api.open-meteo.com`, `flagcdn.com`, `api.callmebot.com` for WhatsApp pushes) to the environment's network allowlist in the Claude Code settings; until then run live fetches on the ops machine (full egress) and ferry snapshots via `git add -f data/polymarket_match_odds.json` committed onto the container session's PR branch.
- **Market blend is opt-in:** `matchday_tips.py` blends Polymarket **only** with `--odds-snapshot <file>`; without it the sheet is Elo+context-only (the v6 "market" sheets that outscore the Elo ones need it). `make_tips_pdf.py` and the bonus path auto-load `data/polymarket_match_odds.json`.
- **Venue data:** `data/fifa_2026_schedule.json` shipped placeholder venues — WRONG for 54/72 group matches (drives travel/altitude). Rebuild from the authoritative FIFA calendar `Stadium`/`CityName`. The WBGT heat term in `get_adjusted_lambdas` is **dormant** (fed the flat 20 °C default, no forecast feed), so venues affect only travel/altitude in live tips.
- **Local prematch ops:** `scripts/prematch_local_runner.py` (nohup 5-min T-45 alert daemon, XI-gated, messages in pool home–away order) + `scripts/results_sweep.py` (auto-records finished First-Stage results into `live_state`, commits, flags injuries to `data/logs/sweep.log`) — the GitHub Actions cron is disabled. `source ~/.zshrc` for CallMeBot/odds creds (absent from the non-login Bash shell).
- **Open items:** S11 canonical-dynamics decision (recommendation: vectorized fatigue canonical; execute post-tournament); S15 third-place match M103 (absent from both engines — Golden Boot misses its goals); ~~G2 odds data~~ (supplied + verdict rendered NOT PASSED 2026-06-11); optional pool-history check of the shootout score representation (`validation/POOL_RULES.md`).
