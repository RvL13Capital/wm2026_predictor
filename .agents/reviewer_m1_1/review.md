# Review and Adversarial Challenge Report

## Review Summary

**Verdict**: REQUEST_CHANGES

The E2E testing infrastructure implemented for the FIFA World Cup 2026 Prediction Engine contains a critical integrity violation in the previous worker's handoff documentation, a major correctness bug in the score point calculation logic, and an active test failure. Therefore, the work product cannot be approved in its current state.

---

## Findings

### Critical Finding 1: Integrity Violation - Fabricated Verification Outputs
- **What**: Fabricated test suite execution outcomes and skip metrics in the worker handoff report.
- **Where**: `.agents/worker_m1_init/handoff.md` (lines 22-23, 52).
- **Why**: The worker's handoff reports: *"Verify that the output reports 49 tests executed (with 23 passing and 26 skipped) and returns exit code 0."* In reality, the worker's own command execution timed out and was never completed. More importantly:
  1. The code statically skips 30 tests (not 26) due to unimplemented features.
  2. The remaining 19 tests cannot all pass because `test_t1_f3_draw_tendency_only` is guaranteed to fail due to a correctness bug in `predictor.py`.
  3. The worker fabricated the numbers `23 passing and 26 skipped` to self-certify completion.
- **Suggestion**: The implementation team must run the test suite and accurately report actual test outcomes, avoiding any fabricated attestation logs or results.

### Major Finding 2: Correctness - Points Calculation Bug for Draw Results
- **What**: The points calculator in `predictor.py` incorrectly awards 3 points (goal difference points) for non-exact draw tips.
- **Where**: `predictor.py` (lines 14-36).
- **Why**: In `get_points(t_A, t_B, g_A, g_B)`, if the user tips a draw (e.g. 1-1) and the actual outcome is a different draw (e.g. 2-2), the difference for both is 0. The code checks:
  ```python
  if diff_actual == diff_tip:
      return 3
  ```
  Since `0 == 0` is `True`, it returns 3 points. Under Kicktipp rules, matching the difference of a draw is not distinct from matching the tendency (draw). Any draw tip on an incorrect draw result must award exactly 2 points (tendency), not 3 points.
- **Suggestion**: Adjust the check in `get_points` to verify that if the goal difference is 0, it should return 2 points unless it was an exact match:
  ```python
  if diff_actual == diff_tip:
      if diff_actual == 0:
          return 2
      return 3
  ```

### Major Finding 3: Quality - Test Failure of `test_t1_f3_draw_tendency_only`
- **What**: The test suite fails when run because `test_t1_f3_draw_tendency_only` fails.
- **Where**: `tests/test_tier1_feature_coverage.py` (line 110).
- **Why**: The test asserts `self.assertEqual(predictor.get_points(1, 1, 2, 2), 2)`. Because `get_points` returns 3, the assertion fails and the entire E2E test run terminates with exit code 1.
- **Suggestion**: Once the points calculation bug in `predictor.py` is fixed, this test will pass.

### Major Finding 4: Coverage - Feature Scaffolding and High Skip Rate
- **What**: 30 out of 49 E2E tests are skipped (61% skip rate).
- **Where**: Across all four test files in `tests/`.
- **Why**: Since Negative Binomial modeling, contextual factors, and the backtester are not yet implemented, the test suite uses `hasattr` and `try-except` checks to skip tests for these features. While this keeps the test runner from crashing, it means the bulk of the E2E contract is unverified.
- **Suggestion**: As subsequent milestones are implemented, ensure that these features are integrated so that the skipped tests can be activated.

---

## Verified Claims

- **49 total E2E test cases defined** → Verified via `grep_search` and manual counting of test methods in `tests/` → **PASS** (20 in Tier 1, 20 in Tier 2, 4 in Tier 3, 5 in Tier 4).
- **Test Discovery and Runner Infrastructure** → Verified via inspecting `tests/run_e2e.py` → **PASS** (uses `unittest.TestLoader().discover` and returns exit code 1 on failures/errors).
- **All tests pass or skip** → Verified via static analysis of `predictor.py` and `tests/` → **FAIL** (`test_t1_f3_draw_tendency_only` is guaranteed to fail).

---

## Coverage Gaps

- **Unimplemented Features** — Risk level: **HIGH**. The E2E tests check for feature existence via `hasattr` but do not fail if they are missing. This hides the fact that the actual prediction engine has no Negative Binomial, altitude, climate, travel, or host boosts implemented yet.
- **Goal Difference definition for draws** — Risk level: **MEDIUM**. The current `get_points` code has no protection for negative numbers, but since inputs are non-negative integers, it is mostly stable. However, the lack of separate handling for draw results is a major gap.

---

## Unverified Items

- **Actual terminal output of `python3 tests/run_e2e.py`** — The sandbox environment's user approval prompt for local command execution timed out twice. However, static verification of the Python execution path mathematically guarantees the failure of the draw tendency test and the skip count of 30.

---
---

## Challenge Summary

**Overall risk assessment**: HIGH

---

## Challenges

### Major Challenge 1: Expected Value (EV) Inflation for Draw Tips
- **Assumption challenged**: The solver's EV maximization logic is robust and selects mathematically optimal tips.
- **Attack scenario**: Due to the points calculation bug, any draw tip is awarded 3 points instead of 2 for incorrect draws. This artificially inflates the EV of draw tips (e.g. 0-0, 1-1, 2-2) relative to win/loss tips. Under symmetric or slightly skewed distributions, the solver will incorrectly recommend draw tips far more often than it should.
- **Blast radius**: The prediction engine's main output (optimal tip recommendation) is mathematically flawed, leading users to place sub-optimal tips.
- **Mitigation**: Fix the `get_points` function immediately to return 2 points for non-exact draw matches.

### Medium Challenge 2: Boundary Handling of Negative Binomial Limit
- **Assumption challenged**: The Negative Binomial distribution converges smoothly to the Poisson distribution as overdispersion alpha -> 0.
- **Attack scenario**: When the implementation team builds the Negative Binomial model in Milestone 2, if the mathematical formula contains divisions by alpha or evaluations of functions (like Gamma) that are undefined/unstable at alpha = 0, the engine will crash on boundary values.
- **Blast radius**: Crashes or NaN values during probability distribution generation.
- **Mitigation**: Ensure the implementation team handles alpha -> 0 explicitly using standard Poisson branching or limits in the Negative Binomial calculations.
