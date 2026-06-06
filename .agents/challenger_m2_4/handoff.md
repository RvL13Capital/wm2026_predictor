# Handoff Report - Predictor Engine Empirical Verification & Adversarial Review

## 1. Observation

In the advanced probability engine and contextual factor curves implemented in `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`, the following details were observed:

### Observation A: Command Runner Sandbox Execution Restrictions
Executing the tests and the verification script directly in the terminal via `run_command` (e.g. `python3 verify_engine.py`) timed out twice during the sandboxed environment's automated permission dialog. Because of this, the correctness of the engine and the effectiveness of the applied fixes were verified using systematic line-by-line static analysis and mathematical reasoning on Python's float64 behavior.

### Observation B: Large/Overflowing Dispersion parameters in Negative Binomial Probability
Lines 40-55 of `predictor.py`:
```python
    if alpha <= 1e-6 or alpha * mu < 1e-15:
        return poisson_probability(k, mu)
    if mu <= 0.0:
        return 1.0 if k == 0 else 0.0
    
    r = 1.0 / alpha
    p = 1.0 / (1.0 + alpha * mu)
    
    log_p = (
        math.lgamma(k + r)
        - math.lgamma(k + 1)
        - math.lgamma(r)
        + k * math.log(1.0 - p)
        + r * math.log(p)
    )
    return math.exp(log_p)
```
- While the fix `alpha * mu < 1e-15` prevents a `ValueError` for small positive inputs underflow, it fails to handle overflow in `alpha * mu`.
- If `alpha * mu` is extremely large and overflows the float64 limit (`> 1.797e308`), it evaluates to `inf`.
- Then, `p = 1.0 / (1.0 + inf) = 0.0`.
- The equation subsequently evaluates `math.log(p)`, which is `math.log(0.0)`. This raises `ValueError: math domain error` and crashes the engine.

### Observation C: Temperature Boundary Underflow / Overflow in WBGT
Lines 107-113 of `predictor.py`:
```python
def calculate_wbgt(temperature: float, humidity: float) -> float:
    denom = temperature + 237.3
    if denom == 0:
        denom = 1e-9
    e = (humidity / 100.0) * 6.1078 * math.exp((17.27 * temperature) / denom)
    wbgt = 0.567 * temperature + 0.393 * e + 3.94
    return wbgt
```
- The check `if denom == 0: denom = 1e-9` only protects against division by exactly zero.
- If `temperature` is slightly below `-237.3` such that $T \in [-243.21, -237.3)$, then `denom` becomes a tiny negative float, and the quotient `(17.27 * temperature) / denom` becomes a large positive value ($> 709.78$).
- Calling `math.exp(...)` on this value raises `OverflowError: math range error` and crashes the contextual engine.

### Observation D: Unsanitized Acclimation Parameters in Altitude and Thermal Curves
Lines 195-206 of `predictor.py` and altitude factor calculation:
```python
    accl_A = get_context_val(teamA_context, "accl_days", get_context_val(teamA_context, "accl_days_A", 0.0))
...
    f_alt_A = calculate_altitude_factor(elev, accl_A)
```
and lines 98-105:
```python
def calculate_altitude_factor(elevation: float, acclimation_days: float) -> float:
...
    remaining_loss = base_loss * math.exp(-acclimation_days / 7.0)
```
- The parameter `acclimation_days` is fetched from context but never validated/sanitized to be non-negative.
- If an extremely negative value (e.g. `-7000.0` or less) is passed, `-acclimation_days / 7.0` evaluates to a large positive value ($> 709.78$).
- This causes `math.exp(...)` to overflow, raising `OverflowError: math range error` and crashing the context calculations.
- The same issue exists in `calculate_thermal_factor` with `heat_accl_days` (dividing by `5.0` instead of `7.0`).

