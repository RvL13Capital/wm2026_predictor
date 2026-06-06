# Handoff Report: Predictor Engine Empirical Verification & Adversarial Review

## 1. Observation
This analysis focuses on the prediction engine and mathematical equations in `predictor.py` at `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`.

### Observation A: Negative Binomial Probability Formula
Under `negative_binomial_probability` in `predictor.py` (lines 35-56):
```python
35: def negative_binomial_probability(k: int, mu: float, alpha: float) -> float:
...
45:     r = 1.0 / alpha
46:     p = 1.0 / (1.0 + alpha * mu)
47:     
48:     log_p = (
49:         math.lgamma(k + r)
50:         - math.lgamma(k + 1)
51:         - math.lgamma(r)
52:         + k * math.log(1.0 - p)
53:         + r * math.log(p)
54:     )
```
When `mu` is a very small positive number (e.g., `1e-17`) and `alpha` is a positive number (e.g., `1.0`), the product `alpha * mu = 1e-17`. Under standard double-precision `float64`, adding `1e-17` to `1.0` results in exactly `1.0` due to floating point precision limits. Therefore, `p` evaluates to `1.0 / 1.0 = 1.0`, and `1.0 - p` evaluates to exactly `0.0`. This causes `math.log(1.0 - p)` to call `math.log(0.0)`, which raises:
```text
ValueError: math domain error
```

### Observation B: Dixon-Coles Probability Normalization
Under `generate_joint_grid` in `predictor.py` (lines 269-291):
```python
284:     # Normalize the grid to ensure sum == 1.0 over the truncated space
285:     total_prob = sum(sum(grid[x].values()) for x in grid)
286:     if total_prob > 0.0:
287:         for x in grid:
288:             for y in grid[x]:
289:                 grid[x][y] /= total_prob
```
When `mu_a` or `mu_b` is extremely large (e.g., $\ge 750.0$), the calculated Poisson or Negative Binomial marginal probabilities `p_a[x]` and `p_b[y]` for all $x, y \le \text{max\_goals} = 12$ underflow to exactly `0.0`. As a result, the sum of all elements in the grid `total_prob` is exactly `0.0`. Under this condition, the normalization condition `total_prob > 0.0` is `False`, skipping the normalization step. The grid remains filled with `0.0`, resulting in a non-normalized probability distribution and returning all outcomes as `nan` or all zeros in `solve_optimal_tip` (lines 322-324):
```python
322:     prob_home = sum(grid[g_a][g_b] for g_a in grid for g_b in grid[g_a] if g_a > g_b)
```

### Observation C: Missing Values and `None` Propagation in Context dicts
In `get_adjusted_lambdas` in `predictor.py` (lines 170-248):
```python
177:     elev = teamA_context.get("elevation", teamB_context.get("elevation", 0.0))
```
If a context dictionary contains a key mapped explicitly to `None` (e.g., `{"elevation": None}`), `teamA_context.get("elevation", 0.0)` evaluates to `None` rather than falling back to `0.0`. This value `None` is passed down to `calculate_altitude_factor` (line 98) which attempts:
```python
99:     if elevation <= 1000.0:
```
This raises:
```text
TypeError: '<=' not supported between instances of 'NoneType' and 'float'
```
Similarly, if `"temp"` is `None` in the context dict, it causes a crash in `calculate_wbgt` (line 108: `denom = temperature + 237.3` -> `TypeError`).

### Observation D: Performance Scaling of Grid Solver
In `generate_joint_grid` in `predictor.py` (lines 269-291):
The grid generation employs a nested loop over `max_goals + 1`:
```python
277:     for x in range(config.max_goals + 1):
278:         grid[x] = {}
279:         for y in range(config.max_goals + 1):
...
282:             grid[x][y] = base_prob * adj_factor
```
If a user calls the solver with a large grid size (e.g., `max_goals = 1000`), this loop runs $(1001)^2 = 1,002,001$ times. Since each iteration performs a Dixon-Coles adjustment check, this scales quadratically $O(M^2)$ in time and space, presenting potential CPU/memory denial-of-service risks.

