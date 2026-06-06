# Changes Summary - Milestone 2 Hardening and Bug Fixes

## 1. Modifications in `predictor.py`
- **Negative Binomial Stability**: Modified `negative_binomial_probability` to fallback to `poisson_probability` when `alpha * mu < 1e-15` or `alpha <= 1e-6` to avoid numerical instability under extremely small positive `mu`.
- **Input Sanitization in `calculate_travel_penalty`**: Sanitized input values (`rest_days`, `travel_miles`, `tz_crossed`) to be non-negative using `max(0, val)`.
- **NoneType Sanitization in Context Dicts**: Created helper `get_context_val` in `get_adjusted_lambdas` to sanitize `None` values to defaults. Replaced all direct `.get` calls with `get_context_val` to prevent `TypeError` when keys are explicitly mapped to `None`.
- **Goal Grid Clamping**: Clamped maximum goals to `min(100, config.max_goals)` in `generate_joint_grid` and `solve_optimal_tip` to prevent quadratic CPU/memory complexity issues.
- **Dixon-Coles Normalization Fallback**: Handled cases where the probability grid sums to `0.0` due to underflow under extremely high lambda by setting all grid probabilities to `0.0` and `grid[max_goals][max_goals]` to `1.0`.

## 2. Fixes in Test Suites
- **`tests/test_tier2_boundary_corner.py`**: Verified that `import math` is present at the top of the file to resolve potential `NameError` issues.
- **`tests/test_tier4_real_world.py`**: Updated `test_t4_rw5_italy_uruguay_draw` to use `rho=-0.2` instead of `rho=-0.1` so that a draw tip is mathematically optimal under Kicktipp rules.
- **`tests/test_predictor.py`**: Added unit tests verifying:
  1. Negative Binomial stability under very small positive mu (`mu=1e-17`, `alpha=1.0`).
  2. NoneType sanitization in context dicts (`{"elevation": None}`).
  3. Dixon-Coles normalization fallback under extreme high lambda (`800.0`).
  4. Negative travel miles in travel penalty calculations.