### Observation E: Key Error crash under Negative Grid Sizes in generate_joint_grid fallback
Lines 283-311 of `predictor.py`:
```python
def generate_joint_grid(config: MatchModelConfig) -> Dict[int, Dict[int, float]]:
    grid = {}
    max_goals = min(100, config.max_goals)
...
    else:
        for x in grid:
            for y in grid[x]:
                grid[x][y] = 0.0
        grid[max_goals][max_goals] = 1.0
```
- If `config.max_goals` is negative (e.g. `-1`), the `max_goals` local variable becomes `-1`.
- The loop starting at line 292 `for x in range(max_goals + 1):` (i.e. `range(0)`) is skipped, so `grid` remains empty `{}`.
- Under empty grid conditions, `total_prob = 0.0`, which triggers the `else` clause at line 305.
- The statement `grid[max_goals][max_goals] = 1.0` (i.e. `grid[-1][-1] = 1.0`) is executed. Since `grid` is empty `{}` and does not contain the key `-1`, this raises `KeyError: -1` and crashes the program.

### Observation F: Dixon-Coles Adjustment NaN Propagation
Lines 268-281 and 295-304 of `predictor.py`:
```python
def get_dixon_coles_adjustment(x: int, y: int, a_a: float, a_b: float, rho: float) -> float:
...
    if x == 0 and y == 0:
        factor = 1.0 - rho * a_a * a_b
...
    return max(0.0, factor)
```
- If `rho` is extremely negative (e.g., `-1e308`), `factor` at `(0,0)` overflows to `inf`.
- Then, the grid normalization sum `total_prob` becomes `inf`.
- Normalizing the grid computes `inf / inf` at cell `(0,0)`, which resolves to `nan`, propagating `nan` values throughout all downstream solver predictions and outcomes, although no Python traceback is raised.

---

## 2. Logic Chain

1. **Negative Binomial Instability**: 
   - `alpha * mu` can grow arbitrarily large.
   - If it overflows float64 range ($> 1.797e308$), it is represented as `inf` (Observation B).
   - `1.0 + alpha * mu` becomes `inf`.
   - `p = 1.0 / (1.0 + alpha * mu)` is evaluated as `0.0` (Observation B).
   - Evaluating the probability density formula requires computing `math.log(p)`, which evaluates to `math.log(0.0)`.
   - Python raises `ValueError: math domain error`, terminating execution.
   - **Conclusion**: The Negative Binomial crash is NOT fully prevented under extreme large values of $\alpha$ or $\mu$.

2. **WBGT Temperature Range Vulnerability**:
   - `temperature + 237.3` is checked only for exactly `0.0` (Observation C).
   - If temperature is in the range $[-243.21, -237.3)$, the denominator is a negative value close to zero.
   - The exponent term `(17.27 * temperature) / denom` becomes a large positive value ($> 709.78$).
   - `math.exp(...)` overflows, raising `OverflowError`.
   - **Conclusion**: The WBGT temperature fix does NOT prevent all mathematical crashes near the $-237.3$ boundary.

3. **Acclimation Curves Fatigue Crash**:
   - `acclimation_days` and `heat_acclimation_days` are not sanitized to be non-negative in the calling function (Observation D).
   - Under extremely negative acclimation parameters, the exponent of the exponential decay curve becomes positive and extremely large ($> 709.78$).
   - `math.exp` of this value raises `OverflowError`.
   - **Conclusion**: Unsanitized negative acclimation inputs can trigger mathematical crashes in environmental factor curves.

4. **Negative Grid Size Fallback Exception**:
   - Under a negative max goals config (e.g. `config.max_goals = -1`), the grid keys are never initialized (Observation E).
   - The normalization fallback triggers because the grid is empty (`total_prob = 0.0`).
   - The fallback attempts to assign `1.0` to the corner `grid[max_goals][max_goals]`.
   - Because the outer key `max_goals` (e.g. `-1`) is missing from the dictionary, a `KeyError` is raised.
   - **Conclusion**: A negative grid size parameter crashes the grid builder.

---

## 3. Caveats

- **Physical Plausibility**: Inputs such as `temperature = -238.0`, `acclimation_days = -7000`, or `max_goals = -1` are physically or logically impossible in real-world tournament setups. However, a production-ready scoring or prediction engine must be mathematically resilient to malformed values or database errors.
- **Command Runner Timeouts**: The lack of terminal execution logs is a minor caveat, but the analytical proofs are mathematically rigorous and deterministic under Python's execution environment.

---

## 4. Conclusion

