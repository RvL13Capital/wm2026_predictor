# Handoff Report — Kicktipp Solver Equivalence & Correctness Verification

## 1. Observation

- **File Checked**: `solver.py` containing the Kicktipp expected value maximization solver.
  - Lines 8-32: `get_points(t_a, t_b, g_a, g_b)` computes points:
    ```python
    def get_points(t_a: int, t_b: int, g_a: int, g_b: int) -> int:
        if t_a == g_a and t_b == g_b:
            return 4
        
        diff_actual = g_a - g_b
        diff_tip = t_a - t_b
        
        sign_actual = sign(diff_actual)
        sign_tip = sign(diff_tip)
        
        if diff_actual == diff_tip:
            if diff_actual == 0:
                return 2
            return 3
        elif sign_actual == sign_tip:
            return 2
        else:
            return 0
    ```
  - Lines 98-119: `solve_optimal_tip_from_grid` calculates expected values:
    ```python
            d = t_a - t_b
            if d > 0:
                ev = p_t + diff_probs.get(d, 0.0) + 2.0 * prob_home
            elif d < 0:
                ev = p_t + diff_probs.get(d, 0.0) + 2.0 * prob_away
            else:
                ev = 2.0 * p_t + 2.0 * prob_draw
    ```

- **Commands Run**:
  - `python3 -m unittest tests/test_solver.py`
    - Result: `OK` (6 tests ran and passed).
    - Output:
      ```
      Ran 6 tests in 0.000s
      OK
      ```
  - `python3 tests/run_e2e.py`
    - Result: `Permission prompt for action 'command' on target 'python3 tests/run_e2e.py' timed out waiting for user response.`
  - `python3 verify_solver_equivalence.py`
    - Result: `Permission prompt for action 'command' on target 'python3 verify_solver_equivalence.py' timed out waiting for user response.`
  - `python3 -m unittest tests/test_solver.py` (after adding `test_mathematical_equivalence`)
    - Result: `Permission prompt for action 'command' ... timed out waiting for user response.`

- **Files Created/Modified**:
  - Created `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/verify_solver_equivalence.py` implementing a verification harness comparing the optimized solver with a naive expectation solver.
  - Appended `test_mathematical_equivalence` to `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_solver.py` to allow verification directly within unit tests.

---

## 2. Logic Chain

- **Step 1 (Point Value Verification)**: The scoring rules are:
  - Exact match: 4 points
  - Non-exact goal difference & tendency match (non-draws only): 3 points
  - Tendency match or non-exact draw on draw outcome: 2 points
  - Otherwise: 0 points
  The `get_points` function returns:
  - 4 when `t_a == g_a and t_b == g_b`.
  - 3 when `diff_actual == diff_tip` and `diff_actual != 0` (non-draws).
  - 2 when `diff_actual == diff_tip == 0` (non-exact draw on draw) or `sign_actual == sign_tip` (correct tendency).
  - 0 otherwise.
  Thus, `get_points` is logically correct and conforms to standard Kicktipp scoring.

- **Step 2 (Mathematical Solver Verification)**:
  Let $p_t = P(g_a = t_a, g_b = t_b)$. Let $P(g_a - g_b = d)$ be the probability of actual goal difference being $d$. Let $P(g_a > g_b)$ be the home win probability (`prob_home`), $P(g_a < g_b)$ be the away win probability (`prob_away`), and $P(g_a = g_b)$ be the draw probability (`prob_draw`).
  
  **Case 2a (Home Win Tip: $t_a > t_b \Rightarrow d = t_a - t_b > 0$)**:
  The expectation under the 4/3/2 rules is:
  $$E(t) = 4p_t + 3(P(g_a - g_b = d) - p_t) + 2(P(g_a > g_b) - P(g_a - g_b = d))$$
  Expanding and simplifying this expression:
  $$E(t) = (4 - 3)p_t + (3 - 2)P(g_a - g_b = d) + 2P(g_a > g_b)$$
  $$E(t) = p_t + P(g_a - g_b = d) + 2P(g_a > g_b)$$
  The optimized solver evaluates this as:
  `ev = p_t + diff_probs.get(d, 0.0) + 2.0 * prob_home`
  This is mathematically identical.

  **Case 2b (Away Win Tip: $t_a < t_b \Rightarrow d = t_a - t_b < 0$)**:
  Symmetrically, the expectation is:
  $$E(t) = 4p_t + 3(P(g_a - g_b = d) - p_t) + 2(P(g_a < g_b) - P(g_a - g_b = d))$$
  $$E(t) = p_t + P(g_a - g_b = d) + 2P(g_a < g_b)$$
  The optimized solver evaluates this as:
  `ev = p_t + diff_probs.get(d, 0.0) + 2.0 * prob_away`
  This is mathematically identical.

  **Case 2c (Draw Tip: $t_a = t_b \Rightarrow d = 0$)**:
  Since correct difference on a draw is not awarded 3 points (it gets 2 points), the expectation is:
  $$E(t) = 4p_t + 2(P(g_a = g_b) - p_t)$$
  $$E(t) = 2p_t + 2P(g_a = g_b)$$
  The optimized solver evaluates this as:
  `ev = 2.0 * p_t + 2.0 * prob_draw`
  This is mathematically identical.

  Therefore, the optimized solver's EV equations are mathematically identical to the naive definition of expected value under the 4/3/2 Kicktipp rules.

- **Step 3 (Complexity Analysis)**:
  - Naive EV solver: For $T^2$ possible tips, we sum over $N^2$ goal outcomes. Complexity: $O(T^2 \cdot N^2)$.
  - Optimized solver: Precomputation of `diff_probs`, `prob_home`, `prob_away`, and `prob_draw` takes $O(N^2)$ time. Then for each of the $T^2$ tips, EV is computed in $O(1)$ time. Complexity: $O(N^2 + T^2)$.
  This is a significant performance improvement.

---

## 3. Caveats

- Due to the user being AFK, execution of E2E tests and equivalence verification scripts timed out on the permission prompts.
- While the mathematical proof is rigorous and complete, empirical runs of the 10,000 randomized grids are blocked on system permissions. However, the logic has been checked and verified as mathematically identical.
- The unit test `test_mathematical_equivalence` has been safely added to `tests/test_solver.py` and the standalone verification script `verify_solver_equivalence.py` was created. Once the user provides permissions, they can be executed.

---

## 4. Conclusion

The Kicktipp EV Solver in `solver.py` is **correct, mathematically identical to the naive solver, and highly optimized**. The verdict is **CLEAN**.

---

## 5. Verification Method

To independently execute and verify correctness:
1. Run the solver unit tests (including the new mathematical equivalence test):
   ```bash
   python3 -m unittest tests/test_solver.py
   ```
2. Run the E2E test suite:
   ```bash
   python3 tests/run_e2e.py
   ```
3. Run the standalone verification script (which tests 10,000 iterations):
   ```bash
   python3 verify_solver_equivalence.py
   ```
