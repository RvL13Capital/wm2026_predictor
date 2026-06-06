# Handoff Report

## 1. Observation
- The target file `predictor.py` was inspected at `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`.
- In `predictor.py`, the solver function `solve_optimal_tip(lam_A, lam_B, rho=0.0, max_goals=12, max_tip=6)` (lines 38-98) builds a 2D probability matrix using Poisson probability `poisson_prob(g_A, lam_A) * poisson_prob(g_B, lam_B)` (line 50) and adjusts it using a Dixon-Coles coefficient `rho` (lines 56-64).
- The current implementation accepts static float values for `lambdaA` and `lambdaB` via CLI argument parsing in `main()` (lines 104-105):
  ```python
  parser.add_argument("--lambdaA", type=float, required=True, help="Torerwartung lambda für Team A (xG)")
  parser.add_argument("--lambdaB", type=float, required=True, help="Torerwartung lambda für Team B (xG)")
  ```
- No adjustments for travel distance, rest days, timezone differences, host advantage, or fan support are currently implemented in `predictor.py`.
- The `PROJECT.md` file at `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/PROJECT.md` documents under Milestone 2 (line 13) that the engine should support bivariate Poisson with Dixon-Coles/NegBinomial plus contextual factors (elevation, climate, travel, host support).

## 2. Logic Chain
- To implement Milestone 2 requirements regarding travel, rest days, fan support, and host advantages, we must design mathematical models that modify the base input lambdas before constructing the Poisson grid.
- Expected goals ($\lambda$) must remain strictly positive. Therefore, a log-additive (exponential multiplier) model is selected to guarantee positivity and allow natural additivity of different penalty/bonus factors in log-space:
  $$\lambda_{\text{adjusted}} = \lambda_{\text{base}} \cdot e^{\Delta_{\text{att}} + \Delta_{\text{def, opponent}}}$$
- Fatigue from travel is a function of travel distance (sub-linear saturation curve), timezone transitions (circadian shift, asymmetric direction effect), and rest days (recovery decay):
  - A rest deficit penalty $P_{\text{rest}}$ is designed to grow convexly for $r < 5$ days.
  - A physical distance penalty $P_{\text{dist}}$ saturates with distance and decays exponentially with rest days.
  - A circadian disruption penalty $P_{\text{tz}}$ takes into account direction of travel and adaptation time.
- Host advantages and fan support skew team efficiency:
  - Host status is split into discrete categories (`True Home`, `Co-Host`, `Neutral`) with fixed log-scale coefficients.
  - Fan support is modeled continuously using the net crowd percentage margin: $\Delta S = S_i - S_j$.
- Function signatures were defined to isolate these calculations and can be seamlessly integrated into `predictor.py`.

## 3. Caveats
- Elevation/climate: The prompt specifically requested travel/rest days and host/fan advantage models. Ground elevation (which also impacts lung capacity and ball aerodynamics) and climate (temperature/humidity) are listed under Milestone 2 in `PROJECT.md` but are not included in this proposal to keep the scope tight.
- Parameter calibration: The coefficients ($\theta_{\text{host}}$, $C_{\text{fan}}$, $c_{\text{att, travel}}$, etc.) are proposed based on typical football analytics benchmarks but should be fine-tuned or fitted using backtesting data (Milestone 4).

## 4. Conclusion
- We have delivered a complete mathematical framework and design document in `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/explorer_m2_3/analysis.md`.
- The design includes detailed continuous formulations for travel penalty and host/fan advantage, clear python signatures, and a walk-through calibration scenario showing how base lambdas of $(1.5, 1.5)$ are successfully transformed into $(1.85, 1.13)$ under high-disadvantage scenarios.

## 5. Verification Method
- **File Inspection**: Verify that the design report `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/explorer_m2_3/analysis.md` exists and contains the math formulas and code signatures.
- **Mathematical Integrity**: Verify the Scenario 2 manual calculations in the report. If the equations are implemented in code, passing the same inputs must yield $\lambda_{\text{adj, A}} \approx 1.851$ and $\lambda_{\text{adj, B}} \approx 1.134$.
- **Invalidation Condition**: If any coefficient yields negative expected goals, or if the travel penalty exceeds the capped value (30%) under extreme conditions, the calibration constants must be adjusted.
