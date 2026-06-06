# Handoff Report — Reviewer 2 (Milestone 2)

This report details the quality and adversarial review of the advanced probability prediction engine implemented in `predictor.py` and its corresponding test suite.

---

## 1. Observation

- **Command Execution Failure**: Running the unit tests via `python3 -m unittest tests/test_predictor.py` timed out at the user permission prompt stage:
  > `Encountered error in step execution: Permission prompt for action 'command' on target 'python3 -m unittest tests/test_predictor.py' timed out waiting for user response.`
- **File Mismatch in `tests/test_predictor.py`**:
  Lines 93-95 of `tests/test_predictor.py` define the following test case:
  ```python
  # Mexico City (2240m), Acclimated (7 days)
  # factor = 1 - 0.122264 * e^-1 = 0.954933
  self.assertAlmostEqual(calculate_altitude_factor(2240, 7), 0.954933, places=5)
  ```
  However, in `predictor.py`, `calculate_altitude_factor(2240, 7)` executes:
  - `h = (2240.0 - 1000.0) / 1000.0 = 1.24`
  - `base_loss = 0.08 * 1.24 + 0.015 * (1.24 ** 2) = 0.122264`
  - `remaining_loss = 0.122264 * math.exp(-7.0 / 7.0) = 0.04497841199577576`
  - `factor = 1.0 - remaining_loss = 0.9550215880042242`
  The difference between actual `0.955021588` and expected `0.954933` is `0.000088588`, which violates the assertion precision `places=5` (`round(abs(A-B), 5) == 0`).
- **IndexError in `predictor.py`**:
  Line 269 of `predictor.py` defines `generate_joint_grid(config: MatchModelConfig)`:
  ```python
  p_a = [compute_marginal_probability(x, config.mu_a, config.alpha_a, config.dist_type) for x in range(config.max_goals + 1)]
  ...
  a_a = p_a[1] / p_a[0] if p_a[0] > 0.0 else config.mu_a
  ```
  If `max_goals = 0`, then `p_a` has length 1. Accessing `p_a[1]` raises `IndexError: list index out of range`. This is triggered by line 55 in `tests/test_tier2_boundary_corner.py`:
  ```python
  tips, scores, outcomes = predictor.solve_optimal_tip(1.0, 1.0, max_goals=0)
  ```
- **Incomplete Test Files**:
  In `tests/test_tier3_cross_feature.py` and `tests/test_tier4_real_world.py`, many test methods (e.g. `test_t3_cf1_elevation_draw_solver`, `test_t4_rw1_mexico_city_azteca`) contain no assertions, only conditional skips. Example from `tests/test_tier3_cross_feature.py` lines 28-31:
  ```python
  def test_t3_cf1_elevation_draw_solver(self):
      """Integrates altitude adjustments, Dixon-Coles draw adjustments, and the solver."""
      if not is_contextual_factors_implemented():
          self.skipTest("Contextual factors (F2) not implemented yet")
  ```

---

## 2. Logic Chain

1. **Assertion Failure Verification**:
   - The test `test_altitude_factor` in `test_predictor.py` asserts that `calculate_altitude_factor(2240, 7)` equals `0.954933` to 5 decimal places.
   - Ground truth math shows the function returns `0.955022` (rounded).
   - The difference `0.955022 - 0.954933 = 0.000089` is greater than `1e-5` (the 5 decimal places tolerance of `assertAlmostEqual`).
   - Therefore, `test_predictor.py` will fail to execute successfully.

2. **IndexError Crash Verification**:
   - The boundary test `test_t2_f1_minimal_grid_size` in `test_tier2_boundary_corner.py` runs the solver with `max_goals = 0`.
   - In `generate_joint_grid`, the probability list `p_a` is constructed with size `max_goals + 1`, which is `1`.
   - The expression `a_a = p_a[1] / p_a[0]` evaluates. Because `len(p_a) == 1`, accessing `p_a[1]` throws an `IndexError`.
   - Therefore, `test_tier2_boundary_corner.py` will crash during execution.

3. **Placeholder Tests**:
   - Multiple test methods in `test_tier3_cross_feature.py` and `test_tier4_real_world.py` are blank/facade tests containing no actual assertion logic. While this does not violate review requirements directly (since they fall under other milestones currently marked as `IN_PROGRESS`), it is an completeness gap.

