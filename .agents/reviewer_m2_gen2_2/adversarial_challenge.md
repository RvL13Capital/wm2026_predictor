# Adversarial Challenge Report

**Overall Risk Assessment**: LOW

This report stress-tests assumptions, constraints, and potential failure modes of the probability engine and solver in `predictor.py`.

## Challenges

### 1. Zero/Negative Alpha or Mu in Negative Binomial
- **Assumption Challenged**: Negative Binomial parameters $\mu$ and $\alpha$ are non-negative.
- **Attack Scenario**: An upstream caller passes negative or zero $\mu$ or $\alpha$.
- **Analysis**:
  - If $\mu \le 0.0$, the function returns `1.0 if k == 0 else 0.0`. This is mathematically correct since a distribution with mean $0.0$ has all its weight at $0$.
  - If $\alpha \le 1e-6$, the function falls back to Poisson distribution with mean $\mu$.
  - If $\alpha$ is negative, it will satisfy `alpha <= 1e-6` and fall back to the Poisson distribution, preventing domain errors in $\log(p)$ or $\text{lgamma}(r)$ where $r = 1/\alpha$.
- **Mitigation**: Robust parameters check and fallback mechanism successfully prevent crashes.

### 2. Large Input Parameters (Inflation Attacks)
- **Assumption Challenged**: Expected goals (lambdas) and environmental factor coordinates are within typical bounds.
- **Attack Scenario**: Extremely large lambdas (e.g. $1e300$) or altitudes (e.g. $1e9$ meters) are provided.
- **Analysis**:
  - Large altitudes: `elevation` is clamped in `calculate_altitude_factor` via `h = min(1000.0, (elevation - 1000.0)/1000.0)`. Thus, $h$ never exceeds $1000.0$, and the altitude factor is clamped to $[0.5, 1.0]$.
  - Large temperature/humidity: Clamped to safe ranges $[-50.0, 60.0]$ and $[0.0, 100.0]$ in `calculate_wbgt`, preventing overflow in the exponential saturated vapor pressure calculation.
  - Large base lambdas: Clamped to $[0.0, 10000.0]$ in `get_adjusted_lambdas`.
  - Large grid size: Capped at `100` in both `generate_joint_grid` and `solve_optimal_tip`.
- **Mitigation**: Clamping and fallback guards prevent performance degradation and overflow.

### 3. Dixon-Coles Parameter Normalization
- **Assumption Challenged**: Dixon-Coles parameter $\rho$ lies in the typical interval $[-1.0, 1.0]$.
- **Attack Scenario**: A user specifies an extreme $\rho = \pm 10.0$ or a team has extremely high base lambdas that blow up $a_a$ and $a_b$.
- **Analysis**:
  - In `get_dixon_coles_adjustment`, if the adjustment factor evaluates to negative or NaN/Inf, the function returns `max(0.0, factor)`.
  - If the joint probabilities end up summing to $\le 0.0$, `generate_joint_grid` detects `total_prob <= 0.0` and falls back to setting the cell `(max_goals, max_goals) = 1.0` and all other cells to `0.0`.
- **Mitigation**: Normalization and fallback guard against division-by-zero or empty probability spaces.

## Stress Test Scenarios

### Scenario 1: Denominator Boundary in calculate_wbgt
- **Inputs**: `temperature = -237.3`
- **Expected Behavior**: No division-by-zero or crash.
- **Actual/Predicted Behavior**: Clamped to $-50.0$. `denom = -50.0 + 237.3 = 187.3`. Correctly computed WBGT without division-by-zero.
- **Result**: PASS

### Scenario 2: Underflow of Poisson Probability
- **Inputs**: `k = 50, lam = 1e-15`
- **Expected Behavior**: Evaluates to `0.0` without raising ValueError/OverflowError.
- **Actual/Predicted Behavior**: `log_p = 50 * math.log(1e-15) - 1e-15 - lgamma(51)` which is a large negative number. `math.exp(log_p)` underflows to `0.0` cleanly.
- **Result**: PASS

### Scenario 3: Negative rest days or travel miles
- **Inputs**: `rest_days = -5.0`, `travel_miles = -100.0`
- **Expected Behavior**: Sanitized to `0.0` and returns valid penalty.
- **Actual/Predicted Behavior**: Clamped via `max(0.0, rest_days)` and `max(0.0, travel_miles)`. Returns a valid travel penalty.
- **Result**: PASS
