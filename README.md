# 🏆 FIFA World Cup 2026 Prediction Engine & Quant Trading Suite

A sports quantitative forecasting engine and exchange-trading research system. Designed to predict exact scorelines, simulate the 48-team tournament bracket, and scan derivative pricing for divergence between model and market.

> **Status & evidence:** see [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for the current work program and [`validation/`](validation/) for the honest out-of-sample record (notably [`validation/F9_OUT_OF_SAMPLE.md`](validation/F9_OUT_OF_SAMPLE.md) and [`validation/SHIN_EVALUATION.md`](validation/SHIN_EVALUATION.md)).

---

## ⚡ Key Architecture & Core Capabilities

1. **Vectorized Tournament Simulation (`vectorized_mc.py`)**
   - Simulates 100,000 full tournament realities (regulation, extra time, and penalty shootouts) in seconds — ~4 s on fast desktop hardware, **14.6 s measured on the CI reference container** — after a **one-off matrix precompute of roughly 4 minutes** (pure-Python grid generation; caching planned, see plan step S13).
   - Compresses the per-simulation working state by 87.5% using compact `np.int8`/`np.int16` types (~29 MB at N=100k). The precomputed float32 CDF lookup tensors are ~100 MB and stream from RAM.
   - Maps qualifying third-place teams using a precomputed 12-bit group bitmask routing table (all 495 valid 8-of-12 combinations), removing loop bottlenecks in the hot path.

2. **Physiological & Environmental Engine (`predictor.py`)**
   - **Dixon-Coles low-score adjustment**: resolves draw bias for low scores ($0$-$0$, $1$-$1$) via the standard DC correlation correction ($\rho$), generalized to Negative-Binomial marginals.
   - **Tactical Heat Vulnerability (PPDA)**: dynamic heat degradation scales with pressing intensity. High-pressing squads (e.g., Spain, low PPDA) face larger exhaustion multipliers in high heat; low-block squads are shielded.
   - **Retractable Roof Overrides**: Dallas, Houston, Atlanta, and Vancouver stadium profiles lock the wet-bulb globe temperature (WBGT) to $21.0^\circ\text{C}$ regardless of outside weather.
   - **Altitude & Travel Attrition**: altitude acclimation decay curves and travel/timezone penalties relative to rest cycles.
   - Note: per the 192-match out-of-sample record (`validation/F9_OUT_OF_SAMPLE.md`), the DC/NB/context layers are **points-neutral** on the Kicktipp objective; they remain available and are being evidence-tested live in 2026.

3. **Squad Value & Injury Attrition (`squad_data.py`)**
   - Maps qualified teams to Transfermarkt-based Starting XI and Bench valuations (65% XI / 35% Bench splits — note: with this fixed split, bench depth is collinear with squad value until real per-player data is ingested).
   - Simulates starter injuries via value-over-replacement swapping, replacing injured starters with average bench value and adjusting expected-goal margins.

4. **In-Play Oracle & Fatigue Propagation ("Dead Legs")**
   - **Live State Ingestion**: bypasses stochastic sampling and enforces deterministic score overrides (by `"Team A vs Team B"` key or match id `"M73"`…), propagating updated standings through the bracket.
   - **Fatigue carry-over**: teams that played Extra Time / penalties carry a bench-depth-scaled exhaustion penalty into their next match.

5. **Derivative Edge Scanner (`edge_scanner.py`)**
   - De-vigs each market book using **Shin's Method** (solved iteratively via Newton–Raphson with a bisection fallback — there is no closed form for 3+ outcomes), then computes edge against the **de-vigged** market and sizes with the **0.25x Fractional Kelly Criterion** on raw payout odds.
   - **The built-in market lines are ILLUSTRATIVE STATIC books** shaped like exchange feeds; live Polymarket wiring is planned (plan step S17). Kelly's guarantees hold only if the model probabilities are correct — an unproven premise; see `validation/SHIN_EVALUATION.md`. Real-money use is gated on the real-odds backtest (plan gate G2).

6. **Point-in-Time Backtesting (`backtest_harness.py`)**
   - Steps chronologically through past tournaments (2014, 2018, 2022) with pre-tournament Elo snapshots.
   - Pits the full physiological model against a vig-adjusted **Synthetic Elo Market Baseline**. Because that baseline is derived from the engine's own Elo, the Brier-skill comparison is a feature ablation, **not** evidence of market alpha (see `validation/SHIN_EVALUATION.md`, Finding 3).

---

## 📂 Code Layout

* [`predictor.py`](predictor.py): Core probability modeling, de-vigging, Dixon-Coles adjustment, and physiological factors.
* [`vectorized_mc.py`](vectorized_mc.py): Vectorized bracket simulator, in-play overrides, and 4D fatigue carry-over tensors.
* [`edge_scanner.py`](edge_scanner.py): Derivative odds scanner and Kelly allocator (static demo books pending a live feed).
* [`backtest_harness.py`](backtest_harness.py): Chronological point-in-time backtesting harness.
* [`matchday_tips.py`](matchday_tips.py): Expected-value maximizing Kicktipp tip generator for group matchdays.
* [`tournament_bonusfragen.py`](tournament_bonusfragen.py): Kicktipp outright/prop questions solver (group winners, semifinalists, champion, top-scorer team).
* [`squad_data.py`](squad_data.py): Starting XI and Bench Transfermarkt valuations database.
* [`stadium_data.py`](stadium_data.py): Retractable roof flags, elevations, coordinates, and timezone profiles.
* [`data/`](data/): Tournament schedule, historical results, and generated prediction outputs (versioned, with provenance headers).
* [`tests/`](tests/): 180+-test unit and end-to-end verification suite (`python3 -m unittest discover tests`).

## 📦 Dependencies

The core prediction path (`predictor.py`, `matchday_tips.py`, `tournament_bonusfragen.py`, `odds_client.py`) is pure Python standard library. The vectorized/quant layer (`vectorized_mc.py`, `edge_scanner.py`, `backtest_harness.py`) **requires numpy**:

```bash
pip install -r requirements.txt
```

---

## 🚀 Execution & Usage Guide

### 1. Run the Test Suite
```bash
python3 -m unittest discover tests
# wall-clock performance budget is only asserted with WM2026_BENCH=1
```

### 2. Generate Optimal Kicktipp Score Tips
Optimal score predictions for a group matchday (maximizing expected points under the 4/3/2 scoring rules):
```bash
python3 matchday_tips.py --md 1 --simulations 1000 --seed 42 --output data/matchday1_tips_vX.txt
```

### 3. Solve Outright Tournament Bonus Questions
```bash
python3 tournament_bonusfragen.py --sims 10000 --seed 42
```

### 4. Run the Edge Scanner (demo books)
```bash
python3 edge_scanner.py --daemon
```

### 5. Run the Chronological Backtest Harness
```bash
python3 backtest_harness.py --tournament 2018 --threshold 0.015 --kelly 0.25
```
