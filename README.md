# WM 2026 Prediction Engine & Kicktipp Optimizer

A zero-dependency (pure Python stdlib) probabilistic pipeline for the 2026 FIFA World Cup,
built to maximize expected points in a 4-3-2 Kicktipp pool.

## What it actually is (no marketing)

1. **Base model** — Elo (auto-loaded from `data/elo_2026_post_friendlies.json`, falling back to
   the hardcoded ratings) mapped to goal expectations `λ = bg · 10^(±Δelo/sf)`, fed into a
   **Negative-Binomial** distribution (`α ≈ 0.06`) for fat-tailed scorelines. A Dixon-Coles `ρ`
   term exists but out-of-sample calibration drove it to ≈ 0, so it is effectively off.
2. **Context layer** — *deterministic* multiplicative adjustments for stadium **altitude**
   (acclimation decay), **WBGT thermal stress**, and **timezone / travel** fatigue. The total
   exponent is hard-capped at **±1.0** (≈ ×2.7); the observed real-venue extreme is ~0.59 (Azteca).
3. **Market bridge** — `odds_client.py` bulk-fetches live **1X2 match markets** from Polymarket and
   emits raw decimal odds. `predictor` strips favourite-longshot bias via the **Power method**,
   reverse-solves λ with a **KL-divergence** optimizer, and blends at 80%. Tournament *outright*
   markets are deliberately NOT used — they measure bracket equity, not 90-minute strength.
4. **Matchday-3 rule** — a flat **0.87× goal trim** on MD3, the *only* effect that survived a
   backtest of 48 historical MD3 matches (the regime "game-theory matrix" did not — see
   `validation/md3_regime_backtest.py`).
5. **Optimizer** — an O(N²) aggregate search that maps the score grid onto the exact 4-3-2 payout
   and returns the **EV-maximizing tip** (not the most-likely score, which is a different object).

## Validation

```bash
python3 validation/evaluate_calibration.py     # RPS / Brier / LogLoss vs naive (OOS 2014-22)
python3 validation/md3_regime_backtest.py      # why the MD3 game-theory matrix was scrapped
python3 recalibrate_lambda.py                  # why the default λ config is left un-tuned
```

Latest out-of-sample (144 group matches, 2014/2018/2022):

| metric | model | naive 1/3 | improvement |
|--------|-------|-----------|-------------|
| RPS | 0.206 | 0.245 | **+16.1%** |
| Brier | 0.567 | 0.667 | +14.9% |
| LogLoss | 0.972 | 1.099 | +11.6% |

(Naive 1/3 is a *weak* baseline; a bookmaker-close comparison would be the real bar but needs
historical match odds we don't hold for 2014-22. RPS is the headline ordinal metric.)

## Daily runbook (kickoff week)

```bash
# 1. Fetch live 1X2 market odds (~12h pre-kickoff; returns {} until Polymarket lists matches)
python3 odds_client.py > data/polymarket_match_odds.json

# 2. (If new warm-up results) refresh Elo — every script auto-imports it afterwards
python3 update_elo_friendlies.py

# 3. EV-optimal matchday tips WITH the 80% market blend  →  your Kicktipp submissions
python3 matchday_tips.py --md 1 --odds-snapshot data/polymarket_match_odds.json

# 4. Structural bracket (Elo projection; market NOT blended — no live odds for future rounds)
python3 make_bracket_html.py          # sampled (default); or `modal` / `simulate`
```

## Honest answers to the red-team

- **"No scipy/numpy?"** — by design. Pure stdlib → trivial serverless deploy, no wheel bloat.
- **"Context params unvalidated?"** — acknowledged and capped at **±1.0** so they act as
  tie-breakers, never baseline-destroyers. (A claimed `e^5 ≈ 148×` blow-up is impossible — bounded
  inputs cap the real exponent near 0.6; verified empirically.)
- **"EV ignores pool game theory?"** — correct, and *not yet fixed*. The optimizer maximizes
  absolute EV, not differential rank. A contrarian fade-the-herd mode is scoped but **not shipped**:
  its ownership weights need real pool data, not guesses.
- **"No rigorous calibration?"** — see `validation/evaluate_calibration.py` (RPS / Brier / LogLoss,
  out-of-sample, pure Python).

## Design constraints

Zero third-party dependencies. `predictor.py` is a self-contained engine: Elo → distribution →
context → optimizer. Every other script imports it, so a single Elo source and a single goal model
drive the bracket, the matchday tips, and the bonusfragen Monte Carlo alike.