### Observation E: Travel Penalty Curve with Negative Distances
In `calculate_travel_penalty` in `predictor.py` (lines 124-138):
```python
126:     p_dist = 0.05 * (1.0 - math.exp(-0.001 * travel_miles)) * math.exp(-0.30 * rest_days)
```
If `travel_miles` is negative (e.g., `-1000.0`), `1.0 - math.exp(-0.001 * travel_miles)` evaluates to a negative number (`-1.718`). Since `p_rest + p_dist + p_tz` is summed, a negative travel distance acts as a fatigue reducer, decreasing the overall travel penalty.

### Observation F: Command Execution Sandbox
During execution of unit tests using `run_command` on target `python3 -m unittest tests/test_predictor.py`, the action timed out waiting for user approval:
```text
Encountered error in step execution: Permission prompt for action 'command' on target 'python3 -m unittest tests/test_predictor.py' timed out waiting for user response.
```

---

## 2. Logic Chain

1. **Negative Binomial Math Stability**:
   - `alpha * mu` dictates the success probability `p = 1.0 / (1.0 + alpha * mu)` (Observation A).
   - If `alpha * mu < 1e-16`, float64 representation of `1.0 + alpha * mu` underflows to exactly `1.0` (Observation A).
   - Since `p` becomes exactly `1.0`, `1.0 - p` is exactly `0.0`.
   - The PMF equation evaluates `math.log(1.0 - p)` which is `math.log(0.0)`.
   - Python's `math.log(0.0)` raises a `ValueError` (Observation A).
   - **Conclusion**: The Negative Binomial distribution is mathematically unstable and crashes under very small positive inputs.

2. **Dixon-Coles Truncation & Normalization**:
   - `total_prob` is the sum of truncated grid elements (Observation B).
   - If the mean $\mu$ is very large (e.g., $\ge 750.0$), the probability mass is shifted far to the right, and the marginal probability of goals $\le 12$ becomes extremely close to $0.0$, underflowing to `0.0` (Observation B).
   - Thus, every element in the grid is `0.0`, and `total_prob` is `0.0`.
   - Since `total_prob` is not greater than `0.0`, normalization is skipped (Observation B).
   - The grid remains all zeros, causing outcome probabilities (home, draw, away wins) to sum to `0.0` instead of `1.0`, and breaking downstream predictions.

3. **`NoneType` Vulnerability**:
   - `.get(key, default)` returns the value if the key exists, even if the value is `None` (Observation C).
   - If the database parser (e.g. from backtests or API) inserts `None` into context dicts for elevation or climate variables, those values bypass the defaults (Observation C).
   - The math curves expect float inputs and attempt operations like `<=` or `+` (Observation C).
   - This mismatch raises a `TypeError` and crashes the application.

4. **Solver Performance Bottleneck**:
   - The grid generation is implemented as a nested loop running $(M+1)^2$ times (Observation D).
   - As $M$ increases, execution time and memory footprint grow quadratically.
   - For $M \ge 1000$, it results in millions of iterations, leading to high latency and potential memory exhaustion.

---

## 3. Caveats
- No live commands could be run in this environment due to the automated sandbox permission timeouts (Observation F). Thus, the unit tests and E2E suites were analyzed statically, and verification of runtime behavior is based on Python's language-level specification and dry-run execution traces.
- No backtest data (`backtest.py`) was present in the workspace directory (it is scheduled as PLANNED for Milestone 4 in `PROJECT.md`).

---

