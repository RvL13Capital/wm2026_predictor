# Handoff Report: Kicktipp Solver Analysis (Milestone 3)

## 1. Observation
We examined the current project structure and implementations:
- **`PROJECT.md` lines 32-40**: 
  ```text
  ### R3. Kicktipp Solver (EV Maximization)
  Strictly implements the 4/3/2 scoring system solver:
  - For any pair of team strength inputs, the solver iterates over possible score tips $(t_A, t_B)$ and outputs the tip maximizing expected points:
    $$E(t) = 4P(\text{Exact}) + 3P(\text{Diff}) + 2P(\text{Tendenz})$$
  - Points rules:
    - **4 Points**: Exact score ($t_A = g_A$ and $t_B = g_B$)
    - **3 Points**: Correct goal difference and tendency ($t_A - t_B = g_A - g_B$ and $\text{sign}(t_A - t_B) = \text{sign}(g_A - g_B)$)
    - **2 Points**: Correct tendency only ($\text{sign}(t_A - t_B) = \text{sign}(g_A - g_B)$)
    - **0 Points**: Otherwise
  ```
- **`predictor.py` lines 116-140**:
  ```python
  def get_points(t_A, t_B, g_A, g_B):
      """
      Calculates tipping points according to the rules:
      - 4 points: Exact score
      - 3 points: Correct goal difference and tendency (e.g. Tip 2:0, Actual 3:1)
      - 2 points: Correct tendency only (Heimsieg / Remis / Auswärtssieg)
      - 0 points: Otherwise
      """
      if t_A == g_A and t_B == g_B:
          return 4
      
      diff_actual = g_A - g_B
      diff_tip = t_A - t_B
      
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
- **`tests/test_tier1_feature_coverage.py` lines 180-204**: Defines test cases for the solver (`test_t1_f3_exact_score_points`, `test_t1_f3_difference_points`, `test_t1_f3_tendency_points`, `test_t1_f3_draw_tendency_only`, and `test_t1_f3_ev_maximization`).

---

## 2. Logic Chain
1. Based on `PROJECT.md`, the solver should determine the optimal tip that maximizes expected Kicktipp points under the 4/3/2 rules.
2. Based on `predictor.py` lines 116-140, the `get_points` function currently handles the points allocation:
   - Matches the exact score: returns 4 points.
   - Matches goal difference for a non-draw match: returns 3 points.
   - Matches draw outcome but not exact score: returns 2 points (handling the Kicktipp draw difference exception where $t_A - t_B = g_A - g_B = 0$ but $t_A \neq g_A$).
   - Matches winner/loser but incorrect goal difference: returns 2 points.
   - Incorrect winner: returns 0 points.
3. Therefore, the logic of `get_points` in `predictor.py` already mathematically encodes the standard Kicktipp draw difference rule.
4. Implementing Milestone 3 requires creating `solver.py`, exporting the point calculation and EV optimization logic there, and refactoring `predictor.py` to import them from `solver.py` for backwards compatibility.

---

## 3. Caveats
- We assumed standard Kicktipp rules are strictly followed (no custom scoring configurations like 5/4/3 rules or other point splits). If a user can configure alternative rule sets (e.g. 1 point for tendency, 2 for difference, 3 for exact), the solver's points calculation logic will need to be parameterized. Under the current `PROJECT.md` requirements, the 4/3/2 system is the exclusive target.
- The command `python -m unittest discover tests` was proposed but could not execute due to a permission timeout. However, we performed read-only code analysis to confirm compliance.

---

## 4. Conclusion
- The core Kicktipp points logic and EV maximization solver should be implemented in `solver.py` as detailed in `analysis.md`.
- `predictor.py` should import `get_points` and `solve_optimal_tip` from `solver.py` to ensure all existing tests pass and CLI execution continues to function properly.

---

## 5. Verification Method
1. Create `solver.py` in the root workspace directory.
2. Execute the existing E2E/unit test suite to verify that the implementation works correctly:
   ```bash
   python3 -m unittest discover tests
   ```
3. Inspect `tests/test_tier1_feature_coverage.py` at line 194 to ensure the specific test:
   ```python
   def test_t1_f3_draw_tendency_only(self):
       self.assertEqual(predictor.get_points(1, 1, 2, 2), 2)
   ```
   runs and passes, confirming the draw difference rule is active.
