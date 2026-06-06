#!/usr/bin/env python3
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from predictor import (
    ModelDistribution,
    MatchModelConfig,
    poisson_probability,
    negative_binomial_probability,
    calculate_altitude_factor,
    calculate_wbgt,
    calculate_thermal_factor,
    calculate_travel_penalty,
    calculate_context_adjustments,
    get_adjusted_lambdas,
    get_dixon_coles_adjustment,
    generate_joint_grid,
    solve_optimal_tip
)

def run_custom_checks():
    print("==================================================")
    print("RUNNING CUSTOM MATHEMATICAL & BOUNDARY CHECKS")
    print("==================================================")
    
    # Check 1: Negative Binomial under extreme parameters
    print("\n--- Check 1: Negative Binomial Extreme Parameters ---")
    try:
        # Large alpha
        p_large_alpha = negative_binomial_probability(2, 1.5, 1e10)
        print(f"Negative Binomial (alpha=1e10): P(2) = {p_large_alpha}")
        
        # Extremely large alpha causing potential overflow/nan
        # alpha = 1e300, mu = 2.0. If alpha*mu overflows or p becomes 0, check behavior.
        try:
            p_huge_alpha = negative_binomial_probability(2, 2.0, 1e300)
            print(f"Negative Binomial (alpha=1e300): P(2) = {p_huge_alpha}")
        except Exception as e:
            print(f"Negative Binomial (alpha=1e300) failed with: {type(e).__name__}: {e}")
            
        # Large mu
        p_large_mu = negative_binomial_probability(2, 1000.0, 0.5)
        print(f"Negative Binomial (mu=1000.0, alpha=0.5): P(2) = {p_large_mu}")
        
        # Zero and negative alpha/mu
        p_zero_mu = negative_binomial_probability(2, 0.0, 0.5)
        p_neg_mu = negative_binomial_probability(2, -1.0, 0.5)
        p_neg_alpha = negative_binomial_probability(2, 1.5, -0.5)
        print(f"NB Zero mu: P(2) = {p_zero_mu}")
        print(f"NB Neg mu: P(2) = {p_neg_mu}")
        print(f"NB Neg alpha: P(2) = {p_neg_alpha}")
        
    except Exception as e:
        print(f"Check 1 failed with error: {e}")

    # Check 2: Dixon-Coles marginal preservation and normalization
    print("\n--- Check 2: Dixon-Coles Marginals & Grid Normalization ---")
    config = MatchModelConfig(
        dist_type=ModelDistribution.POISSON,
        mu_a=1.5,
        mu_b=1.2,
        rho=-0.1,
        max_goals=12
    )
    grid = generate_joint_grid(config)
    sum_prob = sum(sum(grid[x].values()) for x in grid)
    print(f"Grid sum (rho=-0.1, max_goals=12): {sum_prob}")
    
    # Calculate marginal expectations of the grid vs. target mu
    mu_a_computed = sum(x * grid[x][y] for x in grid for y in grid[x])
    mu_b_computed = sum(y * grid[x][y] for x in grid for y in grid[x])
    print(f"Target mu_a: {config.mu_a}, Grid computed mu_a: {mu_a_computed:.6f} (diff: {abs(mu_a_computed - config.mu_a):.6f})")
    print(f"Target mu_b: {config.mu_b}, Grid computed mu_b: {mu_b_computed:.6f} (diff: {abs(mu_b_computed - config.mu_b):.6f})")

    # Dixon-Coles with extreme rho
    config_ext_rho = MatchModelConfig(
        dist_type=ModelDistribution.POISSON,
        mu_a=1.5,
        mu_b=1.2,
        rho=-10.0,
        max_goals=12
    )
    grid_ext = generate_joint_grid(config_ext_rho)
    sum_prob_ext = sum(sum(grid_ext[x].values()) for x in grid_ext)
    print(f"Grid sum with extreme rho=-10.0: {sum_prob_ext}")
    
    # Check 3: Contextual adjustments under extreme inputs
    print("\n--- Check 3: Contextual Adjustments Extreme Inputs ---")
    # Temperature slightly below -237.3 (denominator boundary)
    for temp in [-237.3, -237.3000000000001, -237.2999999999999]:
        try:
            wbgt = calculate_wbgt(temp, 50.0)
            print(f"WBGT at Temp={temp}C: {wbgt}")
        except Exception as e:
            print(f"WBGT at Temp={temp}C failed with: {type(e).__name__}: {e}")
            
    # Extreme temperature/humidity
    try:
        f_therm = calculate_thermal_factor(100.0, 100.0, 0.0)
        print(f"Thermal factor at 100C, 100% hum: {f_therm}")
    except Exception as e:
        print(f"Thermal factor extreme failed with: {type(e).__name__}: {e}")
        
    # Extremely negative rest days or travel miles
    try:
        p_travel = calculate_travel_penalty(rest_days=-1e5, travel_miles=0.0, tz_crossed=0)
        print(f"Travel penalty at -1e5 rest days: {p_travel}")
    except Exception as e:
        print(f"Travel penalty at -1e5 rest days failed with: {type(e).__name__}: {e}")
        
    try:
        p_travel_dist = calculate_travel_penalty(rest_days=5.0, travel_miles=-1e5, tz_crossed=0)
        print(f"Travel penalty at -1e5 travel miles: {p_travel_dist}")
    except Exception as e:
        print(f"Travel penalty at -1e5 travel miles failed with: {type(e).__name__}: {e}")

    # Check 4: Large Grid Sizes and Solver Performance
    print("\n--- Check 4: Large Grid Sizes & Solver ---")
    for size in [12, 20, 50, 100]:
        import time
        t0 = time.time()
        try:
            config = MatchModelConfig(
                dist_type=ModelDistribution.POISSON,
                mu_a=1.5,
                mu_b=1.2,
                max_goals=size,
                max_tip=6
            )
            tips, scores, outcomes = solve_optimal_tip(config)
            dt = time.time() - t0
            print(f"Grid size {size}x{size} solved in {dt:.4f}s. Top tip: {tips[0][0]} EV={tips[0][1]:.4f}")
        except Exception as e:
            print(f"Grid size {size} failed: {type(e).__name__}: {e}")

if __name__ == "__main__":
    run_custom_checks()
    
    print("\n==================================================")
    print("RUNNING ALL UNIT AND E2E/TIER TESTS")
    print("==================================================")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(os.path.dirname(__file__), 'tests'), pattern='test_*.py')
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)

