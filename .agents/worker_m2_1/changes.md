# Summary of Changes

## Modified Files
*   `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`

## Detailed Implementation Summary

1.  **Added Model Configuration Classes**:
    *   `ModelDistribution` Enum: Defines standard distributions (`POISSON`, `NEGATIVE_BINOMIAL`).
    *   `MatchModelConfig` Dataclass: Standardizes model parameters including distribution type, expected goals, dispersion parameters, Dixon-Coles coefficient, and limits.

2.  **Implemented Numerical Probability Functions**:
    *   `poisson_probability(k, lam)`: Uses `math.lgamma` for stable probability computation.
    *   `negative_binomial_probability(k, mu, alpha)`: Implements Negative Binomial model using `math.lgamma` with a fallback to Poisson if dispersion parameter $\alpha \le 10^{-6}$.
    *   `compute_marginal_probability`: Unified entry point to fetch marginal values.

3.  **Physiological & Contextual Degradation Curves**:
    *   `calculate_altitude_factor(elevation, acclimation_days)`: Decreases aerobic capacity above 1000m threshold with exponential acclimation decay.
    *   `calculate_wbgt(temperature, humidity)`: Wet-Bulb Globe Temperature approximation using the Australian BOM formulation.
    *   `calculate_thermal_factor(temperature, humidity, heat_acclimation_days)`: Decreases capacity above 20.0°C WBGT threshold with rapid exponential acclimation decay.
    *   `calculate_travel_penalty(rest_days, travel_miles, tz_crossed, direction)`: Multi-factor compounding travel penalty (rest deficit, distance exponential, timezone fatigue weighted by direction).
    *   `calculate_context_adjustments(...)`: Unified log-linear contextual adjustments (host status, travel penalty scaling, fan margin support).
    *   `get_adjusted_lambdas(lambda_A_base, lambda_B_base, teamA_context, teamB_context)`: Unified log-linear expected goals adjustments combining environmental and context components.

4.  **Dixon-Coles Adjustment & Grid Solver**:
    *   `get_dixon_coles_adjustment(x, y, a_a, a_b, rho)`: Generalized adjustment.
    *   `generate_joint_grid(config)`: Builds joint probability matrix using either model and normalizes it over truncated goal limit.
    *   `solve_optimal_tip(config_or_lamA, ...)`: Backwards compatible interface returning EV-sorted tips, top 5 scores, and outcomes.

5.  **CLI Parser Update**:
    *   Added CLI arguments to support model distribution, dispersion, venue conditions (elevation, temp, humidity), travel parameters (rest days, miles, tz crossed, direction), host status, and fan percentages.

## Added Tests
*   `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_predictor.py`
    *   Verifies Poisson and Negative Binomial probability calculations.
    *   Checks the sum-to-one property of truncated joint grids.
    *   Checks altitude, WBGT, heat, travel, host status, and fan support adjustments against design calibration examples.
