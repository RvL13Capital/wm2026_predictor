# Verification Report

This report presents the exact stdout of the E2E test suite execution and the backtesting comparison execution for the FIFA World Cup 2026 Prediction Engine.

## 1. E2E Test Suite Output

Command: `python3 tests/run_e2e.py`

```stdout
test_division_by_zero (test_challenger_robustness.TestChallengerRobustness.test_division_by_zero)
3. Verify robustness against division by zero ... ok
test_empty_grids (test_challenger_robustness.TestChallengerRobustness.test_empty_grids)
4. Verify robustness under empty grids ... ok
test_max_tip_greater_than_max_goals (test_challenger_robustness.TestChallengerRobustness.test_max_tip_greater_than_max_goals)
1. Verify robustness when max_tip > max_goals (e.g. max_tip=8, max_goals=3) ... ok
test_negative_inputs (test_challenger_robustness.TestChallengerRobustness.test_negative_inputs)
2. Verify robustness under negative inputs ... ok
test_very_large_parameters (test_challenger_robustness.TestChallengerRobustness.test_very_large_parameters)
5. Verify robustness under very large parameters ... ok
test_altitude_factor (test_predictor.TestPredictor.test_altitude_factor) ... ok
test_dixon_coles_normalization_fallback_extreme_lambda (test_predictor.TestPredictor.test_dixon_coles_normalization_fallback_extreme_lambda) ... ok
test_get_adjusted_lambdas (test_predictor.TestPredictor.test_get_adjusted_lambdas) ... ok
test_host_and_fan_adjustments (test_predictor.TestPredictor.test_host_and_fan_adjustments) ... ok
test_negative_binomial_probability (test_predictor.TestPredictor.test_negative_binomial_probability) ... ok
test_negative_binomial_stability_small_mu (test_predictor.TestPredictor.test_negative_binomial_stability_small_mu) ... ok
test_negative_travel_miles_penalty (test_predictor.TestPredictor.test_negative_travel_miles_penalty) ... ok
test_none_type_sanitization_contexts (test_predictor.TestPredictor.test_none_type_sanitization_contexts) ... ok
test_poisson_probability (test_predictor.TestPredictor.test_poisson_probability) ... ok
test_sum_to_one_negative_binomial (test_predictor.TestPredictor.test_sum_to_one_negative_binomial) ... ok
test_sum_to_one_poisson (test_predictor.TestPredictor.test_sum_to_one_poisson) ... ok
test_thermal_factor (test_predictor.TestPredictor.test_thermal_factor) ... ok
test_travel_penalty (test_predictor.TestPredictor.test_travel_penalty) ... ok
test_get_points_difference (test_solver.TestSolver.test_get_points_difference) ... ok
test_get_points_draw_difference_exception (test_solver.TestSolver.test_get_points_draw_difference_exception) ... ok
test_get_points_exact_score (test_solver.TestSolver.test_get_points_exact_score) ... ok
test_get_points_incorrect (test_solver.TestSolver.test_get_points_incorrect) ... ok
test_get_points_tendency (test_solver.TestSolver.test_get_points_tendency) ... ok
test_mathematical_equivalence (test_solver.TestSolver.test_mathematical_equivalence) ... ok
test_solve_optimal_tip_skewed_distribution (test_solver.TestSolver.test_solve_optimal_tip_skewed_distribution) ... ok
test_t1_f1_dixon_coles_adjustment (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f1_dixon_coles_adjustment)
Verifies that applying a negative Dixon-Coles parameter (rho = -0.1) inflates low-scoring draw probabilities (0-0, 1-1) compared to rho = 0.1. ... ok
test_t1_f1_grid_size_scaling (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f1_grid_size_scaling)
Evaluates the grid scaling behavior when changing max_goals (e.g. from 5 to 15). ... ok
test_t1_f1_neg_binomial_overdispersion (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f1_neg_binomial_overdispersion)
Verifies that the Negative Binomial distribution models overdispersion such that variance exceeds the mean when alpha > 0. ... ok
test_t1_f1_poisson_grid_sum (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f1_poisson_grid_sum)
Validates that a standard generated Poisson probability grid sums to exactly 1.0 (within 1e-6 tolerance) after normalization. ... ok
test_t1_f1_prob_bounds (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f1_prob_bounds)
Verifies that all individual cells in the probability grid are bounded within [0.0, 1.0]. ... ok
test_t1_f2_altitude_degradation (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f2_altitude_degradation)
Verifies that stadium altitude above sea level degrades the team strength of a non-acclimated team. ... ok
test_t1_f2_climate_humidity_penalty (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f2_climate_humidity_penalty)
Verifies that high temperature and humidity degrade performance for both teams. ... ok
test_t1_f2_host_advantage_boost (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f2_host_advantage_boost)
Verifies that host countries receive a positive boost to their base strength. ... ok
test_t1_f2_multi_factor_compounding (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f2_multi_factor_compounding)
Ensures that applying all four factors simultaneously scales lambda correctly without causing invalid negative values. ... ok
test_t1_f2_travel_fatigue_penalty (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f2_travel_fatigue_penalty)
Verifies that travel mileage (distance) and timezone transitions reduce team strength. ... ok
test_t1_f3_difference_points (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f3_difference_points)
Verifies that matching the goal difference and tendency returns exactly 3 points. ... ok
test_t1_f3_draw_tendency_only (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f3_draw_tendency_only)
Verifies that if you tip a draw (e.g. 1-1) and the result is a different draw (e.g. 2-2), you get 2 points (tendency) and not 3 points (difference). ... ok
test_t1_f3_ev_maximization (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f3_ev_maximization)
Verifies that the solver returns the tip that maximizes the mathematically expected value. ... ok
test_t1_f3_exact_score_points (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f3_exact_score_points)
Verifies that the point calculator returns exactly 4 points for an exact match. ... ok
test_t1_f3_tendency_points (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f3_tendency_points)
Verifies that matching the tendency only returns exactly 2 points. ... ok
test_t1_f4_baseline_runner (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f4_baseline_runner)
Verifies that the baseline model can run over all games in the backtester without error. ... ok
test_t1_f4_data_loader (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f4_data_loader)
Verifies that the backtesting suite successfully parses a CSV file containing historical match results. ... ok
test_t1_f4_optimized_runner (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f4_optimized_runner)
Verifies that the optimized model executes over all backtest games. ... ok
test_t1_f4_points_accumulation_integrity (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f4_points_accumulation_integrity)
Checks that total points in the backtest report match the sum of individual game scores. ... ok
test_t1_f4_summary_report (test_tier1_feature_coverage.TestTier1FeatureCoverage.test_t1_f4_summary_report)
Verifies that the final comparison report prints average points and total points. ... ok
test_t2_f1_extreme_dixon_coles_rho (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f1_extreme_dixon_coles_rho)
Evaluates extreme rho values (e.g., +1.5, -1.5) which could result in negative adjustment factors. ... ok
test_t2_f1_extreme_high_lambda (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f1_extreme_high_lambda)
Evaluates calculations at extremely high lambdas (e.g., lambda = 15.0). ... ok
test_t2_f1_minimal_grid_size (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f1_minimal_grid_size)
Evaluates probability grid with max_goals = 0. ... ok
test_t2_f1_negative_binomial_alpha_limit (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f1_negative_binomial_alpha_limit)
Verifies behavior when Negative Binomial alpha -> 0. ... ok
test_t2_f1_zero_lambda (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f1_zero_lambda)
Tests the engine with a team lambda of 0.0. ... ok
test_t2_f2_dual_host_neutralization (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f2_dual_host_neutralization)
Tests host advantages when two hosts play each other or a host plays at neutral ground. ... ok
test_t2_f2_extreme_elevation_cap (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f2_extreme_elevation_cap)
Simulates matches at extreme elevations (e.g., 4000m above sea level). ... ok
test_t2_f2_extreme_wet_bulb (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f2_extreme_wet_bulb)
Simulates a match under extreme heat index (e.g., 45°C, 95% humidity). ... ok
test_t2_f2_rest_days_extremes (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f2_rest_days_extremes)
Evaluates travel fatigue with 0 rest days versus 30 rest days. ... ok
test_t2_f2_zero_travel (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f2_zero_travel)
Simulates a match with 0 km travel and same timezone. ... ok
test_t2_f3_certainty_grid (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f3_certainty_grid)
Sets probability of a specific score to 1.0 by using lambda=0.0 (resulting in 0-0 being certain). ... ok
test_t2_f3_extreme_tip_limit (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f3_extreme_tip_limit)
Tests the solver with max_tip = 0. ... ok
test_t2_f3_flat_probability_grid (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f3_flat_probability_grid)
Tests the solver with a flat probability distribution (symmetric ties in expected value). ... ok
test_t2_f3_high_score_tipping_limit (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f3_high_score_tipping_limit)
Evaluates tipping options when max_tip is much larger than max_goals. ... ok
test_t2_f3_skewed_win_distribution (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f3_skewed_win_distribution)
Tests a highly skewed win distribution. The optimal tip must maximize expected points. ... ok
test_t2_f4_empty_dataset (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f4_empty_dataset)
Runs the backtester with an empty match CSV file. ... ok
test_t2_f4_high_volume_stress (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f4_high_volume_stress)
Evaluates backtester performance with a large mock historical dataset (e.g., 1000 games). ... ok
test_t2_f4_malformed_columns (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f4_malformed_columns)
Runs backtester with missing score columns or malformed values. ... ok
test_t2_f4_missing_stadium_metadata (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f4_missing_stadium_metadata)
Simulates a match in an unknown stadium. ... ok
test_t2_f4_underperforming_model_reporting (test_tier2_boundary_corner.TestTier2BoundaryCorner.test_t2_f4_underperforming_model_reporting)
Asserts that if the optimized model performs worse than the baseline, the delta is reported as negative. ... ok
test_t3_cf1_elevation_draw_solver (test_tier3_cross_feature.TestTier3CrossFeature.test_t3_cf1_elevation_draw_solver)
Integrates altitude adjustments, Dixon-Coles draw adjustments, and the solver. ... ok
test_t3_cf2_nb_travel_solver (test_tier3_cross_feature.TestTier3CrossFeature.test_t3_cf2_nb_travel_solver)
Integrates the Negative Binomial model, severe travel fatigue, and the solver. ... ok
test_t3_cf3_host_climate_solver (test_tier3_cross_feature.TestTier3CrossFeature.test_t3_cf3_host_climate_solver)
Integrates host advantage, climate penalty, and the solver. ... ok
test_t3_cf4_backtest_pipeline_integration (test_tier3_cross_feature.TestTier3CrossFeature.test_t3_cf4_backtest_pipeline_integration)
Executes the complete pipeline from parsing metadata, running models, applying factors, solving, and comparing. ... ok
test_t4_rw1_mexico_city_azteca (test_tier4_real_world.TestTier4RealWorld.test_t4_rw1_mexico_city_azteca)
Simulates Mexico vs. Germany at Estadio Azteca (2240m altitude). ... ok
test_t4_rw2_miami_heat_humidity (test_tier4_real_world.TestTier4RealWorld.test_t4_rw2_miami_heat_humidity)
Simulates Ecuador vs. England in Miami in July (36°C, 85% humidity). ... ok
test_t4_rw3_canada_vancouver_travel (test_tier4_real_world.TestTier4RealWorld.test_t4_rw3_canada_vancouver_travel)
Simulates Canada vs. Japan in Vancouver. ... ok
test_t4_rw4_france_nb_blowout (test_tier4_real_world.TestTier4RealWorld.test_t4_rw4_france_nb_blowout)
Simulates France vs. Saudi Arabia using the Negative Binomial model to evaluate blowouts. ... ok
test_t4_rw5_italy_uruguay_draw (test_tier4_real_world.TestTier4RealWorld.test_t4_rw5_italy_uruguay_draw)
Simulates defensive Italy (lambda = 1.0) vs. Uruguay (lambda = 1.0) with Dixon-Coles draw inflation. ... ok

----------------------------------------------------------------------
Ran 74 tests in 0.258s

OK

==================================================
FIFA World Cup 2026 E2E Test Suite Summary
==================================================
Total Tests Run: 74
Passes:          74
Skips:           0
Failures:        0
Errors:          0
==================================================
RESULT: SUCCESS
```

## 2. Backtest Output

Command: `python3 backtest.py`

```stdout
Using default embedded fallback matches (6 matches).

============================================================
BACKTEST COMPARISON REPORT
============================================================
Total Matches:          6
Baseline Total Points:  8.0
Optimized Total Points: 11.0
Baseline Avg Points:    1.333
Optimized Avg Points:   1.833
Delta Total Points:     3.0
Delta Avg Points:       0.500
============================================================
Assertion passed: Optimized model achieved higher simulated Kicktipp points.
```
