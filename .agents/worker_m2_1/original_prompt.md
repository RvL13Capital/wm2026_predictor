## 2026-06-03T17:11:34Z
You are the implementation worker for Milestone 2.
Your working directory is `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/worker_m2_1/`.
Your task is to implement the Advanced Probability Engine & Contextual Factors inside `predictor.py`.

Please follow these instructions carefully:
1. Read the design specification file `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/sub_orch_m2_1/M2_DESIGN.md` for the exact mathematical formulas, data structures, and function signatures.
2. Implement the following functions and classes in `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`:
   - `ModelDistribution` Enum and `MatchModelConfig` dataclass.
   - `poisson_probability(k, lam)` using `math.lgamma` to avoid overflow.
   - `negative_binomial_probability(k, mu, alpha)` with a fallback to `poisson_probability` when alpha <= 1e-6.
   - `calculate_altitude_factor(elevation, acclimation_days)`
   - `calculate_wbgt(temperature, humidity)`
   - `calculate_thermal_factor(temperature, humidity, heat_acclimation_days)`
   - `calculate_travel_penalty(rest_days, travel_miles, tz_crossed, direction)`
   - `calculate_context_adjustments(...)`
   - `get_adjusted_lambdas(...)`
   - `get_dixon_coles_adjustment(x, y, a_a, a_b, rho)` (using the Generalized Dixon-Coles formulation).
   - `generate_joint_grid(config)` and update `solve_optimal_tip(config)` to support these adjustments.
3. Update `main()` in `predictor.py` to parse all new CLI arguments specified in `M2_DESIGN.md`. Ensure that if no additional arguments are supplied, the baseline Poisson model is run.
4. Create a test suite in `tests/test_predictor.py` containing:
   - Test cases verifying the mathematical validity and edge cases of `poisson_probability` and `negative_binomial_probability`.
   - Test cases verifying the sum-to-one property of the generated joint probability grids for both Poisson and Negative Binomial models.
   - Test cases verifying the altitude, climate, travel penalty, and fan/host adjustments against the mathematical calibration examples in `M2_DESIGN.md`.
5. Run the test suite using `pytest` (or `python -m unittest`) and verify that all unit tests pass with 100% success.
6. Write a summary of changes in `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/worker_m2_1/changes.md`.

MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Report back once the implementation is complete and tests pass.
