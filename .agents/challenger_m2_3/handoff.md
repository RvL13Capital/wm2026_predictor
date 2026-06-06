# Handoff Report — Challenger M2 3

## 1. Observation
We performed verification of the advanced probability engine and contextual curves in `predictor.py` under standard test suites and custom extreme value stress testing.

### Test Results
- **Standard Unit/E2E tests**: Passed successfully.
  - `python3 -m unittest tests/test_predictor.py` -> 13 tests passed.
  - `python3 -m unittest tests/test_tier1_feature_coverage.py` -> 20 tests passed (5 skipped).
  - `python3 -m unittest tests/test_tier2_boundary_corner.py` -> 20 tests passed (5 skipped).
  - `python3 -m unittest tests/test_tier3_cross_feature.py` -> 4 tests passed (1 skipped).
  - `python3 -m unittest tests/test_tier4_real_world.py` -> 5 tests passed.
  - *Note*: Skipped tests are related to the planned Backtesting Suite (`backtest.py` is not yet implemented), which is expected.
- **Project Verification Script**: Running `python3 verify_engine.py` completed, but revealed an unhandled warning/crash on temperature near boundary:
  ```
  WBGT at Temp=-237.3000000000001C failed with: OverflowError: math range error
  ```
- **Custom Stress Testing Suite**: Created and ran `tests/stress_test_harness.py` containing edge-case boundary parameters. The execution results:
  ```
  --- Running Altitude Extremes Stress ---
  calculate_altitude_factor(1500, -700) = 0.5
  calculate_altitude_factor(1500, -10000) failed: OverflowError: math range error
  calculate_altitude_factor(inf, 0) = 0.5

  --- Running Dixon-Coles Extremes Stress ---
  get_dixon_coles_adjustment(0, 0, 1.5, 1.2, -100.0) = 181.0
  get_dixon_coles_adjustment(0, 0, 1.5, 1.2, 100.0) = 0.0
  get_dixon_coles_adjustment(0, 0, 1.5, 1.2, inf) = 0.0
  get_dixon_coles_adjustment(0, 0, 1.5, 1.2, nan) = 0.0

  --- Running Fan Support Extremes Stress ---
  get_adjusted_lambdas with extreme fans failed: OverflowError: math range error

  --- Running Negative Binomial Extremes Stress ---
  negative_binomial_probability(2, 1.5, -2.5) = 0.25102143016698364
  negative_binomial_probability(2, 1.5, 1e300) = 5.000000000000393e-301
  negative_binomial_probability(2, 1.5, inf) failed: ValueError: expected a noninteger or positive integer, got 0.0
  negative_binomial_probability(2, 1.5, nan) = nan
  negative_binomial_probability(2, inf, 0.5) failed: ValueError: expected a positive input, got 0.0

  --- Running Complete Pipeline Crash Stress ---
  solve_optimal_tip with extreme config completed. Top tip: (0, 0) EV=2.0

  --- Running Poisson Extremes Stress ---
  poisson_probability(5, 1e15) = 0.0
  poisson_probability(5, inf) = nan
  poisson_probability(5, nan) = nan
  poisson_probability(1000000, 1.5) = 0.0

  --- Running Thermal Extremes Stress ---
  calculate_thermal_factor(-273.15, 50, 0) = 0.5 (wbgt=1.6812150902417264e+57)
  calculate_thermal_factor(-237.3, 50, 0) = 1.0 (wbgt=-130.60909999999998)
  calculate_thermal_factor(-237.3000000000001, 50, 0) failed: OverflowError: math range error
  calculate_thermal_factor(-238.0, 50, 0) failed: OverflowError: math range error
  calculate_thermal_factor(inf, 50, 0) = 1.0
  calculate_thermal_factor(30, 50, -5000) failed: OverflowError: math range error

  --- Running Travel Extremes Stress ---
  calculate_travel_penalty(-1e6, -1e6, -100) = 0.3
  calculate_travel_penalty(inf, 1000, 5) = 0.0
  calculate_travel_penalty(5, inf, 5) = 0.011156508007421491
  ```

---

## 2. Logic Chain
We reasoned from our direct observations to assess the numeric stability claims of the prediction engine:
1. **Observation 3 (Altitude Loss)**: `calculate_altitude_factor(1500, -10000)` threw `OverflowError`.
   - **Reasoning**: In `predictor.py` line 103, `remaining_loss = base_loss * math.exp(-acclimation_days / 7.0)`. If `acclimation_days` is an extremely negative number, `-acclimation_days / 7.0` becomes a large positive value. Since `math.exp` raises `OverflowError` for exponents $> 709.78$, this causes an unhandled crash.
2. **Observation 3 (Thermal Loss)**: `calculate_thermal_factor(30, 50, -5000)` threw `OverflowError`.
   - **Reasoning**: In `predictor.py` line 120, `remaining_loss = base_loss * math.exp(-heat_acclimation_days / 5.0)`. Similar to altitude acclimation, an extremely negative value overflows the exponent in `math.exp`.
3. **Observation 1 & 3 (WBGT/Thermal Boundary)**: Temperatures slightly below `-237.3` crash `calculate_thermal_factor`.
   - **Reasoning**: In `predictor.py` line 111, `e = (humidity / 100.0) * 6.1078 * math.exp((17.27 * temperature) / denom)` where `denom = temperature + 237.3`. The code has a patch for exactly `denom == 0` (setting it to `1e-9`), but in the neighborhood `[-243.07, -237.30)`, `denom` is a tiny negative float, making the exponent a very large positive number. This overflows `math.exp`, raising `OverflowError`.