## 4. Conclusion
While the contextual curves in `predictor.py` are robustly capped in most cases (e.g. altitude and wet-bulb factors are bounded within $[0.5, 1.0]$ even under infinite inputs), there are key mathematical stability and data validation issues:
1. **Critical Crash**: The Negative Binomial model crashes with a `ValueError: math domain error` when the product of the dispersion parameter and the expected goals is extremely small but positive (i.e. $\alpha \mu < 10^{-16}$).
2. **Probability Invalidation**: Extremely large lambdas (e.g., $\ge 750.0$) lead to grid underflow, preventing normalization, and resulting in zero outcome probabilities.
3. **Robustness Issue**: Explicitly passing `None` in the context dictionaries causes crashes via `TypeError`.
4. **Performance Hazard**: Large grid sizes lead to quadratic latency scaling.
5. **Fatigue Anomalies**: Negative travel distances lower fatigue.

---

## 5. Verification Method

### Testing the Negative Binomial Crash
Run the following script to reproduce the Negative Binomial crash:
```python
import predictor
# This will crash with ValueError: math domain error
predictor.negative_binomial_probability(k=0, mu=1e-17, alpha=1.0)
```
*Expected Resolution*: Ensure `alpha * mu > 1e-15` before calculating NB, otherwise fall back to Poisson.

### Testing the NoneType Crash
Run the following script to reproduce the `NoneType` propagation crash:
```python
import predictor
team_a = {"elevation": None, "temp": 20.0, "humidity": 50.0}
team_b = {"elevation": 0.0, "temp": 20.0, "humidity": 50.0}
# This will crash with TypeError: '<=' not supported between instances of 'NoneType' and 'float'
predictor.get_adjusted_lambdas(1.5, 1.5, team_a, team_b)
```
*Expected Resolution*: Update dictionary getters in `get_adjusted_lambdas` to sanitize `None` values (e.g., `elev = teamA_context.get("elevation") or teamB_context.get("elevation") or 0.0`).

### Running the Project Test Commands (if permissions allow)
Verify E2E tests and unit tests:
```bash
python3 -m unittest tests/test_predictor.py
python3 -m unittest tests/test_tier1_feature_coverage.py
python3 -m unittest tests/test_tier2_boundary_corner.py
python3 tests/run_e2e.py
```

---

## 6. Adversarial Review Challenges

### [Critical] Challenge 1: Negative Binomial Underflow Crash
- **Assumption challenged**: That the Negative Binomial distribution is stable for all valid positive input means $\mu > 0.0$.
- **Attack scenario**: A team with an extremely low goal expectation (e.g., $\mu = 10^{-17}$) plays under the Negative Binomial distribution with $\alpha > 0$.
- **Blast radius**: Crashes the entire prediction execution with `ValueError: math domain error`.
- **Mitigation**: Fall back to Poisson if `alpha * mu < 1e-15` or clip `mu` to a reasonable minimum.

### [High] Challenge 2: Dixon-Coles Normalization Grid Deflation
- **Assumption challenged**: That the generated joint grid will always sum to a positive value and normalize to 1.0.
- **Attack scenario**: Inputs with extreme expected goals (e.g., $\mu \ge 750.0$) shifted far past the truncation limit of `max_goals = 12`.
- **Blast radius**: Normalization is skipped, grid probabilities remain $0.0$, and final outcome probabilities sum to $0.0$, violating probability axioms.
- **Mitigation**: If `total_prob == 0.0`, fall back to a default distribution, set the most likely score to $1.0$, or raise a clear warning.

### [Medium] Challenge 3: Unsanitized Context Parameters
- **Assumption challenged**: That the inputs provided in context dictionaries are either valid floats or completely missing.
- **Attack scenario**: Missing values parsed from databases as `None` are passed in context dictionaries.
- **Blast radius**: Raises `TypeError` and crashes the execution.
- **Mitigation**: Sanitize inputs in `get_adjusted_lambdas` using `val if val is not None else default`.

### [Low] Challenge 4: Quadratic Complexity Grid Solver
- **Assumption challenged**: That grid size `max_goals` scales linearly or is always low.
- **Attack scenario**: Extremely large values of `max_goals` (e.g., $1000$ or higher) passed to the solver.
- **Blast radius**: Memory exhaustion or execution timeout (OOM/latency penalty).
- **Mitigation**: Add a hard limit or validation check on `max_goals` (e.g., $\le 100$).
