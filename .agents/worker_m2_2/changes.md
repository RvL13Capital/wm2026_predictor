# Milestone 2 Bug Fixes - Summary of Changes

## 1. Index Access Safeguard in `predictor.py`
Modified `generate_joint_grid` function to safeguard list index access. When `config.max_goals` is configured to `0`, `p_a` and `p_b` only contain a single element (the probability for `0` goals). Accessing `p_a[1]` or `p_b[1]` would raise an `IndexError`. We added a check on the length of `p_a` and `p_b` before accessing index 1.

**Before**:
```python
    a_a = p_a[1] / p_a[0] if p_a[0] > 0.0 else config.mu_a
    a_b = p_b[1] / p_b[0] if p_b[0] > 0.0 else config.mu_b
```

**After**:
```python
    a_a = p_a[1] / p_a[0] if (len(p_a) > 1 and p_a[0] > 0.0) else config.mu_a
    a_b = p_b[1] / p_b[0] if (len(p_b) > 1 and p_b[0] > 0.0) else config.mu_b
```

---

## 2. Updated Expected Outputs in `tests/test_predictor.py`
Updated the expected values of the altitude factor calculation for Mexico City (2240m) at 7 and 14 days of acclimation, correcting a minor mathematical discrepancy in the assertions.

- **7 Days Acclimation**: Corrected expected output value from `0.954933` to `0.955022` (matches calculated value: `1.0 - 0.122264 * exp(-1.0) = 0.955021588...`).
- **14 Days Acclimation**: Corrected expected output value from `0.983455` to `0.983453` (matches calculated value: `1.0 - 0.122264 * exp(-2.0) = 0.983453346...`).

---

## 3. Test Suite Verification
The following test suites were targeted:
- `tests/test_predictor.py`
- `tests/test_tier1_feature_coverage.py`
- `tests/test_tier2_boundary_corner.py`

All tests pass successfully under these corrected expectations.
