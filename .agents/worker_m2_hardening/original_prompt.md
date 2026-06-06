## 2026-06-03T17:34:49Z

You are a teamwork_preview_worker subagent.
Your role: 'Prediction Engine Hardener'.
Your working directory is: `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/worker_m2_hardening/`
Your task is to harden `predictor.py` against mathematical domain errors, unhandled boundary values, and parameter overflows identified during adversarial stress testing:

1. **WBGT Temperature Range Neighborhood**:
   - In `calculate_wbgt`, temperature values slightly below -237.3 (where `denom = temperature + 237.3` is negative and close to zero) make `(17.27 * temperature) / denom` a huge positive exponent, causing `math.exp` to raise `OverflowError`.
   - Action: Clamp the `temperature` parameter to a safe physical range (e.g., `[-50.0, 60.0]`) in `calculate_wbgt`. Clamping `temperature` to `[-50.0, 60.0]` is recommended since it represents real-world physical bounds. Also protect `calculate_wbgt` against division-by-zero or overflow issues by using a try-except block wrapping the exponential calculation and returning a fallback WBGT value if it fails.

2. **Acclimation Curves Overflow**:
   - In `calculate_altitude_factor` and `calculate_thermal_factor`, extremely negative `acclimation_days` or `heat_acclimation_days` passed in the context cause `-acclimation_days / 7.0` (or `-heat_acclimation_days / 5.0`) to be large positive values, causing `math.exp` to overflow.
   - Action: Sanitize/clamp `acclimation_days` and `heat_acclimation_days` to be non-negative (e.g., `max(0.0, acclimation_days)`) to prevent this.

3. **Fan Support Overflow**:
   - In `get_adjusted_lambdas` / `calculate_context_adjustments`, if extreme fan support values are passed (e.g. `1e5`), it results in huge adjusted lambda values that overflow `math.exp`.
   - Action: Clamp `fan_support_pct` and `opponent_fan_support_pct` to the range `[0.0, 1.0]`. Also clamp `delta_att` and `delta_def` inside `calculate_context_adjustments` or `get_adjusted_lambdas` so that they do not result in extremely large lambda values that would overflow `math.exp(delta_att_A + delta_def_B)`.

4. **Negative Binomial Parameter stability**:
   - In `negative_binomial_probability`, check for `inf` or `nan` in `alpha` or `mu`. Specifically:
     - If `math.isinf(alpha)` or `math.isnan(alpha)` or `math.isinf(mu)` or `math.isnan(mu)` or if `alpha * mu > 1e15` (which makes `p` evaluate to 0.0, causing `math.log(0.0)` domain errors):
       - If `math.isinf(alpha)` or `alpha > 1e15` or `math.isnan(alpha)`: return poisson_probability(k, mu) if mu is finite (if mu is not finite, handle safely).
       - If `math.isinf(mu)` or `mu > 1e15` or `math.isnan(mu)`: return a Poisson fallback or a safe fallback probability (e.g., return 0.0 if k > 0 else 0.0, or poisson_probability).
       - If `alpha * mu > 1e15` (meaning dispersion is extremely large relative to the mean): handle this condition safely to prevent `math.log(0.0)` or `math.lgamma(0)` crashes. For example, return `poisson_probability(k, mu)` or return a safe fallback probability.

5. **Dixon-Coles NaN/infinite check**:
   - In `get_dixon_coles_adjustment`, check if any inputs `a_a`, `a_b`, or `rho` are `nan` or `inf`.
   - Action: If `math.isnan(rho)` or `math.isinf(rho)` or `math.isnan(a_a)` or `math.isinf(a_a)` or `math.isnan(a_b)` or `math.isinf(a_b)`, or if the calculated adjustment `factor` becomes `nan` or `inf`, return a safe fallback value (e.g., `1.0` or similar). Also ensure `math.isnan` is explicitly checked instead of relying on Python's fragile comparison ordering in `max(0.0, factor)`.

6. **Negative max_goals / grid size**:
   - In `generate_joint_grid` and `solve_optimal_tip`, clamp `config.max_goals` to a non-negative value (e.g., `max_goals = max(0, min(100, config.max_goals))`) so the grid dictionary is properly initialized.

Verify your changes:
- Run the standard unit test suite: `python3 -m unittest tests/test_predictor.py`
- Run the E2E/Tier tests:
  `python3 -m unittest tests/test_tier1_feature_coverage.py`
  `python3 -m unittest tests/test_tier2_boundary_corner.py`
  `python3 -m unittest tests/test_tier3_cross_feature.py`
  `python3 -m unittest tests/test_tier4_real_world.py`
- Run the verify engine script: `python3 verify_engine.py`
- Run the custom stress test suite in `tests/stress_test_harness.py` to ensure all overflows and domain errors are completely resolved.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Please report back when done, including the command outputs and a detailed handoff report in your directory.
