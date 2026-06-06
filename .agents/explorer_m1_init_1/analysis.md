# Analysis & E2E Testing Infrastructure Design

## 1. Introduction & Testing Philosophy
The E2E testing infrastructure for the FIFA World Cup 2026 prediction engine is designed to validate the integration and mathematical accuracy of the entire pipeline—from parsing historical data and stadium metadata to applying contextual adjustments, computing probabilities, and solving for optimal Kicktipp tips.

The E2E testing suite will follow an **opaque-box integration approach**:
- It will execute the system modules and command-line interfaces (CLIs) directly, passing inputs and verifying outputs.
- It will avoid deep mocking of the internal math routines to ensure that the composite systems (probability engine, solver, data loaders, backtester) work together correctly.
- Tests will be structured using Python's built-in `unittest` framework to avoid external dependencies, ensuring portability and speed.

---

## 2. Feature Inventory
The E2E testing suite validates the following four core features:
- **F1: Advanced Probability Engine**: Supports Bivariate Poisson with Dixon-Coles adjustments (to handle draw bias) and Negative Binomial distribution (to handle overdispersion/high-scoring blowouts).
- **F2: Contextual WM-Specific Factors**: Applies correction factors to team strength parameters ($\lambda$) based on stadium elevation (altitude acclimation), temperature/humidity (climate), travel mileage & timezone transitions (travel/rest days), and host nation fan support.
- **F3: Kicktipp Solver (EV Maximization)**: Iterates over the probability grid to output the optimal tip $(t_A, t_B)$ maximizing expected points under the strict 4/3/2 Kicktipp rules.
- **F4: Backtesting & Validation Suite**: Evaluates baseline vs. optimized model performance using historical World Cup 2022 match results, outputting comparative metrics.

---

## 3. Test Suite Architecture
The tests will be organized under the `tests/` directory at the project root:
- `tests/run_e2e.py`: The orchestrator script that executes all test files across all tiers and returns a unified report and exit code (0 on success, non-zero on failure).
- `tests/test_tier1_feature_coverage.py`: Contains test cases verifying feature coverage (5 cases per feature, total 20).
- `tests/test_tier2_boundary_corner.py`: Contains test cases verifying boundaries, limits, and invalid inputs (5 cases per feature, total 20).
- `tests/test_tier3_cross_feature.py`: Contains test cases verifying integration across features (total 4).
- `tests/test_tier4_real_world.py`: Contains real-world match scenario simulations validating realistic outputs (total 5).

---

## 4. Detailed Test Case Enumeration (49 Test Cases)

### Tier 1: Feature Coverage (20 Test Cases)

#### Feature 1: Advanced Probability Engine (F1)
1. **`test_t1_f1_poisson_grid_sum`**:
   - *Description*: Validates that a standard generated Poisson probability grid sums to exactly 1.0 (within $10^{-6}$ tolerance) after normalization.
   - *Expected Behavior*: Cumulative sum of the matrix elements equals 1.0.
2. **`test_t1_f1_dixon_coles_adjustment`**:
   - *Description*: Verifies that applying a positive Dixon-Coles parameter ($\rho = 0.1$) inflates low-scoring draw probabilities (0-0, 1-1) compared to the independent baseline.
   - *Expected Behavior*: $P(0,0)$ and $P(1,1)$ are strictly higher under Dixon-Coles than the baseline.
3. **`test_t1_f1_neg_binomial_overdispersion`**:
   - *Description*: Verifies that the Negative Binomial distribution models overdispersion such that variance exceeds the mean when $\alpha > 0$.
   - *Expected Behavior*: The variance of generated goals is higher than the expected goals ($\lambda$).
4. **`test_t1_f1_prob_bounds`**:
   - *Description*: Verifies that all individual cells in the probability grid are bounded within $[0.0, 1.0]$.
   - *Expected Behavior*: No cell has a probability $< 0$ or $> 1$.
5. **`test_t1_f1_grid_size_scaling`**:
   - *Description*: Evaluates the grid scaling behavior when changing `max_goals` (e.g. from 5 to 15).
   - *Expected Behavior*: Grid dimension is exactly $(\text{max\_goals} + 1) \times (\text{max\_goals} + 1)$ and sums to 1.0.

#### Feature 2: Contextual WM-Specific Factors (F2)
6. **`test_t1_f2_altitude_degradation`**:
   - *Description*: Verifies that stadium altitude above sea level degrades the team strength ($\lambda$) of a non-acclimated team.
   - *Expected Behavior*: The adjusted $\lambda$ is strictly lower than the base $\lambda$.
7. **`test_t1_f2_climate_humidity_penalty`**:
   - *Description*: Verifies that high temperature and humidity (high heat index) degrade performance for both teams.
   - *Expected Behavior*: Both teams' lambdas are scaled down under hot/humid weather parameters.
