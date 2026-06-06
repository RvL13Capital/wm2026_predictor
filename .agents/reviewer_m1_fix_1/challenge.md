## Challenge Summary

**Overall risk assessment**: LOW

All analyzed aspects of the World Cup 2026 Prediction Engine and its E2E testing infrastructure have been stress-tested. The design exhibits high resilience against edge cases, extreme inputs, and model deviations.

---

## Challenges

### [Low] Challenge 1: Dixon-Coles Parameter (rho) Out of Bounds
- **Assumption challenged**: The Dixon-Coles correlation parameter ($\rho$) is assumed to be reasonably small (typically in $[-0.1, 0.1]$).
- **Attack scenario**: If a user runs the prediction engine CLI with a highly distorted $\rho$ value (e.g., `--rho 5.0` or `--rho -5.0`), the Dixon-Coles adjustment factors could become negative.
- **Blast radius**: If a negative factor were applied, cell probabilities in the grid could become negative, leading to negative outcome probabilities and invalid expected point calculations (EV).
- **Mitigation**: The code in `predictor.py` (Line 267) safely clips the factor using `max(0.0, factor)`. This successfully mitigates the issue, maintaining probability bounds [0, 1] even under highly adversarial inputs.

### [Low] Challenge 2: Environmental Temperature and Elevation Extreme Scaling
- **Assumption challenged**: Elevations and wet-bulb temperatures are assumed to lie within habitable ranges.
- **Attack scenario**: Inputs simulating elevations at 20,000 meters or ambient temperatures at 45°C with 95% humidity.
- **Blast radius**: Performance degradation functions could compute negative or extremely small capacity factors, resulting in exponential decay that reduces team expected goals ($\lambda$) close to zero or negative.
- **Mitigation**: The functions `calculate_altitude_factor` (Line 105) and `calculate_thermal_factor` (Line 122) strictly cap the resulting capacity factor to $[0.5, 1.0]$. This prevents complete team neutralization and avoids division-by-zero or negative Torerwartung.

### [Low] Challenge 3: Incomplete Solver Grid Search Boundary
- **Assumption challenged**: The grid limits for goal calculations (`max_goals`) and maximum tips (`max_tip`) are large enough to capture the probability mass.
- **Attack scenario**: When `max_tip` is configured to be significantly larger than `max_goals` (e.g., `--max_goals 5 --max_tip 10`), the probability of scoring above 5 goals is zero (due to truncation), and the solver might select an empty or skewed optimal tip.
- **Blast radius**: Minor distortion in expected value calculation due to probability truncation at the grid edge.
- **Mitigation**: The probability grid is normalized to sum to 1.0 over the truncated space (Line 285–289). This ensures that expected values remain mathematically valid, even if the grid size is restricted.

---

## Stress Test Results

- **Extreme High Lambda (15.0)** → Expected: No floating point overflow, sum of outcomes equals 1.0 → Actual: Poisson log probability log-gamma formulation prevents overflow, sum equals 1.0 → **PASS**
- **Negative Dixon-Coles Correction Factor** → Expected: Cell probability is clipped to 0, no negative probabilities → Actual: Capped at 0.0, probability bounds preserved → **PASS**
- **Rest Days = 0** → Expected: Rest day travel penalty does not exceed maximum allowable value → Actual: Penalty successfully capped at 0.30 → **PASS**
- **Altitude = 20,000m** → Expected: Altitude factor is capped at 0.5 → Actual: Capped at 0.5 → **PASS**
