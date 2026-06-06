## 2026-06-03T17:26:56Z
You are the implementation worker for Milestone 2 bug fixes and hardening.
Your working directory is `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/worker_m2_3/`.

Please apply the following changes:

1. In `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`:
   a. In `negative_binomial_probability` (around line 35), change the condition:
   ```python
       if alpha <= 1e-6:
           return poisson_probability(k, mu)
   ```
   to:
   ```python
       if alpha <= 1e-6 or alpha * mu < 1e-15:
           return poisson_probability(k, mu)
   ```
   b. In `calculate_travel_penalty` (around line 124), sanitize input values to be non-negative:
   ```python
       rest_days = max(0.0, rest_days)
       travel_miles = max(0.0, travel_miles)
       tz_crossed = max(0, tz_crossed)
   ```
   c. In `get_adjusted_lambdas` (around line 170), define a small helper or logic to sanitize `None` values to default values so that keys mapped to `None` do not cause TypeErrors:
   ```python
       def get_context_val(context, key, default):
           val = context.get(key)
           return val if val is not None else default

       elev_a = get_context_val(teamA_context, "elevation", None)
       elev_b = get_context_val(teamB_context, "elevation", None)
       elev = elev_a if elev_a is not None else (elev_b if elev_b is not None else 0.0)
       
       temp_a = get_context_val(teamA_context, "temp", None)
       temp_b = get_context_val(teamB_context, "temp", None)
       temp = temp_a if temp_a is not None else (temp_b if temp_b is not None else 20.0)
       
       hum_a = get_context_val(teamA_context, "humidity", None)
       hum_b = get_context_val(teamB_context, "humidity", None)
       hum = hum_a if hum_a is not None else (hum_b if hum_b is not None else 0.0)
       
       accl_A = get_context_val(teamA_context, "accl_days", get_context_val(teamA_context, "accl_days_A", 0.0))
       accl_B = get_context_val(teamB_context, "accl_days", get_context_val(teamB_context, "accl_days_B", 0.0))
       
       heat_accl_A = get_context_val(teamA_context, "heat_accl_days", get_context_val(teamA_context, "heat_accl_days_A", 0.0))
       heat_accl_B = get_context_val(teamB_context, "heat_accl_days", get_context_val(teamB_context, "heat_accl_days_B", 0.0))
       
       p_travel_A = calculate_travel_penalty(
           get_context_val(teamA_context, "rest_days", 5.0),
           get_context_val(teamA_context, "travel_miles", 0.0),
           get_context_val(teamA_context, "tz_crossed", 0),
           get_context_val(teamA_context, "direction", "None")
       )
       p_travel_B = calculate_travel_penalty(
           get_context_val(teamB_context, "rest_days", 5.0),
           get_context_val(teamB_context, "travel_miles", 0.0),
           get_context_val(teamB_context, "tz_crossed", 0),
           get_context_val(teamB_context, "direction", "None")
       )
       
       delta_att_ctx_A, delta_def_ctx_A = calculate_context_adjustments(
           status=get_context_val(teamA_context, "status", "Neutral"),
           opponent_status=get_context_val(teamB_context, "status", "Neutral"),
           fan_support_pct=get_context_val(teamA_context, "fan_pct_A", get_context_val(teamA_context, "fan_support_pct", 0.5)),
           opponent_fan_support_pct=get_context_val(teamB_context, "fan_pct_B", get_context_val(teamB_context, "fan_support_pct", 0.5))
       )
   ```
   d. In `generate_joint_grid` (around line 269), add a clamp for maximum goals to avoid quadratic complexity CPU/memory risks, and add a normalization fallback in case the truncated probability sum is 0.0 (high lambda underflow):
   ```python
       max_goals = min(100, config.max_goals)
       p_a = [compute_marginal_probability(x, config.mu_a, config.alpha_a, config.dist_type) for x in range(max_goals + 1)]
       p_b = [compute_marginal_probability(y, config.mu_b, config.alpha_b, config.dist_type) for y in range(max_goals + 1)]
       # (make sure to replace config.max_goals with max_goals in the loops of generate_joint_grid)
   ```
   Normalization fallback:
   ```python
       total_prob = sum(sum(grid[x].values()) for x in grid)
       if total_prob > 0.0:
           for x in grid:
               for y in grid[x]:
                   grid[x][y] /= total_prob
       else:
           for x in grid:
               for y in grid[x]:
                   grid[x][y] = 0.0
           grid[max_goals][max_goals] = 1.0
   ```
   e. In `solve_optimal_tip` (around line 293), also use `max_goals = min(100, config.max_goals)` for the inner scoring loops and probability sum loops to ensure index alignment:
   ```python
       max_goals = min(100, config.max_goals)
       # (replace config.max_goals with max_goals in the range loops inside solve_optimal_tip)
   ```

2. In `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_tier2_boundary_corner.py`:
   Add `import math` at the top of the file to fix the NameError.

3. In `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_tier4_real_world.py` (line 132), in `test_t4_rw5_italy_uruguay_draw`, change:
   `tips, _, outcomes = predictor.solve_optimal_tip(1.0, 1.0, rho=-0.1)`
   to:
   `tips, _, outcomes = predictor.solve_optimal_tip(1.0, 1.0, rho=-0.2)`
   This ensures a draw tip is mathematically optimal under Kicktipp rules.

4. In `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_predictor.py`, add unit tests verifying:
   a. Negative Binomial stability under very small positive mu (e.g. `mu=1e-17`, `alpha=1.0`).
   b. NoneType sanitization in context dicts (e.g. `{"elevation": None}`).
   c. Dixon-Coles normalization fallback under extreme high lambda (e.g. `800.0`).
   d. Negative travel miles in travel penalty calculations.

Run the tests:
- `python3 -m unittest tests/test_predictor.py`
- `python3 -m unittest tests/test_tier1_feature_coverage.py`
- `python3 -m unittest tests/test_tier2_boundary_corner.py`
- `python3 -m unittest tests/test_tier4_real_world.py`

Write a summary of changes to `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/worker_m2_3/changes.md`.