4. **Observation 3 (Negative Binomial)**: `negative_binomial_probability` crashed with `ValueError` on `alpha = inf` and `mu = inf`.
   - **Reasoning**:
     - For `alpha = inf`, `r = 1.0 / alpha` is `0.0`. The code calls `math.lgamma(r)` which evaluates `math.lgamma(0.0)`, throwing a `ValueError` because the gamma function is undefined/infinite at 0.
     - For `mu = inf` and `alpha > 0`, `p = 1.0 / (1.0 + alpha * mu)` is `0.0`. The code evaluates `math.log(p)` which evaluates `math.log(0.0)`, raising `ValueError` (math domain error).
5. **Observation 3 (Fan Support)**: `get_adjusted_lambdas` crashed with `OverflowError` on `fan_support_pct = 1e5`.
   - **Reasoning**: `net_fan_margin = fan_support_pct - opponent_fan_support_pct` becomes huge. Since this margin is not clamped, `delta_att_fan = c_att_fan * net_fan_margin` becomes huge, causing `math.exp(delta_att_A + delta_def_B)` to overflow and crash the adjustment logic.
6. **Observation 3 (Dixon-Coles & Python Order Quirks)**: `get_dixon_coles_adjustment(..., nan)` returns `0.0` successfully without crashing.
   - **Reasoning**: In `predictor.py` line 281, `return max(0.0, factor)`. If `factor` is `nan` (due to `rho` being `nan`), Python's `max(0.0, nan)` returns `0.0` because `nan >= 0.0` is False, so it falls back to the first argument. If the arguments were reversed to `max(factor, 0.0)`, it would evaluate to `nan`. Thus, this safeguard depends on a fragile python comparison quirk.

---

## 3. Caveats
- No code was modified in the implementation directory, strictly complying with the "Review-only" mandate. All bugs must be fixed by implementer agents.
- Backtesting CSVs or pipeline modules (`backtest.py`) do not exist yet; hence backtester-specific tests were skipped.
- High-volume scaling was not checked beyond standard unittest coverage limits.

---

## 4. Conclusion (Adversarial Challenge Report)

### Overall Risk Assessment: HIGH
The advanced probability engine contains multiple unhandled math domain boundaries and exponential growth bugs that can easily crash the application under extreme or malicious parameters. The fixes applied are only partially effective.

### Key Challenges

#### [High] Challenge 1: Thermal Boundary Neighborhood Overflow
- **Assumption challenged**: The division-by-zero check for `temperature = -237.3` prevents all WBGT calculations from crashing.
- **Attack scenario**: Feeding a temperature in the neighborhood `[-243.07, -237.30)` causes `denom` to be a small negative float, driving the exponent to overflow `math.exp`.
- **Blast radius**: Crashes `calculate_wbgt` and `get_adjusted_lambdas` during match simulation.
- **Mitigation**: Physically clamp temperature to a safe interval (e.g. `[-50.0, 60.0]`) or wrap the exponent math in a try-except block to handle `OverflowError`.

#### [High] Challenge 2: Unclamped Acclimation Decay Curves
- **Assumption challenged**: Environmental acclimation inputs are safe from causing numerical crashes.
- **Attack scenario**: Passing extremely negative values for `accl_days` or `heat_accl_days` drives exponential decay curves `math.exp(-days / C)` to infinity, overflowing `math.exp`.
- **Blast radius**: Crashes environmental adjustment calculations.
- **Mitigation**: Sanitize acclimation days using `max(0.0, acclimation_days)`.

#### [Medium] Challenge 3: Unclamped Fan Support Percentage
- **Assumption challenged**: Fan support inputs do not compromise solver stability.
- **Attack scenario**: Passing a fan support percentage of `1e5` results in a massive net fan margin, causing the adjustment exponent to overflow.
- **Blast radius**: Crashes `get_adjusted_lambdas`.
- **Mitigation**: Clamp `fan_support_pct` to `[0.0, 1.0]`.

#### [Medium] Challenge 4: Negative Binomial Infinite Bounds
- **Assumption challenged**: Parameter fallbacks in the Negative Binomial model handle all extreme parameter states.
- **Attack scenario**: Setting `alpha = float('inf')` or `mu = float('inf')` bypasses the Poisson fallback checks but crashes `math.lgamma(0.0)` or `math.log(0.0)`.
- **Blast radius**: Crashes probability grid generation.
- **Mitigation**: Check for infinite parameters `math.isinf(alpha)` or `math.isinf(mu)` and route them to Poisson or return clean errors.

#### [Low] Challenge 5: Fragile Ordering in max(0.0, factor)
- **Assumption challenged**: Dixon-Coles adjustment is robustly protected against NaN propagation.
- **Attack scenario**: If `factor` becomes `nan` (due to `rho = nan`), `max(0.0, factor)` returns `0.0` due to Python's argument order. A minor refactoring to `max(factor, 0.0)` would break this protection and propagate NaNs.
- **Blast radius**: Potential latent bug if code is refactored.
- **Mitigation**: Explicitly check for `math.isnan(factor)`.

---

## 5. Verification Method
To independently verify these findings, run:
1. The custom stress test suite in the tests folder:
   ```bash
   python3 -m unittest tests/stress_test_harness.py
   ```
2. The default verification script:
   ```bash
   python3 verify_engine.py
   ```
Observe the raised `OverflowError` and `ValueError` outputs.
