import unittest
import os
import sys

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import predictor

def is_negative_binomial_implemented():
    return hasattr(predictor, 'negative_binomial_prob') or hasattr(predictor, 'negative_binomial')

def is_contextual_factors_implemented():
    return hasattr(predictor, 'apply_contextual_factors') or hasattr(predictor, 'altitude_penalty') or hasattr(predictor, 'get_adjusted_lambdas')

def is_solver_implemented():
    return hasattr(predictor, 'solve_optimal_tip') and hasattr(predictor, 'get_points')

def is_backtester_implemented():
    try:
        import backtest
        return True
    except ImportError:
        return False

class TestTier1FeatureCoverage(unittest.TestCase):

    # --- Feature 1: Advanced Probability Engine (F1) ---

    def test_t1_f1_poisson_grid_sum(self):
        """Validates that a standard generated Poisson probability grid sums to exactly 1.0 (within 1e-6 tolerance) after normalization."""
        _, _, outcomes = predictor.solve_optimal_tip(1.5, 1.2)
        # Sum of home win, draw, and away win probabilities should equal 1.0
        self.assertAlmostEqual(sum(outcomes), 1.0, delta=1e-6)

    def test_t1_f1_dixon_coles_adjustment(self):
        """Verifies that applying a negative Dixon-Coles parameter (rho = -0.1) inflates low-scoring draw probabilities (0-0, 1-1) compared to rho = 0.1."""
        _, scores_neg, _ = predictor.solve_optimal_tip(1.0, 1.0, rho=-0.1)
        _, scores_pos, _ = predictor.solve_optimal_tip(1.0, 1.0, rho=0.1)
        
        p_neg_00 = next(p for score, p in scores_neg if score == (0,0))
        p_neg_11 = next(p for score, p in scores_neg if score == (1,1))
        
        p_pos_00 = next(p for score, p in scores_pos if score == (0,0))
        p_pos_11 = next(p for score, p in scores_pos if score == (1,1))
        
        self.assertGreater(p_neg_00, p_pos_00)
        self.assertGreater(p_neg_11, p_pos_11)

    def test_t1_f1_neg_binomial_overdispersion(self):
        """Verifies that the Negative Binomial distribution models overdispersion such that variance exceeds the mean when alpha > 0."""
        if not is_negative_binomial_implemented():
            self.skipTest("Negative Binomial distribution not implemented yet")
        
        mu = 3.0
        alpha = 0.5
        probs = [predictor.negative_binomial_prob(k, mu, alpha) for k in range(50)]
        sum_p = sum(probs)
        self.assertAlmostEqual(sum_p, 1.0, delta=1e-3)
        
        mean = sum(k * p for k, p in enumerate(probs))
        variance = sum((k - mean)**2 * p for k, p in enumerate(probs))
        
        self.assertAlmostEqual(mean, mu, delta=1e-2)
        self.assertGreater(variance, mean)

    def test_t1_f1_prob_bounds(self):
        """Verifies that all individual cells in the probability grid are bounded within [0.0, 1.0]."""
        _, scores, outcomes = predictor.solve_optimal_tip(1.5, 1.2)
        for score, p in scores:
            self.assertTrue(0.0 <= p <= 1.0, f"Probability {p} is out of bounds for score {score}")
        for p in outcomes:
            self.assertTrue(0.0 <= p <= 1.0, f"Outcome probability {p} is out of bounds")

    def test_t1_f1_grid_size_scaling(self):
        """Evaluates the grid scaling behavior when changing max_goals (e.g. from 5 to 15)."""
        for max_goals in [5, 10, 15]:
            _, _, outcomes = predictor.solve_optimal_tip(1.5, 1.2, max_goals=max_goals)
            self.assertAlmostEqual(sum(outcomes), 1.0, delta=1e-5)

    # --- Feature 2: Contextual WM-Specific Factors (F2) ---

    def test_t1_f2_altitude_degradation(self):
        """Verifies that stadium altitude above sea level degrades the team strength of a non-acclimated team."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
        
        factor_sea_level = predictor.calculate_altitude_factor(0.0, 0.0)
        factor_high_altitude = predictor.calculate_altitude_factor(2000.0, 0.0)
        self.assertEqual(factor_sea_level, 1.0)
        self.assertLess(factor_high_altitude, 1.0)
        
        factor_acclimated = predictor.calculate_altitude_factor(2000.0, 7.0)
        self.assertGreater(factor_acclimated, factor_high_altitude)
        
        lambda_sea, _ = predictor.get_adjusted_lambdas(2.0, 2.0, {"elevation": 0.0, "accl_days": 0.0}, {"elevation": 0.0, "accl_days": 0.0})
        lambda_alt, _ = predictor.get_adjusted_lambdas(2.0, 2.0, {"elevation": 2000.0, "accl_days": 0.0}, {"elevation": 2000.0, "accl_days": 10.0})
        self.assertLess(lambda_alt, lambda_sea)

    def test_t1_f2_climate_humidity_penalty(self):
        """Verifies that high temperature and humidity degrade performance for both teams."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        factor_normal = predictor.calculate_thermal_factor(20.0, 40.0, 0.0)
        self.assertEqual(factor_normal, 1.0)
        
        factor_hot_humid = predictor.calculate_thermal_factor(35.0, 80.0, 0.0)
        self.assertLess(factor_hot_humid, 1.0)
        
        factor_acclimated = predictor.calculate_thermal_factor(35.0, 80.0, 10.0)
        self.assertGreater(factor_acclimated, factor_hot_humid)

    def test_t1_f2_travel_fatigue_penalty(self):
        """Verifies that travel mileage (distance) and timezone transitions reduce team strength."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
        
        penalty_none = predictor.calculate_travel_penalty(5.0, 0.0, 0, "None")
        self.assertEqual(penalty_none, 0.0)
        
        penalty_travel = predictor.calculate_travel_penalty(3.0, 3000.0, 0, "None")
        self.assertGreater(penalty_travel, 0.0)
        
        penalty_tz_east = predictor.calculate_travel_penalty(3.0, 3000.0, 6, "East")
        penalty_tz_west = predictor.calculate_travel_penalty(3.0, 3000.0, 6, "West")
        self.assertGreater(penalty_tz_east, penalty_tz_west)

    def test_t1_f2_host_advantage_boost(self):
        """Verifies that host countries receive a positive boost to their base strength."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        neutral_context = {"status": "Neutral", "fan_support_pct": 0.5, "rest_days": 5.0, "travel_miles": 0.0, "tz_crossed": 0}
        lambda_A_neut, lambda_B_neut = predictor.get_adjusted_lambdas(1.5, 1.5, neutral_context, neutral_context)
        self.assertAlmostEqual(lambda_A_neut, 1.5)
        self.assertAlmostEqual(lambda_B_neut, 1.5)
        
        home_context = {"status": "True Home", "fan_support_pct": 0.5, "rest_days": 5.0, "travel_miles": 0.0, "tz_crossed": 0}
        lambda_A_home, lambda_B_away = predictor.get_adjusted_lambdas(1.5, 1.5, home_context, neutral_context)
        self.assertGreater(lambda_A_home, 1.5)
        self.assertLess(lambda_B_away, 1.5)

    def test_t1_f2_multi_factor_compounding(self):
        """Ensures that applying all four factors simultaneously scales lambda correctly without causing invalid negative values."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        context_A = {
            "status": "True Home",
            "fan_support_pct": 0.8,
            "elevation": 3000.0,
            "temp": 38.0,
            "humidity": 90.0,
            "accl_days": 1.0,
            "heat_accl_days": 1.0,
            "rest_days": 2.0,
            "travel_miles": 4000.0,
            "tz_crossed": 8,
            "direction": "East"
        }
        
        context_B = {
            "status": "Neutral",
            "fan_support_pct": 0.2,
            "elevation": 3000.0,
            "temp": 38.0,
            "humidity": 90.0,
            "accl_days": 14.0,
            "heat_accl_days": 14.0,
            "rest_days": 6.0,
            "travel_miles": 0.0,
            "tz_crossed": 0
        }
        
        lambda_A_adj, lambda_B_adj = predictor.get_adjusted_lambdas(2.0, 2.0, context_A, context_B)
        self.assertGreater(lambda_A_adj, 0.0)
        self.assertGreater(lambda_B_adj, 0.0)

    # --- Feature 3: Kicktipp Solver (EV Maximization) (F3) ---

    def test_t1_f3_exact_score_points(self):
        """Verifies that the point calculator returns exactly 4 points for an exact match."""
        self.assertEqual(predictor.get_points(2, 1, 2, 1), 4)

    def test_t1_f3_difference_points(self):
        """Verifies that matching the goal difference and tendency returns exactly 3 points."""
        self.assertEqual(predictor.get_points(2, 1, 3, 2), 3)

    def test_t1_f3_tendency_points(self):
        """Verifies that matching the tendency only returns exactly 2 points."""
        self.assertEqual(predictor.get_points(2, 0, 3, 2), 2)

    def test_t1_f3_draw_tendency_only(self):
        """Verifies that if you tip a draw (e.g. 1-1) and the result is a different draw (e.g. 2-2), you get 3 points (correct difference of 0) and not 2 points."""
        self.assertEqual(predictor.get_points(1, 1, 2, 2), 3)

    def test_t1_f3_ev_maximization(self):
        """Verifies that the solver returns the tip that maximizes the mathematically expected value."""
        tips, _, _ = predictor.solve_optimal_tip(1.5, 1.2)
        evs = [ev for tip, ev in tips]
        # Verify tips are sorted descending by EV, meaning index 0 has maximum EV
        self.assertEqual(evs, sorted(evs, reverse=True))

    # --- Feature 4: Backtesting & Validation Suite (F4) ---

    def test_t1_f4_data_loader(self):
        """Verifies that the backtesting suite successfully parses a CSV file containing historical match results."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_mock_matches.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            f.write("Germany,Mexico,1,2,2240,25,50\n")
            f.write("USA,England,1,1,0,20,40\n")
            
        try:
            data = backtest.load_match_data(csv_path)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]['team_a'], "Germany")
            self.assertEqual(data[0]['goals_b'], 2)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_t1_f4_baseline_runner(self):
        """Verifies that the baseline model can run over all games in the backtester without error."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_mock_matches.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            f.write("Germany,Mexico,1,2,2240,25,50\n")
            
        try:
            data = backtest.load_match_data(csv_path)
            results = backtest.run_backtest(model_type="baseline", data=data)
            self.assertIn("total_points", results)
            self.assertIn("predictions", results)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_t1_f4_optimized_runner(self):
        """Verifies that the optimized model executes over all backtest games."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_mock_matches.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            f.write("Germany,Mexico,1,2,2240,25,50\n")
            
        try:
            data = backtest.load_match_data(csv_path)
            results = backtest.run_backtest(model_type="optimized", data=data)
            self.assertIn("total_points", results)
            self.assertIn("predictions", results)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_t1_f4_summary_report(self):
        """Verifies that the final comparison report prints average points and total points."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_mock_matches.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            f.write("Germany,Mexico,1,2,2240,25,50\n")
            
        try:
            data = backtest.load_match_data(csv_path)
            results_base = backtest.run_backtest(model_type="baseline", data=data)
            results_opt = backtest.run_backtest(model_type="optimized", data=data)
            report = backtest.generate_summary_report(results_base, results_opt)
            self.assertIn("baseline_total_points", report)
            self.assertIn("optimized_total_points", report)
            self.assertIn("baseline_avg_points", report)
            self.assertIn("optimized_avg_points", report)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_t1_f4_points_accumulation_integrity(self):
        """Checks that total points in the backtest report match the sum of individual game scores."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_mock_matches.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            f.write("Germany,Mexico,1,2,2240,25,50\n")
            f.write("USA,England,1,1,0,20,40\n")
            
        try:
            data = backtest.load_match_data(csv_path)
            results = backtest.run_backtest(model_type="optimized", data=data)
            sum_points = sum(pred["points"] for pred in results["predictions"])
            self.assertEqual(results["total_points"], sum_points)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

if __name__ == '__main__':
    unittest.main()