8. **`test_t1_f2_travel_fatigue_penalty`**:
   - *Description*: Verifies that travel mileage (distance) and timezone transitions reduce team strength.
   - *Expected Behavior*: Lambda decreases proportionally to travel distance and timezone difference.
9. **`test_t1_f2_host_advantage_boost`**:
   - *Description*: Verifies that host countries (USA, Mexico, Canada) receive a positive boost to their base $\lambda$.
   - *Expected Behavior*: Host nation's adjusted lambda is higher than its baseline strength.
10. **`test_t1_f2_multi_factor_compounding`**:
    - *Description*: Ensures that applying all four factors simultaneously scales lambda correctly without causing invalid negative values.
    - *Expected Behavior*: Compounded multipliers yield a final strength factor between 0.2 and 1.5.

#### Feature 3: Kicktipp Solver (EV Maximization) (F3)
11. **`test_t1_f3_exact_score_points`**:
    - *Description*: Verifies that the point calculator returns exactly 4 points for an exact match.
    - *Expected Behavior*: `get_points(2, 1, 2, 1)` returns 4.
12. **`test_t1_f3_difference_points`**:
    - *Description*: Verifies that matching the goal difference and tendency returns exactly 3 points.
    - *Expected Behavior*: `get_points(2, 1, 3, 2)` returns 3.
13. **`test_t1_f3_tendency_points`**:
    - *Description*: Verifies that matching the tendency only returns exactly 2 points.
    - *Expected Behavior*: `get_points(2, 0, 3, 2)` returns 2.
14. **`test_t1_f3_draw_tendency_only`**:
    - *Description*: Verifies that if you tip a draw (e.g. 1-1) and the result is a different draw (e.g. 2-2), you get 2 points (tendency) and not 3 points (difference).
    - *Expected Behavior*: `get_points(1, 1, 2, 2)` returns 2.
15. **`test_t1_f3_ev_maximization`**:
    - *Description*: Verifies that the solver returns the tip that maximizes the mathematically expected value.
    - *Expected Behavior*: The top tip output has the maximum calculated expected value.

#### Feature 4: Backtesting & Validation Suite (F4)
16. **`test_t1_f4_data_loader`**:
    - *Description*: Verifies that the backtesting suite successfully parses a CSV file containing historical match results.
    - *Expected Behavior*: The parser returns a list of dictionaries with matching columns.
17. **`test_t1_f4_baseline_runner`**:
    - *Description*: Verifies that the baseline model can run over all games in the backtester without error.
    - *Expected Behavior*: Runs successfully and outputs baseline tips and points.
18. **`test_t1_f4_optimized_runner`**:
    - *Description*: Verifies that the optimized model executes over all backtest games.
    - *Expected Behavior*: Runs successfully and outputs optimized tips and points.
19. **`test_t1_f4_summary_report`**:
    - *Description*: Verifies that the final comparison report prints average points and total points.
    - *Expected Behavior*: Summary contains comparisons and total points.
20. **`test_t1_f4_points_accumulation_integrity`**:
    - *Description*: Checks that total points in the backtest report match the sum of individual game scores.
    - *Expected Behavior*: Total points sum matches the step-by-step game point sum.

---

### Tier 2: Boundary & Corner Cases (20 Test Cases)

#### Feature 1: Advanced Probability Engine (F1)
21. **`test_t2_f1_zero_lambda`**:
    - *Description*: Tests the engine with a team lambda of 0.0.
    - *Expected Behavior*: No division by zero; probability of 0 goals is 1.0, all other goal amounts have probability 0.0.
22. **`test_t2_f1_extreme_high_lambda`**:
    - *Description*: Evaluates calculations at extremely high lambdas (e.g., $\lambda = 15.0$).
    - *Expected Behavior*: No math overflow/underflow; correct distribution centering around 15.
23. **`test_t2_f1_extreme_dixon_coles_rho`**:
    - *Description*: Evaluates extreme $\rho$ values (e.g., $+1.5$, $-1.5$) which could result in negative adjustment factors.
    - *Expected Behavior*: The adjustment is clipped at $0.0$ (`max(0.0, factor)`) and renormalized correctly.
24. **`test_t2_f1_minimal_grid_size`**:
    - *Description*: Evaluates probability grid with `max_goals = 0`.
    - *Expected Behavior*: Returns a 1x1 matrix containing $P(0,0) = 1.0$.
25. **`test_t2_f1_negative_binomial_alpha_limit`**:
    - *Description*: Verifies behavior when Negative Binomial $\alpha \to 0$.
    - *Expected Behavior*: The distribution converges to standard Poisson.

#### Feature 2: Contextual WM-Specific Factors (F2)
26. **`test_t2_f2_extreme_elevation_cap`**:
    - *Description*: Simulates matches at extreme elevations (e.g., 4000m above sea level).
    - *Expected Behavior*: Degradation is capped at a maximum threshold to prevent the lambda from falling to zero or negative.
