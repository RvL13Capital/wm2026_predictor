# Project: World Cup 2026 Prediction Engine

## Architecture
- Refactored `predictor.py` with advanced models and contextual factors.
- `solver.py` for the Kicktipp EV maximizing solver.
- `backtest.py` for backtesting comparison against the baseline.
- `tests/` for E2E and unit tests.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | E2E Testing Track | Design and build the E2E test suite (Tiers 1-4). Outputs: `TEST_INFRA.md`, `tests/run_e2e.py`, `TEST_READY.md`, and E2E test suite in `tests/` | None | DONE (Conv: 4606a3e4-1e6e-445b-8297-9307c4ee54d6) |
| 2 | Advanced Probability Engine | Bivariate Poisson with Dixon-Coles or NegBinomial + contextual factors (elevation, climate, travel, host support) | None | DONE (Conv: 4f3269e2-ee07-40b5-a16d-ccb850258a93 / 5e253a0d-1ef6-433b-8ff5-37ec851b88d5) |
| 3 | Kicktipp Solver | EV Maximization under 4/3/2 scoring rules | M2 | DONE (Conv: 5ec5b1fc-eba4-46ab-9594-0883a7e5092d) |
| 4 | Backtesting Suite | Backtest optimized model vs baseline on WC 2022 data | M2, M3 | DONE (Conv: 1c17fbc0-a37c-479d-9f52-97f97dfa44dc) |
| 5 | E2E Validation & Adversarial Hardening | E2E testing validation + Tier 5 coverage audit and fix | M1, M4 | DONE (Conv: 1ff89a9c-a7fd-4f6c-8d6a-d4b718379ee3) |

## Detailed Requirements Mapping

### R1. Advanced Probability Engine
The engine replaces the simplistic independent Poisson model to resolve draw bias and overdispersion:
- **Bivariate Poisson with Dixon-Coles Adjustments**: Adjusts probabilities for low scores (0-0, 1-0, 0-1, 1-1) using a correlation parameter ($\rho$) to properly model draw tendencies.
- **Negative Binomial Model**: Handles overdispersion (high-scoring outliers) where variance exceeds the mean.

### R2. Contextual WM-Specific Factors
Incorporates mathematical correction factors to adjust team strength parameters dynamically:
- **Altitude Acclimation Curves**: Stadium elevations impact player endurance and ball physics, modeled using acclimation curves.
- **Climatic Conditions**: Adjusts team performance based on heat and humidity index (wet-bulb temperature equivalents).
- **Travel and Rest Days**: Penalizes teams based on travel mileage and timezone transitions relative to rest days.
- **Fan Support / Host Advantage**: Adjusts base strength parameters to account for home-field / host country support.

### R3. Kicktipp Solver (EV Maximization)
Strictly implements the 4/3/2 scoring system solver:
- For any pair of team strength inputs, the solver iterates over possible score tips $(t_A, t_B)$ and outputs the tip maximizing expected points:
  $$E(t) = 4P(\text{Exact}) + 3P(\text{Diff}) + 2P(\text{Tendenz})$$
- Points rules:
  - **4 Points**: Exact score ($t_A = g_A$ and $t_B = g_B$)
  - **3 Points**: Correct goal difference and tendency ($t_A - t_B = g_A - g_B$ and $\text{sign}(t_A - t_B) = \text{sign}(g_A - g_B)$)
  - **2 Points**: Correct tendency only ($\text{sign}(t_A - t_B) = \text{sign}(g_A - g_B)$)
  - **0 Points**: Otherwise

### R4. Backtesting and Validation
Provides a backtesting suite (`backtest.py`) that:
- Evaluates the model using historical data (e.g., World Cup 2022 match results).
- Compares its simulated Kicktipp points performance against the baseline independent Poisson model.
- Verifies if the optimized model achieves higher total points than the baseline on historical match data.

## Interface Contracts
### predictor.py ↔ solver.py
- **Prediction engine** outputs a full probability distribution over scores (up to `max_goals` × `max_goals` grid, e.g., $12 \times 12$).
- **Solver** takes this probability distribution and outputs the optimal tip $(t_A, t_B)$ maximizing Kicktipp EV.

## Code Layout
- `predictor.py`: probability modeling (implements Poisson, Dixon-Coles, Negative Binomial, and contextual factors).
- `solver.py`: Kicktipp solver (implements EV optimization).
- `backtest.py`: backtesting runner (runs historical evaluations and outputs comparison reports).
- `tests/`: test suite (contains unit and end-to-end tests).
