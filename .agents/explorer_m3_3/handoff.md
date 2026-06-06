# Handoff Report - explorer_m3_3

## 1. Observation
* **Current Solver Implementation**: In `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`, `solve_optimal_tip` is defined from line 464 to 522 and `get_points` is defined from line 116 to 140.
* **Interface Contract**: In `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/PROJECT.md` (lines 49-51):
  > ### predictor.py ↔ solver.py
  > - **Prediction engine** outputs a full probability distribution over scores (up to `max_goals` × `max_goals` grid, e.g., $12 \times 12$).
  > - **Solver** takes this probability distribution and outputs the optimal tip $(t_A, t_B)$ maximizing Kicktipp EV.
* **Test Discovery**: In `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/run_e2e.py` (lines 12-13):
  > `suite = loader.discover(start_dir=os.path.dirname(__file__), pattern='test_*.py')`
* **Command Execution**: Attempted to run `python3 tests/run_e2e.py`, but it timed out on the permission prompt:
  > `Encountered error in step execution: Permission prompt for action 'command' on target 'python3 tests/run_e2e.py' timed out waiting for user response.`

---

## 2. Logic Chain
1. To fulfill the contract in `PROJECT.md`, `solver.py` must handle Kicktipp EV maximization, while `predictor.py` serves as the prediction engine.
2. To avoid circular imports, `solver.py` should be fully independent of `predictor.py` and its configuration/grid-generating functions.
3. Therefore, `solver.py` must accept a generic 2D grid dict representing the probability distribution over scores and execute the EV loop.
4. Exporting `get_points` and `solve_optimal_tip_from_grid` to `solver.py`, and importing/wrapping them in `predictor.py` ensures that all existing E2E/Tier tests targeting `predictor.py`'s API pass without code modifications.
5. Creating `tests/test_solver.py` matches the test runner pattern `test_*.py` from observation 3, ensuring automatic discovery and execution of the new unit tests.

---

## 3. Caveats
* Due to zsh command permission prompt timeout, the current test suite was not run locally. Code analysis and design are verified through static inspection of file contents.

---

## 4. Conclusion
* Extract the point calculator (`get_points`) and grid-based solver (`solve_optimal_tip_from_grid`) into a new file `solver.py`.
* Refactor `predictor.py` to import both functions and delegate to keep its API fully backward-compatible.
* Write a new test file `tests/test_solver.py` containing point check scenarios, draw difference tendency checks, and a mathematically validated EV maximization test (where the top EV tip is distinct from the most probable outcome).

---

## 5. Verification Method
* Run the test suite using `python3 tests/run_e2e.py` and confirm that all tests pass, including the newly created `tests/test_solver.py`.
* Inspect the imported functions in `predictor.py` to verify no circular dependencies or signature mismatch errors occur.
