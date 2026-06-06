# Handoff Report — explorer_m3_2

## 1. Observation
- **Expected Value Loop**: In `predictor.py` (lines 497-505), `solve_optimal_tip` computes expected value for all possible tips:
  ```python
      # Calculate expected points for each tip (t_A, t_B)
      expected_points = {}
      for t_a in range(max_tip_clamped + 1):
          for t_b in range(max_tip_clamped + 1):
              ev = 0.0
              for g_a in range(max_goals_clamped + 1):
                  for g_b in range(max_goals_clamped + 1):
                      pts = get_points(t_a, t_b, g_a, g_b)
                      ev += pts * grid[g_a][g_b]
              expected_points[(t_a, t_b)] = ev
  ```
- **Interface Contract**: In `PROJECT.md` (lines 49-51):
  ```markdown
  ### predictor.py ↔ solver.py
  - **Prediction engine** outputs a full probability distribution over scores (up to `max_goals` × `max_goals` grid, e.g., $12 \times 12$).
  - **Solver** takes this probability distribution and outputs the optimal tip $(t_A, t_B)$ maximizing Kicktipp EV.
  ```
- **Scoring Rules**: In `PROJECT.md` (lines 33-40) and `predictor.py` (lines 116-140), point rules are specified as:
  - Exact score: 4 points.
  - Correct goal difference and tendency (when difference is non-zero): 3 points.
  - Correct tendency (when difference is zero or different): 2 points.
  - Otherwise: 0 points.
- **Existing Test Interface**: In `tests/test_tier1_feature_coverage.py` (lines 200), tests invoke the solver directly from the predictor:
  ```python
          tips, _, _ = predictor.solve_optimal_tip(1.5, 1.2)
  ```

---

## 2. Logic Chain
1. Based on the observation in `PROJECT.md`, the interface contract separates probability prediction (`predictor.py`) from EV optimization (`solver.py`). Therefore, we need to create `solver.py` and delegate the expected value optimization logic to it.
2. Based on the observation in `tests/test_tier1_feature_coverage.py`, existing tests call `predictor.solve_optimal_tip` directly. Thus, for backwards compatibility, `predictor.solve_optimal_tip` must import the new `solver.py` module and wrap or delegate to it.
3. Based on the observation of the double-loop expected value calculation in `predictor.py` (lines 497-505), the naive grid search runs in $O(T^2 \cdot N^2)$ time.
4. By mathematically decomposing the expected value equations under the 4/3/2 Kicktipp rules, we observe that the expected value for any tip is linear with respect to the exact probability of that score, the probability of that goal difference, and the total outcome tendency (Home/Draw/Away).
5. Specifically:
   - If $t_A > t_B \implies E(t_A, t_B) = P(t_A, t_B) + P(\text{Diff} = t_A - t_B) + 2 P(\text{Home})$
   - If $t_A < t_B \implies E(t_A, t_B) = P(t_A, t_B) + P(\text{Diff} = t_A - t_B) + 2 P(\text{Away})$
   - If $t_A = t_B \implies E(t_A, t_B) = 2 P(t_A, t_B) + 2 P(\text{Draw})$
6. Precalculating $P(\text{Home})$, $P(\text{Draw})$, $P(\text{Away})$, and $P(\text{Diff}=d)$ takes $O(N^2)$ time. Then, evaluating all $(T+1)^2$ possible tips takes $O(T^2)$ time. This reduces the total complexity to $O(N^2 + T^2)$, making the solver significantly more efficient.
7. To guarantee correctness, the implementation in `solver.py` can support both naive and optimized versions, running them side-by-side during validation to confirm that the outputs are mathematically identical.

---

## 3. Caveats
- The mathematical derivation assumes the strict **4/3/2** scoring rule defined in `PROJECT.md`. If the rules are modified (e.g. to a different point allocation such as 5/4/3 or if goal differences in draws yield points), the optimized formulas must be re-derived.
- When $t_A$ or $t_B$ exceed $N = \text{max\_goals}$, the value $P(t_A, t_B)$ is not present in the probability grid. The implementation must treat such out-of-grid index accesses as $0.0$ to avoid `KeyError` exceptions.

---

## 4. Conclusion
We recommend implementing a new file `solver.py` that implements the Kicktipp solver function using the optimized $O(N^2 + T^2)$ expected value search. For testing and verification purposes, a naive $O(T^2 N^2)$ search mode should be supported to allow unit-test verification of the mathematical equivalence. Finally, `predictor.py` should import `solver.py` and delegate `solve_optimal_tip` to it for backward compatibility.

---

## 5. Verification Method
1. **Regression Suite**: Execute `pytest tests/` to confirm that delegating the solver logic to `solver.py` does not break any existing test cases.
2. **Mathematical Invariance Check**: Write a unit test that feeds multiple random grids to the solver and compares `use_optimized=True` and `use_optimized=False`, asserting that the returned optimal tip and expected values are identical.
3. **Out-of-Grid Check**: Verify that when `max_tip > max_goals`, the solver handles tip inputs correctly without index errors.