27. **`test_t2_f2_extreme_wet_bulb`**:
    - *Description*: Simulates a match under extreme heat index (e.g., 45°C, 95% humidity).
    - *Expected Behavior*: Climate penalty scales to its maximum cap and does not go below a minimum team strength threshold.
28. **`test_t2_f2_zero_travel`**:
    - *Description*: Simulates a match with 0 km travel and same timezone.
    - *Expected Behavior*: Travel modifier is exactly 1.0 (no degradation).
29. **`test_t2_f2_dual_host_neutralization`**:
    - *Description*: Tests host advantages when two hosts play each other or a host plays at neutral ground.
    - *Expected Behavior*: Host advantage applies correctly based on tournament regulations.
30. **`test_t2_f2_rest_days_extremes`**:
    - *Description*: Evaluates travel fatigue with 0 rest days versus 30 rest days.
    - *Expected Behavior*: 0 rest days yields maximum travel penalty; 30 rest days yields 0 penalty.

#### Feature 3: Kicktipp Solver (EV Maximization) (F3)
31. **`test_t2_f3_flat_probability_grid`**:
    - *Description*: Tests the solver with a flat probability distribution.
    - *Expected Behavior*: Ties in EV are resolved deterministically without crashing.
32. **`test_t2_f3_extreme_tip_limit`**:
    - *Description*: Tests the solver with `max_tip = 0`.
    - *Expected Behavior*: The only tip considered is (0, 0), which is returned.
33. **`test_t2_f3_certainty_grid`**:
    - *Description*: Sets probability of a specific score (e.g., 3-1) to 1.0 and all others to 0.0.
    - *Expected Behavior*: Solver returns exactly (3, 1) with an EV of 4.0.
34. **`test_t2_f3_skewed_win_distribution`**:
    - *Description*: Tests a highly skewed win distribution.
    - *Expected Behavior*: Solver tips the score that maximizes expected points (which might not be the most probable score due to the 4/3/2 reward structure).
35. **`test_t2_f3_high_score_tipping_limit`**:
    - *Description*: Evaluates tipping options when `max_tip` is much larger than `max_goals`.
    - *Expected Behavior*: Tips above `max_goals` evaluate to an expected value based on the grid constraints.

#### Feature 4: Backtesting & Validation Suite (F4)
36. **`test_t2_f4_empty_dataset`**:
    - *Description*: Runs the backtester with an empty match CSV file.
    - *Expected Behavior*: Graceful exit, prints a warning, and reports 0 games.
37. **`test_t2_f4_malformed_columns`**:
    - *Description*: Runs backtester with missing score columns or malformed values.
    - *Expected Behavior*: The bad lines are skipped with a warning, and the remaining matches are processed.
38. **`test_t2_f4_missing_stadium_metadata`**:
    - *Description*: Simulates a match in an unknown stadium.
    - *Expected Behavior*: Falls back to baseline defaults (sea level, neutral climate) without failing.
39. **`test_t2_f4_underperforming_model_reporting`**:
    - *Description*: Asserts that if the optimized model performs worse than the baseline, the delta is reported as negative.
    - *Expected Behavior*: Report accurately displays negative improvement.
40. **`test_t2_f4_high_volume_stress`**:
    - *Description*: Evaluates backtester performance with a large mock historical dataset (e.g., 1000 games).
    - *Expected Behavior*: Compiles and executes in under 5 seconds.

---

### Tier 3: Cross-Feature Combinations (4 Test Cases)

41. **`test_t3_cf1_elevation_draw_solver`**:
    - *Description*: Integrates altitude adjustments, Dixon-Coles draw adjustments, and the solver. A high-altitude match that reduces goal expectations, combined with Dixon-Coles draw adjustments, should shift the optimal tip from a high-scoring win (e.g., 2-1) to a low-scoring draw (e.g., 1-1).
    - *Expected Behavior*: Shift in optimal tip output matches mathematical expectations.
42. **`test_t3_cf2_nb_travel_solver`**:
    - *Description*: Integrates the Negative Binomial model, severe travel fatigue, and the solver. A fatigued team playing against a high-scoring team under the overdispersed NB model should shift the solver's tip towards a high-scoring blowout win for the opponent to maximize EV.
    - *Expected Behavior*: The optimal tip adapts to the wider variance tail of the NB distribution.
43. **`test_t3_cf3_host_climate_solver`**:
    - *Description*: Integrates host advantage, climate penalty, and the solver. The host team's boost offsets a harsh climate penalty, while the opponent suffers the full climate degradation.
    - *Expected Behavior*: Solver tip adapts to the home team's relative advantage.
