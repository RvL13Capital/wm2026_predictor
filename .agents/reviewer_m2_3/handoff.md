# Reviewer Handoff Report for Milestone 2

## 1. Observation

During my review of the implementation in `predictor.py` and the test files, I ran the following commands and observed the outputs below:

### Command 1: `python3 -m unittest tests/test_predictor.py`
**Output**:
```
.........
----------------------------------------------------------------------
Ran 9 tests in 0.000s

OK
```

### Command 2: `python3 -m unittest tests/test_tier1_feature_coverage.py`
**Output**:
```
...............sssss
----------------------------------------------------------------------
Ran 20 tests in 0.007s

OK (skipped=5)
```
*(Note: The 5 skipped tests are for Feature 4 / Backtester, which is expected since it is out of scope for Milestone 2).*

### Command 3: `python3 -m unittest tests/test_tier2_boundary_corner.py`
**Output**:
```
.....E.........sssss
======================================================================
ERROR: test_t2_f2_dual_host_neutralization (tests.test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f2_dual_host_neutralization)
Tests host advantages when two hosts play each other or a host plays at neutral ground.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_tier2_boundary_corner.py", line 115, in test_t2_f2_dual_host_neutralization
    self.assertAlmostEqual(lambda_A, 1.5 * math.exp(0.03 - 0.02))
                                           ^^^^
NameError: name 'math' is not defined. Did you forget to import 'math'?

----------------------------------------------------------------------
Ran 20 tests in 0.010s

FAILED (errors=1, skipped=5)
```

### Command 4: `python3 -m unittest tests/test_tier4_real_world.py` (Extended verification)
**Output**:
```
....F
======================================================================
FAIL: test_t4_rw5_italy_uruguay_draw (tests.test_tier4_real_world.TestTier4RealWorld.test_t4_rw5_italy_uruguay_draw)
Simulates defensive Italy (lambda = 1.0) vs. Uruguay (lambda = 1.0) with Dixon-Coles draw inflation.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_tier4_real_world.py", line 135, in test_t4_rw5_italy_uruguay_draw
    self.assertEqual(optimal_tip[0], optimal_tip[1], f"Expected a draw tip, but got {optimal_tip}")
AssertionError: 0 != 1 : Expected a draw tip, but got (0, 1)

----------------------------------------------------------------------
Ran 5 tests in 0.001s

FAILED (failures=1)
```

### Code Snippets of Interest

In `predictor.py` (lines 274-275), the `max_goals = 0` handling:
```python
    a_a = p_a[1] / p_a[0] if (len(p_a) > 1 and p_a[0] > 0.0) else config.mu_a
    a_b = p_b[1] / p_b[0] if (len(p_b) > 1 and p_b[0] > 0.0) else config.mu_b
```

In `tests/test_predictor.py` (lines 70-99), the altitude factor assertions:
```python
    def test_altitude_factor(self):
        # Low altitude
        self.assertEqual(calculate_altitude_factor(500, 0), 1.0)
        
        # Guadalajara (1560m)
        self.assertAlmostEqual(calculate_altitude_factor(1560, 0), 0.950496, places=5)
        self.assertAlmostEqual(calculate_altitude_factor(1560, 7), 0.981789, places=5)
        
        # Mexico City (2240m)
        self.assertAlmostEqual(calculate_altitude_factor(2240, 0), 0.877736, places=5)
        self.assertAlmostEqual(calculate_altitude_factor(2240, 7), 0.955022, places=5)
        self.assertAlmostEqual(calculate_altitude_factor(2240, 14), 0.983453, places=5)
```

---

## 2. Logic Chain

1. **IndexError on `max_goals = 0` resolution**:
   - As observed in `predictor.py`, `a_a` and `a_b` are calculated with a guard `len(p_a) > 1`.
   - If `max_goals = 0`, `len(p_a)` is 1. The check fails, and it falls back to `config.mu_a` without attempting to access `p_a[1]`.
   - This prevents the `IndexError` completely.
   - Therefore, Claim 1 ("The IndexError on max_goals = 0 is resolved") is **verified as resolved**.

2. **Altitude factor test assertions**:
   - As observed in `tests/test_predictor.py`, the assertions use exact mathematical values that align with the acclimation formula:
     $$h = (E - 1000) / 1000$$
     $$\text{base\_loss} = 0.08h + 0.015h^2$$
     $$\text{factor} = 1.0 - \text{base\_loss} \times e^{-A/7}$$
   - For Mexico City at 7 days acclimation, the assertion checks `0.955022`, which matches the calculated value $1.0 - 0.122264 \times e^{-1} \approx 0.95502158$.
   - Therefore, Claim 2 ("The altitude factor test assertions are corrected") is **verified as correct**.

