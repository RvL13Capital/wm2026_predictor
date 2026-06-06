#!/usr/bin/env python3
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
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

class StressTestHarness(unittest.TestCase):

    def test_poisson_extremes(self):
        print("\n--- Running Poisson Extremes Stress ---")
        # Extremely large lambda
        try:
            p = poisson_probability(5, 1e15)
            print(f"poisson_probability(5, 1e15) = {p}")
        except Exception as e:
            print(f"poisson_probability(5, 1e15) failed: {type(e).__name__}: {e}")

        # Infinite lambda
        try:
            p = poisson_probability(5, float('inf'))
            print(f"poisson_probability(5, inf) = {p}")
        except Exception as e:
            print(f"poisson_probability(5, inf) failed: {type(e).__name__}: {e}")

        # Nan lambda
        try:
            p = poisson_probability(5, float('nan'))
            print(f"poisson_probability(5, nan) = {p}")
        except Exception as e:
            print(f"poisson_probability(5, nan) failed: {type(e).__name__}: {e}")

        # Large k
        try:
            p = poisson_probability(1000000, 1.5)
            print(f"poisson_probability(1000000, 1.5) = {p}")
        except Exception as e:
            print(f"poisson_probability(1000000, 1.5) failed: {type(e).__name__}: {e}")

    def test_negative_binomial_extremes(self):
        print("\n--- Running Negative Binomial Extremes Stress ---")
        # Negative alpha (should fall back to Poisson because alpha <= 1e-6)
        try:
            p = negative_binomial_probability(2, 1.5, -2.5)
            print(f"negative_binomial_probability(2, 1.5, -2.5) = {p}")
        except Exception as e:
            print(f"negative_binomial_probability(2, 1.5, -2.5) failed: {type(e).__name__}: {e}")

        # Extremely large alpha (1e300)
        try:
            p = negative_binomial_probability(2, 1.5, 1e300)
            print(f"negative_binomial_probability(2, 1.5, 1e300) = {p}")
        except Exception as e:
            print(f"negative_binomial_probability(2, 1.5, 1e300) failed: {type(e).__name__}: {e}")

        # Infinite alpha
        try:
            p = negative_binomial_probability(2, 1.5, float('inf'))
            print(f"negative_binomial_probability(2, 1.5, inf) = {p}")
        except Exception as e:
            print(f"negative_binomial_probability(2, 1.5, inf) failed: {type(e).__name__}: {e}")

        # Nan alpha
        try:
            p = negative_binomial_probability(2, 1.5, float('nan'))
            print(f"negative_binomial_probability(2, 1.5, nan) = {p}")
        except Exception as e:
            print(f"negative_binomial_probability(2, 1.5, nan) failed: {type(e).__name__}: {e}")

        # Infinite mu
        try:
            p = negative_binomial_probability(2, float('inf'), 0.5)
            print(f"negative_binomial_probability(2, inf, 0.5) = {p}")
        except Exception as e:
            print(f"negative_binomial_probability(2, inf, 0.5) failed: {type(e).__name__}: {e}")

    def test_altitude_extremes(self):
        print("\n--- Running Altitude Extremes Stress ---")
        # Extreme negative acclimation days
        try:
            factor = calculate_altitude_factor(1500.0, -700.0)
            print(f"calculate_altitude_factor(1500, -700) = {factor}")
        except Exception as e:
            print(f"calculate_altitude_factor(1500, -700) failed: {type(e).__name__}: {e}")

        try:
            factor = calculate_altitude_factor(1500.0, -10000.0)
            print(f"calculate_altitude_factor(1500, -10000) = {factor}")
        except Exception as e:
            print(f"calculate_altitude_factor(1500, -10000) failed: {type(e).__name__}: {e}")

        # Infinite elevation
        try:
            factor = calculate_altitude_factor(float('inf'), 0.0)
            print(f"calculate_altitude_factor(inf, 0) = {factor}")
        except Exception as e:
            print(f"calculate_altitude_factor(inf, 0) failed: {type(e).__name__}: {e}")

    def test_thermal_extremes(self):
        print("\n--- Running Thermal Extremes Stress ---")
        # Absolute zero and below denom boundary
        for t in [-273.15, -237.3, -237.3000000000001, -238.0]:
            try:
                wbgt = calculate_wbgt(t, 50.0)
                factor = calculate_thermal_factor(t, 50.0, 0.0)
                print(f"calculate_thermal_factor({t}, 50, 0) = {factor} (wbgt={wbgt})")
            except Exception as e:
                print(f"calculate_thermal_factor({t}, 50, 0) failed: {type(e).__name__}: {e}")

        # Infinite temperature
        try:
            factor = calculate_thermal_factor(float('inf'), 50.0, 0.0)
            print(f"calculate_thermal_factor(inf, 50, 0) = {factor}")
        except Exception as e:
            print(f"calculate_thermal_factor(inf, 50, 0) failed: {type(e).__name__}: {e}")

        # Extreme negative heat acclimation days
        try:
            factor = calculate_thermal_factor(30.0, 50.0, -5000.0)
            print(f"calculate_thermal_factor(30, 50, -5000) = {factor}")
        except Exception as e:
            print(f"calculate_thermal_factor(30, 50, -5000) failed: {type(e).__name__}: {e}")

    def test_travel_extremes(self):
        print("\n--- Running Travel Extremes Stress ---")
        # Extreme negative inputs
        try:
            penalty = calculate_travel_penalty(rest_days=-1e6, travel_miles=-1e6, tz_crossed=-100)
            print(f"calculate_travel_penalty(-1e6, -1e6, -100) = {penalty}")
        except Exception as e:
            print(f"calculate_travel_penalty(-1e6, -1e6, -100) failed: {type(e).__name__}: {e}")

        # Infinite rest days
        try:
            penalty = calculate_travel_penalty(rest_days=float('inf'), travel_miles=1000.0, tz_crossed=5)
            print(f"calculate_travel_penalty(inf, 1000, 5) = {penalty}")
        except Exception as e:
            print(f"calculate_travel_penalty(inf, 1000, 5) failed: {type(e).__name__}: {e}")

        # Infinite miles
        try:
            penalty = calculate_travel_penalty(rest_days=5.0, travel_miles=float('inf'), tz_crossed=5)
            print(f"calculate_travel_penalty(5, inf, 5) = {penalty}")
        except Exception as e:
            print(f"calculate_travel_penalty(5, inf, 5) failed: {type(e).__name__}: {e}")

    def test_dixon_coles_extremes(self):
        print("\n--- Running Dixon-Coles Extremes Stress ---")
        # Extreme rho
        for rho in [-100.0, 100.0, float('inf'), float('nan')]:
            try:
                adj = get_dixon_coles_adjustment(0, 0, 1.5, 1.2, rho)
                print(f"get_dixon_coles_adjustment(0, 0, 1.5, 1.2, {rho}) = {adj}")
            except Exception as e:
                print(f"get_dixon_coles_adjustment(0, 0, 1.5, 1.2, {rho}) failed: {type(e).__name__}: {e}")

    def test_fan_support_extremes(self):
        print("\n--- Running Fan Support Extremes Stress ---")
        # Extremely large fan support percentage causing lambda adjustment overflow
        teamA_context = {"fan_support_pct": 1e5}
        teamB_context = {"fan_support_pct": 0.0}
        try:
            lambda_A, lambda_B = get_adjusted_lambdas(1.5, 1.5, teamA_context, teamB_context)
            print(f"get_adjusted_lambdas with extreme fans: {lambda_A}, {lambda_B}")
        except Exception as e:
            print(f"get_adjusted_lambdas with extreme fans failed: {type(e).__name__}: {e}")

    def test_pipeline_crash(self):
        print("\n--- Running Complete Pipeline Crash Stress ---")
        # Combining extreme inputs in solve_optimal_tip
        try:
            config = MatchModelConfig(
                dist_type=ModelDistribution.NEGATIVE_BINOMIAL,
                mu_a=1.5,
                mu_b=1.2,
                alpha_a=1e300,
                alpha_b=float('nan'),
                rho=float('inf'),
                max_goals=12
            )
            tips, scores, outcomes = solve_optimal_tip(config)
            print(f"solve_optimal_tip with extreme config completed. Top tip: {tips[0][0]} EV={tips[0][1]}")
        except Exception as e:
            print(f"solve_optimal_tip failed: {type(e).__name__}: {e}")

if __name__ == "__main__":
    unittest.main()
