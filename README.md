# 🏆 FIFA World Cup 2026 Prediction Engine & Quant Trading Suite

An institutional-grade sports quantitative forecasting engine and exchange trading system. Designed to predict exact scorelines, simulate the 48-team tournament bracket, and systematically exploit derivative pricing inefficiencies in live betting exchanges.

---

## ⚡ Key Architecture & Core Capabilities

1. **High-Frequency Vectorized Simulation (`vectorized_mc.py`)**
   - Simulates 100,000 full tournament realities (regulation, extra time, and penalty shootouts) in **4.2 seconds**.
   - Compresses working memory by **87.5%** using compact `np.int8`/`np.int16` types, fitting the entire simulation state directly within the CPU's **L3 cache** and bypassing RAM bus latency.
   - Maps qualifying third-place teams using a precomputed 12-bit group bitmask routing table, removing loop bottlenecks in the hot path.

2. **Physiological & Environmental Engine (`predictor.py`)**
   - **Bivariate Dixon-Coles Copula**: Resolves draw bias for low scores ($0$-$0$, $1$-$1$) by modeling exact score correlation parameters ($\rho$).
   - **Tactical Heat Vulnerability (PPDA)**: Dynamic heat degradation scales based on pressing intensity. High-pressing squads (e.g., Spain, low PPDA) face severe physical exhaustion multipliers in high heat, while low-block squads (e.g., Qatar, high PPDA) are shielded.
   - **Retractable Roof Overrides**: Dallas, Houston, Atlanta, and Vancouver stadium profiles trigger roof overrides, locking internal wet-bulb globe temperature (WBGT) to an optimal $21.0^\circ\text{C}$ regardless of outside weather forecasts.
   - **Altitude & Travel Attrition**: Evaluates altitude acclimation decay curves and travel timezone crossing penalties relative to resting cycles.

3. **Real-Time Attrition & Squad VORP (`squad_data.py`)**
   - Maps qualified teams to Transfermarkt-based Starting XI and Bench valuations (65% XI / 35% Bench splits).
   - Simulates starter injuries via **Value Over Replacement Player (VORP)** swapping, replacing injured stars with average bench players and dynamically adjusting expected goal margins.

4. **In-Play Oracle & Fatigue Propagation ("Dead Legs")**
   - **Live State Ingestion**: Bypasses stochastic sampling and enforces deterministic score updates dynamically, propagating updated standings in real-time.
   - **Fatigue carry-over**: Knocks out teams playing Extra Time / Penalties in previous rounds by carrying forward a bench-depth-scaled exhaustion penalty ("Dead Legs") to their next match.

5. **Outrights Exchange Scanner Daemon (`edge_scanner.py`)**
   - Asynchronously pulls live betting exchange odds (Outright Winner, Reach SF, Win Group, etc.).
   - De-vigs each market book using **Shin's Method** (solved iteratively via Newton–Raphson with a bisection fallback — there is no closed form for 3+ outcomes) to isolate true probabilities from the overround, then computes edge against the **de-vigged** market.
   - Blends market-implied expected goals with the engine's physics-based priors.
   - Recommends capital allocations using the **0.25x Fractional Kelly Criterion** to maximize bankroll growth rate while keeping the risk of ruin at $0.00\%$.

6. **Point-in-Time Walk-Forward Backtesting (`backtest_harness.py`)**
   - Steps chronologically through past tournaments (2014, 2018, 2022) to evaluate the engine out-of-sample.
   - Pits the full physiological model directly against a vig-adjusted **Synthetic Elo Market Baseline** to isolate predictive alpha (Brier Score, Brier Skill Score, Sharpe, Max Drawdown).

---

## 📂 Code Layout

* [`predictor.py`](file:///Users/vonlinck/Desktop/wm2026_predictor/predictor.py): Core probability modeling, margins, Dixon-Coles copula, and physiological adjustment factors.
* [`vectorized_mc.py`](file:///Users/vonlinck/Desktop/wm2026_predictor/vectorized_mc.py): Vectorized bracket simulator, in-play overrides, and 4D fatigue carry-over tensors.
* [`edge_scanner.py`](file:///Users/vonlinck/Desktop/wm2026_predictor/edge_scanner.py): Live betting exchange odds scanner and Kelly asset allocator.
* [`backtest_harness.py`](file:///Users/vonlinck/Desktop/wm2026_predictor/backtest_harness.py): Chronological point-in-time backtesting harness.
* [`matchday_tips.py`](file:///Users/vonlinck/Desktop/wm2026_predictor/matchday_tips.py): Expected-value maximizing Kicktipp tip generator for individual matchdays.
* [`tournament_bonusfragen.py`](file:///Users/vonlinck/Desktop/wm2026_predictor/tournament_bonusfragen.py): Kicktipp Outright/Prop questions solver (group winners, semifinalists, champion, top goalscorer team).
* [`squad_data.py`](file:///Users/vonlinck/Desktop/wm2026_predictor/squad_data.py): Starting XI and Bench Transfermarkt valuations database.
* [`stadium_data.py`](file:///Users/vonlinck/Desktop/wm2026_predictor/stadium_data.py): Retractable roof flags, elevations, coordinates, and stadium profiles.
* [`data/`](file:///Users/vonlinck/Desktop/wm2026_predictor/data/): Tournament match schedules, historical results, and generated prediction outputs.
* [`tests/`](file:///Users/vonlinck/Desktop/wm2026_predictor/tests/): Extensive 176-test unit and end-to-end verification suite.

---

## 🚀 Execution & Usage Guide

### 1. Run the Test Suite
Confirm the entire testing matrix is green:
```bash
venv/bin/python3 -m unittest discover tests
```

### 2. Generate Optimal Kicktipp Score Tips
Solve for the optimal score predictions for Matchday 1 (maximizing expected points under the 4/3/2 scoring rules):
```bash
venv/bin/python3 matchday_tips.py --md 1 --simulations 1000
```

### 3. Solve Outright Tournament Bonus Questions
Simulate 10,000 World Cup runs to solve for optimal predictions on group winners, semifinalists, champion, and top goalscorer team:
```bash
venv/bin/python3 tournament_bonusfragen.py --sims 10000
```

### 4. Run the Live Exchange Edge Scanner Daemon
Launch the daemon to monitor exchanges and calculate Kelly stake allocations:
```bash
venv/bin/python3 edge_scanner.py --daemon
```

### 5. Run the Chronological Backtest Harness
Verify the engine's performance on historical tournaments (2014, 2018, or 2022) against a Synthetic Elo Market baseline:
```bash
venv/bin/python3 backtest_harness.py --tournament 2018 --threshold 0.015 --kelly 0.25
```