3. **Rest of implementation correctness**:
   - Under symmetric conditions ($\lambda_A=\lambda_B=1.0$) and a small draw inflation factor ($\rho=-0.1$), the Kicktipp solver evaluates the expected values of all possible tips.
   - According to Kicktipp scoring rules implemented in `get_points`, tipping a draw (e.g. `(1, 1)`) only yields 2 points for a different draw (due to the `diff_actual == 0` rule), whereas tipping a 1-goal win (e.g. `(0, 1)`) yields 3 points for a different 1-goal win (e.g. `(1, 2)`, `(2, 3)`).
   - This asymmetric points ruleset means that under symmetric conditions, the expected value of tipping `(0, 1)` is $0.988$ points, whereas tipping `(1, 1)` is $0.969$ points.
   - Because of this, the solver correctly recommends `(0, 1)` or `(1, 0)` rather than a draw.
   - The test `test_t4_rw5_italy_uruguay_draw` in `tests/test_tier4_real_world.py` incorrectly asserts that the optimal tip must be a draw for $\rho=-0.1$. For the solver to recommend a draw, a stronger draw inflation is required (e.g., $\rho = -0.2$ yields an EV of $1.050$ for `(0, 0)` and `(1, 1)`, making draws optimal).
   - Therefore, the implementation in `predictor.py` is mathematically correct, but the test suite has incorrect test assertions and missing imports.

---

## 3. Caveats

- I did not review the backtesting runner implementations because the backtester file (`backtest.py`) has not yet been built (which is designated for Milestone 4).
- I assumed the scoring logic specified in `PROJECT.md` is the ground truth.

---

## 4. Conclusion & Review Report

**Verdict**: **REQUEST_CHANGES**

### Findings

#### [Major] Finding 1: Missing Import in Test File
- **What**: The module `math` is used in assertions but is not imported.
- **Where**: `tests/test_tier2_boundary_corner.py` at line 115:
  ```python
  self.assertAlmostEqual(lambda_A, 1.5 * math.exp(0.03 - 0.02))
  ```
- **Why**: Running the boundary test suite fails with a `NameError: name 'math' is not defined`.
- **Suggestion**: Add `import math` to the top of `tests/test_tier2_boundary_corner.py`.

#### [Major] Finding 2: Flawed Test Assertion for Draw Tips
- **What**: The real-world test suite asserts that a draw tip is optimal under low draw inflation, which is mathematically false under Kicktipp rules.
- **Where**: `tests/test_tier4_real_world.py` at line 135:
  ```python
  self.assertEqual(optimal_tip[0], optimal_tip[1], f"Expected a draw tip, but got {optimal_tip}")
  ```
- **Why**: Due to Kicktipp's asymmetry where non-exact draws only yield 2 points, the EV of a draw tip is lower than a 1-goal margin tip unless draw inflation is strong enough. For $\lambda=1.0$, a $\rho=-0.1$ is insufficient to make a draw optimal.
- **Suggestion**: Change the test parameter to `rho=-0.2` in line 132 so that a draw tip becomes mathematically optimal, or adjust the assertion.

#### [Minor] Finding 3: Unused Parameters in Signature
- **What**: The parameters `opponent_status` and `opponent_travel_penalty` are accepted but never used in the function body.
- **Where**: `predictor.py` at lines 140-151 (`calculate_context_adjustments`).
- **Why**: Code clutter, though not causing incorrect behavior since `get_adjusted_lambdas` passes correct values and coordinates the compounding correctly.
- **Suggestion**: Clean up the unused signature parameters or document why they are kept.

### Verified Claims

- **Claim 1**: IndexError on `max_goals = 0` is resolved.
  - *Method*: Verified via inspect and running `test_t2_f1_minimal_grid_size` in `tests/test_tier2_boundary_corner.py`.
  - *Status*: PASS
- **Claim 2**: Altitude factor test assertions are corrected.
  - *Method*: Verified calculations and compared them against `test_altitude_factor` in `tests/test_predictor.py`.
  - *Status*: PASS
- **Claim 3**: The Negative Binomial dispersion and environmental factors compile and behave according to specifications.
  - *Method*: Inspected equations and ran `test_predictor.py` and `test_tier1_feature_coverage.py`.
  - *Status*: PASS

---

## 5. Verification Method

To verify these issues independently:
1. Run `python3 -m unittest tests/test_tier2_boundary_corner.py` and observe the `NameError` crash.
2. Run `python3 -m unittest tests/test_tier4_real_world.py` and observe the `AssertionError` for `test_t4_rw5_italy_uruguay_draw`.
3. Check imports of `tests/test_tier2_boundary_corner.py` to confirm `math` is missing.
4. Verify the math of symmetric Kicktipp expected values via the script:
   ```bash
   python3 -c "import predictor; tips, _, _ = predictor.solve_optimal_tip(1.0, 1.0, rho=-0.1); print(tips[:3])"
   ```
