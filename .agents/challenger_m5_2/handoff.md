# Handoff Report — Challenger M5 Phase 2

## 1. Observation
The following code structures and behaviors were directly observed in the source code files:
- **In `predictor.py` (lines 51-54):**
  ```python
  alpha_is_nan = math.isnan(alpha) if isinstance(alpha, (int, float)) else True
  alpha_is_inf = math.isinf(alpha) if isinstance(alpha, (int, float)) else False
  mu_is_nan = math.isnan(mu) if isinstance(mu, (int, float)) else True
  mu_is_inf = math.isinf(mu) if isinstance(mu, (int, float)) else False
  ```
  However, string-to-float conversions are performed afterwards in lines 57-58:
  ```python
  alpha = float(alpha)
  mu = float(mu)
  ```
- **In `backtest.py` (lines 168-180):**
  ```python
  for key, val in row.items():
      if key in ['team_a', 'team_b', 'goals_a', 'goals_b', 'elevation', 'temp', 'humidity']:
          continue
      if val is None or val.strip() == '':
          continue
      val_str = val.strip()
      try:
          if '.' in val_str:
              match_dict[key] = float(val_str)
          else:
              match_dict[key] = int(val_str)
      except ValueError:
          match_dict[key] = val_str
  ```
- **In `solver.py` (line 109):**
  ```python
  else:
      p_t = grid[t_a][t_b] if (t_a < len(grid) and t_b < len(grid[t_a])) else 0.0
  ```
- **In `predictor.py` (line 382):**
  ```python
  factor = 1.0 - rho * a_a * a_b
  ```
- Additionally, attempts to execute python unit tests via `run_command` timed out waiting for user permission, meaning verification relies on static validation and structured unittest assertion design.

## 2. Logic Chain
1. **Silent Fallback Bug (mu/alpha):** Because `alpha_is_nan` and `mu_is_nan` check type before conversion, any float string (e.g. `alpha="0.5"`, `mu="2.0"`) causes them to evaluate to `True`. As a result, `negative_binomial_probability` silently falls back to Poisson (when `alpha_is_nan` is True) or returns `0.0` immediately (when `mu_is_nan` is True), discarding valid input.
2. **Backtester CSV Type Leak:** The loader in `backtest.py` catches `ValueError` for optional columns (e.g., `fan_pct_a` as `"not_a_float"`) and stores them as raw strings. The parser fails to raise a `ValueError` for bad data. Later, when `get_adjusted_lambdas` accesses these values and calls math functions, it triggers a `TypeError` crash.
3. **Solver list-of-dicts KeyError:** When `grid` is structured as a list of dicts, it falls into the `else` block of `solve_optimal_tip_from_grid`. The index boundary check compares the index `t_b` against the size of the dict `len(grid[t_a])`, but then does `grid[t_a][t_b]` as a dictionary lookup. If `t_b` is not a key in that dict, a `KeyError` is raised.
4. **Dixon-Coles Model Invariant Collapse:** With an extremely negative `rho` and high team parameter values, the adjustment factor `1.0 - rho * a_a * a_b` is massive and positive. When normalized, the probability of a draw `(0,0)` collapses to `1.0`, contradicting the qualitative model requirement that a negative correlation parameter should penalize draws.

## 3. Caveats
- Command-line execution was not performed because permission prompts timed out. The test files have been verified for syntax correctness and structural validity but have not been executed on the live environment.

## 4. Conclusion
There are multiple type-safety, logic, and model invariant gaps across the predictor, solver, and backtester components. 
We have designed and saved 11 adversarial tests inside `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_adversarial_c2.py` mapping to these specific gaps:
- Optional CSV fields parsing and downstream propagation crashes.
- Whitespace-only team names validation bypassing.
- Directory path input to CSV loader.
- AttributeError triggers in `get_team_stats`.
- Silent Poisson fallback for string `alpha` and zero returns for string `mu`.
- Model invariant collapse under extreme Dixon-Coles parameters.
- KeyErrors in solver during list-of-dicts iterations.
- NaN value propagation in solver grid structures.
- Unsanitized string parameter inputs in environmental/thermal factors.

## 5. Verification Method
To verify the adversarial test suite and check that all 11 test cases run successfully, run:
```bash
python3 -m unittest tests/test_adversarial_c2.py
```
Or run the E2E test orchestrator to find the overall status:
```bash
python3 tests/run_e2e.py
```
Inspection of `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_adversarial_c2.py` will confirm the presence and coverage of all tests.
