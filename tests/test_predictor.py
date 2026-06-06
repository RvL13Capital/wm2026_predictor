import unittest
import math
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

class TestPredictor(unittest.TestCase):
    
    def test_poisson_probability(self):
        # Base case
        self.assertAlmostEqual(poisson_probability(0, 0.0), 1.0)
        self.assertAlmostEqual(poisson_probability(1, 0.0), 0.0)
        
        # Standard case: lambda = 2.0, k = 3
        # P(3) = 2^3 * e^-2 / 6 = 8 * 0.135335 / 6 = 0.180447
        expected = (2.0**3 * math.exp(-2.0)) / 6.0
        self.assertAlmostEqual(poisson_probability(3, 2.0), expected)
        
    def test_negative_binomial_probability(self):
        # Fallback to Poisson when alpha <= 1e-6
        self.assertAlmostEqual(negative_binomial_probability(2, 1.5, 1e-7), poisson_probability(2, 1.5))
        
        # Standard negative binomial check
        # mu = 2.0, alpha = 0.5
        # r = 1/alpha = 2.0
        # p = 1/(1 + alpha*mu) = 1/2 = 0.5
        # P(k=1) = gamma(1+2)/(gamma(2)*gamma(2)) * (0.5)^1 * (0.5)^2 = 2 * 0.5 * 0.25 = 0.25
        self.assertAlmostEqual(negative_binomial_probability(1, 2.0, 0.5), 0.25)
        
    def test_sum_to_one_poisson(self):
        config = MatchModelConfig(
            dist_type=ModelDistribution.POISSON,
            mu_a=1.5,
            mu_b=1.2,
            rho=-0.05,
            max_goals=12,
            max_tip=5
        )
        grid = generate_joint_grid(config)
        total_prob = sum(sum(grid[x].values()) for x in grid)
        self.assertAlmostEqual(total_prob, 1.0)
        
    def test_sum_to_one_negative_binomial(self):
        config = MatchModelConfig(
            dist_type=ModelDistribution.NEGATIVE_BINOMIAL,
            mu_a=1.5,
            mu_b=1.2,
            alpha_a=0.3,
            alpha_b=0.2,
            rho=-0.05,
            max_goals=12,
            max_tip=5
        )
        grid = generate_joint_grid(config)
        total_prob = sum(sum(grid[x].values()) for x in grid)
        self.assertAlmostEqual(total_prob, 1.0)
        
    def test_altitude_factor(self):
        # Low altitude
        self.assertEqual(calculate_altitude_factor(500, 0), 1.0)
        
        # Guadalajara (1560m)
        # Unacclimated (0 days)
        # h = 0.56
        # base_loss = 0.08 * 0.56 + 0.015 * 0.56^2 = 0.0448 + 0.004704 = 0.049504
        # factor = 1.0 - 0.049504 = 0.950496
        self.assertAlmostEqual(calculate_altitude_factor(1560, 0), 0.950496, places=5)
        
        # Guadalajara (1560m), Acclimated (7 days)
        # remaining_loss = 0.049504 * e^-1 = 0.018211
        # factor = 1 - 0.018211 = 0.981789
        self.assertAlmostEqual(calculate_altitude_factor(1560, 7), 0.981789, places=5)
        
        # Mexico City (2240m)
        # Unacclimated (0 days)
        # h = 1.24
        # base_loss = 0.08 * 1.24 + 0.015 * 1.24^2 = 0.0992 + 0.023064 = 0.122264
        # factor = 1 - 0.122264 = 0.877736
        self.assertAlmostEqual(calculate_altitude_factor(2240, 0), 0.877736, places=5)
        
        # Mexico City (2240m), Acclimated (7 days)
        # factor = 1 - 0.122264 * e^-1 = 0.954933
        self.assertAlmostEqual(calculate_altitude_factor(2240, 7), 0.955022, places=5)
        
        # Mexico City (2240m), Fully Acclimated (14 days)
        # factor = 1 - 0.122264 * e^-2 = 0.983455
        self.assertAlmostEqual(calculate_altitude_factor(2240, 14), 0.983453, places=5)

    def test_thermal_factor(self):
        # Mild condition T=20C, RH=50%
        # WBGT is approx 19.87 <= 20.0
        self.assertEqual(calculate_thermal_factor(20.0, 50.0, 0), 1.0)
        
        # Hot and Humid T=32C, RH=70%
        wbgt = calculate_wbgt(32.0, 70.0)
        self.assertAlmostEqual(wbgt, 35.176, places=1)
        
        # Unacclimated (0 days)
        f_therm_unaccl = calculate_thermal_factor(32.0, 70.0, 0)
        self.assertAlmostEqual(f_therm_unaccl, 1.0 - 0.015 * (wbgt - 20.0), places=5)
        
        # Acclimated (5 days)
        f_therm_accl = calculate_thermal_factor(32.0, 70.0, 5)
        self.assertAlmostEqual(f_therm_accl, 1.0 - 0.015 * (wbgt - 20.0) * math.exp(-1.0), places=5)

    def test_travel_penalty(self):
        # Baseline: rest = 5, dist = 0, tz = 0, dir = None
        self.assertEqual(calculate_travel_penalty(5.0, 0, 0, "None"), 0.0)
        
        # Fatigue/Travel Scenario B: rest = 3, dist = 3000, tz = 6, dir = East
        # p_rest = 0.03 * (5 - 3)^1.5 = 0.03 * 2.8284 = 0.08485
        # p_dist = 0.05 * (1 - e^-3.0) * e^-0.90 = 0.05 * 0.9502 * 0.4066 = 0.01932
        # p_tz = 0.02 * (6 * 1.5 - 3) = 0.02 * 6 = 0.12
        # total = 0.08485 + 0.01932 + 0.12 = 0.22417
        p = calculate_travel_penalty(3.0, 3000.0, 6, "East")
        self.assertAlmostEqual(p, 0.22417, places=4)

    def test_host_and_fan_adjustments(self):
        # Scenario 2 from explorer analysis
        # Team A (Home, 80% fans): status = True Home, fans = 0.80, travel_penalty = 0.0
        # Team B (Away, 10% fans): status = Neutral, fans = 0.10, travel_penalty = 0.22417
        delta_att_A, delta_def_A = calculate_context_adjustments(
            status="True Home",
            opponent_status="Neutral",
            fan_support_pct=0.80,
            opponent_fan_support_pct=0.10,
            travel_penalty=0.0,
            opponent_travel_penalty=0.22417
        )
        
        # Team A:
        # delta_att_travel = 0
        # delta_att_host = 0.08
        # delta_att_fan = 0.05 * (0.80 - 0.10) = 0.035
        # total_att = 0.115
        self.assertAlmostEqual(delta_att_A, 0.115)
        
        # delta_def_travel = 0
        # delta_def_host = -0.06
        # delta_def_fan = -0.04 * (0.80 - 0.10) = -0.028
        # total_def = -0.088
        self.assertAlmostEqual(delta_def_A, -0.088)

    def test_get_adjusted_lambdas(self):
        # Setup baseline scenario
        teamA_context = {
            "elevation": 0.0,
            "temp": 15.0,
            "humidity": 50.0,
            "accl_days": 0.0,
            "heat_accl_days": 0.0,
            "rest_days": 5.0,
            "travel_miles": 0.0,
            "tz_crossed": 0,
            "direction": "None",
            "status": "True Home",
            "fan_support_pct": 0.80
        }
        
        teamB_context = {
            "elevation": 0.0,
            "temp": 15.0,
            "humidity": 50.0,
            "accl_days": 0.0,
            "heat_accl_days": 0.0,
            "rest_days": 3.0,
            "travel_miles": 3000.0,
            "tz_crossed": 6,
            "direction": "East",
            "status": "Neutral",
            "fan_support_pct": 0.10
        }
        
        lambda_A, lambda_B = get_adjusted_lambdas(1.5, 1.5, teamA_context, teamB_context)
        self.assertAlmostEqual(lambda_A, 1.5 * math.exp(0.115 + (0.22417 * 0.3 + 0.028)), places=3)
        self.assertAlmostEqual(lambda_B, 1.5 * math.exp((-0.7 * 0.22417 - 0.035) - 0.088), places=3)

    def test_negative_binomial_stability_small_mu(self):
        # With mu=1e-17 and alpha=1.0, alpha * mu = 1e-17 < 1e-15, should fallback to Poisson.
        prob = negative_binomial_probability(0, 1e-17, 1.0)
        self.assertAlmostEqual(prob, poisson_probability(0, 1e-17), places=7)
        self.assertAlmostEqual(prob, 1.0, places=7)

    def test_none_type_sanitization_contexts(self):
        # Create contexts mapping values to None
        teamA_context = {
            "elevation": None,
            "temp": None,
            "humidity": None,
            "accl_days": None,
            "heat_accl_days": None,
            "rest_days": None,
            "travel_miles": None,
            "tz_crossed": None,
            "direction": None,
            "status": None,
            "fan_support_pct": None
        }
        teamB_context = {
            "elevation": None,
            "temp": None,
            "humidity": None,
            "accl_days": None,
            "heat_accl_days": None,
            "rest_days": None,
            "travel_miles": None,
            "tz_crossed": None,
            "direction": None,
            "status": None,
            "fan_support_pct": None
        }
        # This call should run without raising any TypeError due to NoneType sanitization
        lambda_A, lambda_B = get_adjusted_lambdas(1.5, 1.5, teamA_context, teamB_context)
        self.assertGreater(lambda_A, 0.0)
        self.assertGreater(lambda_B, 0.0)

    def test_dixon_coles_normalization_fallback_extreme_lambda(self):
        config = MatchModelConfig(
            dist_type=ModelDistribution.POISSON,
            mu_a=800.0,
            mu_b=800.0,
            rho=0.0,
            max_goals=12,
            max_tip=5
        )
        # Under mu=800, Poisson prob for k <= 12 is extremely small and underflows/sums to 0.0.
        # This should trigger the fallback and not raise division by zero.
        grid = generate_joint_grid(config)
        total_prob = sum(sum(grid[x].values()) for x in grid)
        self.assertAlmostEqual(total_prob, 1.0)
        self.assertEqual(grid[12][12], 1.0)

    def test_negative_travel_miles_penalty(self):
        # Inputting negative travel miles, rest days, or tz_crossed should be sanitized to 0.0/0
        penalty_neg = calculate_travel_penalty(
            rest_days=-2.0,
            travel_miles=-500.0,
            tz_crossed=-3,
            direction="East"
        )
        penalty_zero = calculate_travel_penalty(
            rest_days=0.0,
            travel_miles=0.0,
            tz_crossed=0,
            direction="East"
        )
        self.assertEqual(penalty_neg, penalty_zero)

if __name__ == "__main__":
    unittest.main()