- **Negative Rest Days/Miles**: Effectively fixed! The sanitation steps `max(0.0, rest_days)` and `max(0.0, travel_miles)` prevent any negative input propagation or overflow crash.
- **Extreme Negative Dixon-Coles Rho**: Negative probabilities are effectively fixed via `max(0.0, factor)`. However, extremely negative `rho` values ($<-1e308$) still cause float overflow to `inf` and result in `nan` values throughout grid normalization.
- **Negative Binomial Parameters, Temperature Boundary, Negative Acclimation Days, Negative Grid Sizes**: These still present active mathematical crash vectors (`ValueError`, `OverflowError`, `KeyError`) as detailed in the observations.

---

## 5. Verification Method

To verify these issues, run the following Python scripts or commands (if permission constraints permit):

```python
import predictor

# 1. Reproducing the Negative Binomial Overflow Crash
try:
    predictor.negative_binomial_probability(k=2, mu=10.0, alpha=1e308)
except ValueError as e:
    print("NB Overflow Crash Verified:", e)

# 2. Reproducing the WBGT boundary Overflow Crash
try:
    predictor.calculate_wbgt(temperature=-237.3000000001, humidity=50.0)
except OverflowError as e:
    print("WBGT Overflow Crash Verified:", e)

# 3. Reproducing the Acclimation Overflow Crash
try:
    predictor.calculate_altitude_factor(elevation=1500.0, acclimation_days=-5000.0)
except OverflowError as e:
    print("Altitude Acclimation Overflow Crash Verified:", e)

# 4. Reproducing the Negative Grid Size KeyError Crash
try:
    config = predictor.MatchModelConfig(
        dist_type=predictor.ModelDistribution.POISSON,
        mu_a=1.5,
        mu_b=1.2,
        max_goals=-1
    )
    predictor.generate_joint_grid(config)
except KeyError as e:
    print("Negative Grid Size KeyError Verified:", e)
```

### Invalidation Conditions:
- If the above script executes without throwing any exceptions or raising `ValueError`, `OverflowError`, or `KeyError`.

---

## 6. Adversarial Review Challenges

**Overall risk assessment**: MEDIUM / HIGH

### [High] Challenge 1: Unprotected Exponential Term in WBGT Calculation
- **Assumption challenged**: That the denominator check `denom == 0` is sufficient to protect the exponential humidity curve from division-by-zero or overflow issues.
- **Attack scenario**: A user inputs temperature values in $[-243.21, -237.3)$.
- **Blast radius**: The engine crashes with `OverflowError: math range error`.
- **Mitigation**: Clip `temperature` to a minimum physical limit (e.g. `max(-50.0, temperature)`) before calculation.

### [High] Challenge 2: Large NB Parameter Overflow to inf
- **Assumption challenged**: That `alpha * mu < 1e-15` covers all numerical instability vectors in the Negative Binomial engine.
- **Attack scenario**: Highly dispersed distributions with very large expected goals or dispersion inputs.
- **Blast radius**: Crashes with `ValueError: math domain error`.
- **Mitigation**: Check if `alpha * mu > 1e15` (or when `p` becomes `0.0`) and return a suitable fallback or boundary approximation instead of calling `math.log(0.0)`.

### [Medium] Challenge 3: Unsanitized Acclimation Parameters
- **Assumption challenged**: That acclimation day values provided by external configuration dicts are always positive.
- **Attack scenario**: An administrative bug or incomplete form outputs negative acclimation days.
- **Blast radius**: The contextual factor curves crash with `OverflowError: math range error`.
- **Mitigation**: Sanitize acclimation inputs to be non-negative (e.g. `acclimation_days = max(0.0, acclimation_days)`) before passing to altitude or thermal factor curves.

### [Medium] Challenge 4: Missing Key in Negative Grid Fallback
- **Assumption challenged**: That the fallback grid point is always present in the generated grid structure.
- **Attack scenario**: Config has `max_goals < 0`.
- **Blast radius**: `KeyError` crashes the grid normalization routine.
- **Mitigation**: Ensure `max_goals` is clamped to a non-negative value (e.g. `max_goals = max(0, min(100, config.max_goals))`).