---

## 3. Caveats

- Direct unit test execution was blocked by local environment permission timeout restrictions. All findings are derived from manual dry-runs and mathematical verification of the logic.
- We assume standard Python `unittest` behavior for `assertAlmostEqual` (which uses a default rounding mechanism).

---

## 4. Conclusion (Quality Review Report)

### Review Summary
**Verdict**: REQUEST_CHANGES

### Findings

#### [Critical] Finding 1: Test Assertion Mismatch in `test_predictor.py`
- **What**: Mismatch between computed value and expected value in unit test.
- **Where**: `tests/test_predictor.py` line 95.
- **Why**: `calculate_altitude_factor(2240, 7)` computes to `0.955021588`, but the test asserts value `0.954933` with `places=5` precision, resulting in a unit test suite failure.
- **Suggestion**: Update the expected value in the assertion to `0.95502` or adjust the tolerance.

#### [Critical] Finding 2: IndexError on `max_goals = 0` Boundary Case
- **What**: Out-of-bounds index access in probability grid generation.
- **Where**: `predictor.py` line 274.
- **Why**: Accesses `p_a[1]` and `p_b[1]` assuming `max_goals >= 1`. If `max_goals = 0`, it crashes with `IndexError`.
- **Suggestion**: Add a safeguard:
  ```python
  a_a = p_a[1] / p_a[0] if (len(p_a) > 1 and p_a[0] > 0.0) else config.mu_a
  a_b = p_b[1] / p_b[0] if (len(p_b) > 1 and p_b[0] > 0.0) else config.mu_b
  ```

#### [Minor] Finding 3: Empty E2E Tests in Tiers 3 & 4
- **What**: Placeholder tests with no assertion logic.
- **Where**: `tests/test_tier3_cross_feature.py` and `tests/test_tier4_real_world.py`.
- **Why**: They exist as facades to meet structure checks but lack real implementation.
- **Suggestion**: Ensure these are fully populated in subsequent milestones.

### Verified Claims
- `poisson_probability(3, 2.0)` -> verified via manual computation -> **PASS**
- `negative_binomial_probability(1, 2.0, 0.5)` -> verified via manual computation -> **PASS**
- `calculate_travel_penalty(3.0, 3000.0, 6, "East")` -> verified via manual computation -> **PASS**

### Coverage Gaps
- Performance analysis on negative binomial execution for very large grid sizes (`max_goals` > 30) has not been verified. Risk is Low.

---

## 5. Adversarial Review Report

### Challenge Summary
**Overall risk assessment**: MEDIUM

### Challenges

#### [Medium] Challenge 1: Empty Grid Size Constraint (`max_goals = 0`)
- **Assumption challenged**: Assumed `max_goals >= 1` in marginal array indexing.
- **Attack scenario**: Solver is called with `max_goals = 0` (e.g. from an extreme CLI config input or automated grid sweep).
- **Blast radius**: Complete crash (`IndexError`) of the prediction pipeline.
- **Mitigation**: Add length checks before accessing array index `1`.

#### [Low] Challenge 2: Negative and Non-Physical Inputs to Travel Penalty
- **Assumption challenged**: Assumed `travel_miles >= 0` and `rest_days >= 0`.
- **Attack scenario**: Upstream models pass negative or extremely high fatigue metrics.
- **Blast radius**: Although bounded between `[0, 0.30]`, negative values could produce mathematically distorted intermediate adjustments.
- **Mitigation**: Add `max(0.0, ...)` bounds to input parameters within `calculate_travel_penalty`.

### Stress Test Results
- `solve_optimal_tip(1.0, 1.0, max_goals=0)` -> Expected: return (0,0) -> Actual: **CRASH** (IndexError)
- `calculate_altitude_factor(20000.0, 0.0)` -> Expected: cap at 0.5 -> Actual: **PASS** (Capped at 0.5)

---

## 6. Verification Method

To verify the fixes, execute the following commands in the workspace:
1. Fix the `test_predictor.py` assertion on line 95.
2. Fix the index access in `predictor.py` lines 274-275.
3. Run:
   ```bash
   python3 -m unittest tests/test_predictor.py
   python3 -m unittest tests/test_tier1_feature_coverage.py
   python3 -m unittest tests/test_tier2_boundary_corner.py
   ```
4. Confirm all tests pass with no failures or errors.
