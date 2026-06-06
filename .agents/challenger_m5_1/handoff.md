# Handoff Report — 2026-06-03T18:51:39Z

## 1. Observation
We reviewed and analyzed the implementation source files `predictor.py`, `solver.py`, and `backtest.py` and identified several gaps, bugs, and weaknesses:

*   **`predictor.py` - String Float Input Bug**:
    In `negative_binomial_probability` (lines 46-52):
    ```python
    def negative_binomial_probability(k: int, mu: float, alpha: float) -> float:
        alpha_is_nan = math.isnan(alpha) if isinstance(alpha, (int, float)) else True
        alpha_is_inf = math.isinf(alpha) if isinstance(alpha, (int, float)) else False
        ...
        try:
            alpha = float(alpha)
            ...
        if alpha_is_nan or alpha_is_inf or alpha > 1e15:
            return poisson_probability(k, mu)
    ```
    When `alpha` is a string representation of a float (e.g. `"0.5"`), `isinstance(alpha, (int, float))` evaluates to `False`, causing `alpha_is_nan` to be `True`. This causes the condition `alpha_is_nan or ...` to evaluate to `True`, causing the function to incorrectly fall back to Poisson.

*   **`predictor.py` - Direct helper call crashes**:
    Direct calls to helper functions (like `calculate_altitude_factor`, `calculate_wbgt`, `calculate_travel_penalty`, `calculate_context_adjustments`, and `get_adjusted_lambdas`) with `None` values trigger crashes such as `TypeError: must be real number, not NoneType` because `math.isnan(None)` or operations are performed directly without sanitization.

*   **`predictor.py` - Status normalization failure**:
    In `get_adjusted_lambdas`, status strings are extracted from contexts and passed directly to `calculate_context_adjustments` without normalization. Variations like `"True_Home"` or `"co-host"` fail to match `"True Home"` or `"Co-Host"` in `host_att_map` and are silently treated as `"Neutral"` (yielding 0.0 adjustments).

*   **`solver.py` - Floating point tip vulnerability**:
    In `get_points` (lines 8-32), values are compared directly. Floating-point tips (e.g. tipping `1.5` goals when actual goals is `2`) evaluate to `3` points instead of being rejected or returning `0` points because of float comparisons.

*   **`backtest.py` - Scientific notation parsing bug**:
    In `load_match_data` (line 175):
    ```python
    if '.' in val_str:
        match_dict[key] = float(val_str)
    else:
        match_dict[key] = int(val_str)
    ```
    If temperature/humidity/elevation are in scientific notation without a dot (e.g., `"1e3"`), it tries to cast to `int` which fails, and it falls back to storing `"1e3"` as a string. This string causes a `TypeError` crash later during calculations in `calculate_wbgt`.

*   **`backtest.py` - Empty match / tie assertion failure**:
    In `main()` (line 347):
    ```python
    assert report['optimized_total_points'] > report['baseline_total_points'], ...
    ```
    If the CSV is empty or both models score the same total points, `report['optimized_total_points']` and `report['baseline_total_points']` are both `0.0`. The assertion fails and crashes the script instead of outputting a clean summary report.

## 2. Logic Chain
1. In `predictor.py`, checking `isinstance` before float conversion results in `alpha_is_nan` being set to `True` for string representations of floats. This causes the function to short-circuit and return `poisson_probability` instead of negative binomial probability.
2. In `predictor.py`, the lack of `None` checks before calling `math.isnan` results in a `TypeError` when helpers are called directly with `None` inputs.
3. In `get_adjusted_lambdas`, the lack of casing and underscore normalization on context status strings causes them to default to `"Neutral"` in `calculate_context_adjustments`, ignoring host advantages.
4. In `solver.py`, the lack of float tip rejection in `get_points` allows float differences to match integer differences, giving positive scores to float tips.
5. In `backtest.py`, checking for floats via `'.' in val_str` misses scientific notation floats like `"1e3"`. This causes them to be stored as strings and crash the calculation engine later.
6. In `backtest.py`, the hard assertion `assert report['optimized_total_points'] > report['baseline_total_points']` causes a crash when running empty datasets or tie games.

## 3. Caveats
- Argparse in CLI mains performs some sanitization, but direct API integration remains vulnerable.
- We assumed standard Python 3.10+ behaviour.
- We did not verify performance/time complexity of very large inputs above 100 as they are clamped.

## 4. Conclusion
The World Cup 2026 Prediction Engine has multiple validation, parsing, and type-checking bugs that cause incorrect fallback logic, silent loss of host advantage parameters, and crashes under extreme inputs.

## 5. Verification Method
Run the newly created adversarial test cases in `tests/test_adversarial_c1.py` using:
```bash
python3 -m unittest tests/test_adversarial_c1.py
```
Check that all tests run successfully (since they assert that these bugs and crashes occur as described).

Path to new test file: `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/tests/test_adversarial_c1.py`
