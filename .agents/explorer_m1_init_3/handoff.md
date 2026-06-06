# Handoff Report: E2E Testing Infrastructure Design

## 1. Observation
- **Root Files**:
  - `PROJECT.md`: Milestone 1 (E2E Testing Track) is currently marked as `PLANNED`. Milestone 2 (Advanced Probability Engine) is marked as `IN_PROGRESS` with conversation ID `4f3269e2-ee07-40b5-a16d-ccb850258a93`.
  - `predictor.py`: Only contains the basic Bivariate Poisson model with Dixon-Coles adjustments. Arguments accepted include `--lambdaA`, `--lambdaB`, `--rho`, `--max_tip`, but lack parameters for Negative Binomial or contextual factors.
- **Scope File**:
  - `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/sub_orch_e2e_1/SCOPE.md` outlines the required test suite distribution:
    - Tier 1: Feature Coverage (>=5 cases per feature: F1-F4)
    - Tier 2: Boundary & Corner Cases (>=5 cases per feature: F1-F4)
    - Tier 3: Cross-Feature Combinations (>=4 cases)
    - Tier 4: Real-World Application Scenarios (>=5 scenarios)
    - Total minimum: 49 cases.
- **Sibling Agent Explorer Prompts**:
  - `explorer_m2_1` focuses on Dixon-Coles & Negative Binomial.
  - `explorer_m2_2` focuses on Altitude and Climate factors.
  - `explorer_m2_3` focuses on Travel, Rest, and Fan/Host support factors.

---

## 2. Logic Chain
1. Since the core probability models and contextual features are not yet implemented in `predictor.py`, the E2E test cases must serve as a **functional contract** for the implementation phase.
2. An opaque-box CLI-based testing model is designed where `tests/run_e2e.py` runs commands against the python executables via subprocess and verifies printed values or outputs.
3. To facilitate automated parsing, a `--json` argument contract is proposed for `predictor.py` and `backtest.py`.
4. 49 test cases are cataloged to meet the target requirements of `sub_orch_e2e_1/SCOPE.md`: 20 coverage cases, 20 boundary cases, 4 cross-feature combinations, and 5 real-world scenarios.
5. The design has been written to `TEST_INFRA.md` which will serve as the project test specification.
6. `PROJECT.md` must be updated to change Milestone 1 status to `IN_PROGRESS` and link the parent conversation ID.

---

## 3. Caveats
- **CLI Argument Contract**: The E2E tests assume a specific CLI schema for the new features. If the implementation team implements different CLI flag names, the test configuration parameters will need to be matched.
- **Numerical Stability**: Floating-point assertions in tests assume default double precision calculations; small variance tolerance ($\pm 1e-6$) might need to be relaxed based on actual implementation.
- **No live execution**: As a read-only exploration agent, I cannot run `pytest` or execute the proposed test suite because the implementation files have not been created or updated yet.

---

## 4. Conclusion
- The E2E testing infrastructure is designed completely.
- A suite of 49 test cases covers all features (F1-F4), boundaries, combinations, and real-world scenarios.
- The design has been written to `analysis.md` in the agent's folder, ready to be created as `TEST_INFRA.md` at the project root.
- The `PROJECT.md` modifications are detailed and ready to be applied.

---

## 5. Verification Method
1. Inspect the `analysis.md` file in this directory to confirm that all 49 test cases are fully detailed with IDs, Inputs, and Expected Outcomes.
2. Confirm the implementation agent successfully creates `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/TEST_INFRA.md` with the proposed content.
3. Confirm that the implementer updates `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/PROJECT.md` by setting Milestone 1 status to `IN_PROGRESS` and adding the parent conversation ID (`4606a3e4-1e6e-445b-8297-9307c4ee54d6`).

---

## 6. Remaining Work (Handoff for Implementation)
1. **Apply Design**:
   - Create `TEST_INFRA.md` in the root workspace using the content specified in `analysis.md`.
   - Edit `PROJECT.md` to set Milestone 1 status to `IN_PROGRESS` and record the conversation ID `4606a3e4-1e6e-445b-8297-9307c4ee54d6`.
2. **Implement Runner & Data**:
   - Create `tests/run_e2e.py` to parse `tests/test_cases.json`, run `predictor.py` or `backtest.py` via subprocess, parse outputs, and log results.
   - Create test datasets: `data/wc2022_test.csv`, `data/wc2022_context.csv`, `data/empty.csv`, `data/single_match.csv`, `data/malformed.csv`, and `data/all_draws.csv` in a new `data/` directory.
   - Populate `tests/test_cases.json` with the 49 test definitions.
3. **Execute and Verify**:
   - Run the E2E runner: `python3 tests/run_e2e.py`
   - Integrate runner execution into the project test command.