44. **`test_t3_cf4_backtest_pipeline_integration`**:
    - *Description*: Executes the complete pipeline from parsing metadata, running the bivariate Poisson model, applying contextual factor changes, solving for Kicktipp EV tips, and comparing baseline vs. optimized points.
    - *Expected Behavior*: Pipeline runs end-to-end without exceptions, returning consistent final scores.

---

### Tier 4: Real-World Application Scenarios (5 Test Cases)

45. **`test_t4_rw1_mexico_city_azteca`**:
    - *Description*: Simulates Mexico vs. Germany at Estadio Azteca (2240m altitude). Germany has severe travel fatigue (travel from Munich) and no altitude acclimation; Mexico is the host and is acclimated.
    - *Expected Behavior*: Germany's lambda is heavily degraded; Mexico's lambda is boosted. The solver tips a Mexico win (e.g., 2-0 or 2-1).
46. **`test_t4_rw2_miami_heat_humidity`**:
    - *Description*: Simulates Ecuador vs. England in Miami in July (36°C, 85% humidity). Both teams suffer extreme climate penalties.
    - *Expected Behavior*: Both teams' lambdas are significantly reduced, concentrating the probability grid on low scores, resulting in a 1-0 or 1-1 tip.
47. **`test_t4_rw3_canada_vancouver_travel`**:
    - *Description*: Simulates Canada vs. Japan in Vancouver. Japan travels 8,000+ km, transitions 9 timezones, and has 3 rest days. Canada has host advantage.
    - *Expected Behavior*: Japan suffers high travel degradation; Canada is boosted. Solver tips Canada win.
48. **`test_t4_rw4_france_nb_blowout`**:
    - *Description*: Simulates France ($\lambda = 3.5$) vs. Saudi Arabia ($\lambda = 0.5$) using the Negative Binomial model to evaluate blowouts.
    - *Expected Behavior*: High-scoring French blowout tips (e.g., 4-0 or 4-1) yield higher expected points than standard Poisson.
49. **`test_t4_rw5_italy_uruguay_draw`**:
    - *Description*: Simulates defensive Italy ($\lambda_A = 1.0$) vs. Uruguay ($\lambda_B = 1.0$) with Dixon-Coles draw inflation.
    - *Expected Behavior*: Draw probability increases, leading the solver to recommend tipping 1-1.

---

## 5. Proposed Content for `TEST_INFRA.md`
This file will be created at the project root by the implementation team. It establishes the test suite design and run instructions.

```markdown
# E2E Testing Infrastructure

This document outlines the end-to-end (E2E) testing framework for the FIFA World Cup 2026 Prediction Engine.

## Testing Philosophy
- **Opaque-Box Verification**: Test execution utilizes the public CLI interfaces and high-level module APIs.
- **Zero External Dependencies**: All tests run using Python's standard `unittest` library.
- **Strict Tiered Validation**:
  - **Tier 1**: Feature Coverage (20 test cases checking core logic).
  - **Tier 2**: Boundary & Corner Cases (20 test cases verifying limits, nulls, and extreme values).
  - **Tier 3**: Cross-Feature Combinations (4 test cases validating component interaction).
  - **Tier 4**: Real-World Scenarios (5 scenarios simulating specific matches).

## Directory Structure
```text
tests/
├── run_e2e.py                     # E2E Test Suite Orchestrator
├── test_tier1_feature_coverage.py  # Feature-specific tests
├── test_tier2_boundary_corner.py  # Extreme inputs, limit tests
├── test_tier3_cross_feature.py     # Component integrations
└── test_tier4_real_world.py        # Real-world simulations
```

## Running the E2E Test Suite
To run all tests across all tiers, run:
```bash
python3 tests/run_e2e.py
```

To run a specific test tier (e.g. Tier 1):
```bash
python3 -m unittest tests/test_tier1_feature_coverage.py
```
```

---

## 6. Proposed Edits for `PROJECT.md`
We propose updating the status of Milestone 1 in `PROJECT.md` to `IN_PROGRESS` and adding the conversation ID.

### Proposed Changes to Milestones Table:
*Target Content (line 12 of `PROJECT.md`):*
```markdown
| 1 | E2E Testing Track | Design and build the E2E test suite (Tiers 1-4) | None | PLANNED |
```

*Replacement Content:*
```markdown
| 1 | E2E Testing Track | Design and build the E2E test suite (Tiers 1-4) | None | IN_PROGRESS (Conv: 4606a3e4-1e6e-445b-8297-9307c4ee54d6) |
```

---

## 7. Verification Strategy
The validity of the E2E testing framework design can be verified by running the test orchestrator:
1. Ensure all test scripts (`test_tier1_feature_coverage.py`, etc.) are placed in the `tests/` directory.
2. Run `python3 tests/run_e2e.py`.
3. The orchestrator must run all 49 test cases and display a summary indicating $49/49$ tests executed.
