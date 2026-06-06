import unittest
import os
import sys
import math

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

class TestTier2BoundaryCorner(unittest.TestCase):

    # --- Feature 1: Advanced Probability Engine (F1) ---

    def test_t2_f1_zero_lambda(self):
        """Tests the engine with a team lambda of 0.0."""
        # lambda of 0.0 should not raise division by zero
        tips, scores, outcomes = predictor.solve_optimal_tip(0.0, 0.0)
        # With 0.0 lambda, probability of 0-0 is 1.0, meaning draw probability is 1.0
        self.assertAlmostEqual(outcomes[1], 1.0, delta=1e-5)
        # Top score should be 0:0 with probability 1.0
        self.assertEqual(scores[0][0], (0, 0))
        self.assertAlmostEqual(scores[0][1], 1.0, delta=1e-5)

    def test_t2_f1_extreme_high_lambda(self):
        """Evaluates calculations at extremely high lambdas (e.g., lambda = 15.0)."""
        tips, scores, outcomes = predictor.solve_optimal_tip(15.0, 15.0)
        self.assertAlmostEqual(sum(outcomes), 1.0, delta=1e-5)

    def test_t2_f1_extreme_dixon_coles_rho(self):
        """Evaluates extreme rho values (e.g., +1.5, -1.5) which could result in negative adjustment factors."""
        tips, scores, outcomes = predictor.solve_optimal_tip(1.0, 1.0, rho=1.5)
        self.assertAlmostEqual(sum(outcomes), 1.0, delta=1e-5)
        
        tips2, scores2, outcomes2 = predictor.solve_optimal_tip(1.0, 1.0, rho=-1.5)
        self.assertAlmostEqual(sum(outcomes2), 1.0, delta=1e-5)

    def test_t2_f1_minimal_grid_size(self):
        """Evaluates probability grid with max_goals = 0."""
        tips, scores, outcomes = predictor.solve_optimal_tip(1.0, 1.0, max_goals=0)
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0][0], (0, 0))
        self.assertAlmostEqual(scores[0][1], 1.0, delta=1e-5)

    def test_t2_f1_negative_binomial_alpha_limit(self):
        """Verifies behavior when Negative Binomial alpha -> 0."""
        if not is_negative_binomial_implemented():
            self.skipTest("Negative Binomial distribution not implemented yet")
        
        mu = 2.5
        p_nb_fallback = predictor.negative_binomial_prob(2, mu, 1e-7)
        p_poisson = predictor.poisson_prob(2, mu)
        self.assertAlmostEqual(p_nb_fallback, p_poisson, places=7)
        
        p_nb_small = predictor.negative_binomial_prob(2, mu, 1e-5)
        self.assertAlmostEqual(p_nb_small, p_poisson, delta=1e-4)

    # --- Feature 2: Contextual WM-Specific Factors (F2) ---

    def test_t2_f2_extreme_elevation_cap(self):
        """Simulates matches at extreme elevations (e.g., 4000m above sea level)."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        factor_4000 = predictor.calculate_altitude_factor(4000.0, 0.0)
        self.assertTrue(0.5 <= factor_4000 < 1.0)
        
        factor_extreme = predictor.calculate_altitude_factor(20000.0, 0.0)
        self.assertEqual(factor_extreme, 0.5)

    def test_t2_f2_extreme_wet_bulb(self):
        """Simulates a match under extreme heat index (e.g., 45°C, 95% humidity)."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        wbgt_extreme = predictor.calculate_wbgt(45.0, 95.0)
        self.assertGreater(wbgt_extreme, 35.0)
        
        factor_extreme = predictor.calculate_thermal_factor(45.0, 95.0, 0.0)
        self.assertEqual(factor_extreme, 0.5)

    def test_t2_f2_zero_travel(self):
        """Simulates a match with 0 km travel and same timezone."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        penalty = predictor.calculate_travel_penalty(5.0, 0.0, 0, "None")
        self.assertEqual(penalty, 0.0)

    def test_t2_f2_dual_host_neutralization(self):
        """Tests host advantages when two hosts play each other or a host plays at neutral ground."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        context_A = {"status": "Co-Host", "fan_support_pct": 0.5, "rest_days": 5.0, "travel_miles": 0.0, "tz_crossed": 0}
        context_B = {"status": "Co-Host", "fan_support_pct": 0.5, "rest_days": 5.0, "travel_miles": 0.0, "tz_crossed": 0}
        
        lambda_A, lambda_B = predictor.get_adjusted_lambdas(1.5, 1.5, context_A, context_B)
        self.assertEqual(lambda_A, lambda_B)
        self.assertAlmostEqual(lambda_A, 1.5 * math.exp(0.03 - 0.02))

    def test_t2_f2_rest_days_extremes(self):
        """Evaluates travel fatigue with 0 rest days versus 30 rest days."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        penalty_0_days = predictor.calculate_travel_penalty(0.0, 1000.0, 5, "East")
        penalty_30_days = predictor.calculate_travel_penalty(30.0, 1000.0, 5, "East")
        
        self.assertEqual(penalty_0_days, 0.30)
        self.assertAlmostEqual(penalty_30_days, 0.0, delta=1e-5)

    # --- Feature 3: Kicktipp Solver (EV Maximization) (F3) ---

    def test_t2_f3_flat_probability_grid(self):
        """Tests the solver with a flat probability distribution (symmetric ties in expected value)."""
        tips, _, _ = predictor.solve_optimal_tip(1.0, 1.0, rho=0.0)
        ev_dict = dict(tips)
        # Symmetry check: (1,0) and (0,1) should have identical expected values
        self.assertAlmostEqual(ev_dict[(1,0)], ev_dict[(0,1)], delta=1e-6)

    def test_t2_f3_extreme_tip_limit(self):
        """Tests the solver with max_tip = 0."""
        tips, _, _ = predictor.solve_optimal_tip(1.5, 1.2, max_tip=0)
        self.assertEqual(len(tips), 1)
        self.assertEqual(tips[0][0], (0, 0))

    def test_t2_f3_certainty_grid(self):
        """Sets probability of a specific score to 1.0 by using lambda=0.0 (resulting in 0-0 being certain)."""
        tips, _, _ = predictor.solve_optimal_tip(0.0, 0.0, max_tip=3)
        self.assertEqual(tips[0][0], (0, 0))
        self.assertAlmostEqual(tips[0][1], 4.0, delta=1e-5)

    def test_t2_f3_skewed_win_distribution(self):
        """Tests a highly skewed win distribution. The optimal tip must maximize expected points."""
        tips, scores, _ = predictor.solve_optimal_tip(2.5, 0.8)
        optimal_tip = tips[0][0]
        optimal_ev = tips[0][1]
        
        most_probable_score = scores[0][0]
        ev_dict = dict(tips)
        most_probable_ev = ev_dict.get(most_probable_score, 0.0)
        
        self.assertGreaterEqual(optimal_ev, most_probable_ev)

    def test_t2_f3_high_score_tipping_limit(self):
        """Evaluates tipping options when max_tip is much larger than max_goals."""
        tips, _, _ = predictor.solve_optimal_tip(1.5, 1.2, max_goals=5, max_tip=10)
        self.assertTrue(len(tips) > 0)

    # --- Feature 4: Backtesting & Validation Suite (F4) ---

    def test_t2_f4_empty_dataset(self):
        """Runs the backtester with an empty match CSV file."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_empty.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            
        try:
            data = backtest.load_match_data(csv_path)
            self.assertEqual(len(data), 0)
        except Exception as e:
            self.assertTrue(isinstance(e, (ValueError, RuntimeError, KeyError)))
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_t2_f4_malformed_columns(self):
        """Runs backtester with missing score columns or malformed values."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_malformed.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a\n")
            f.write("Germany,Mexico,not_a_number\n")
            
        try:
            with self.assertRaises((ValueError, KeyError, TypeError)):
                backtest.load_match_data(csv_path)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_t2_f4_missing_stadium_metadata(self):
        """Simulates a match in an unknown stadium."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_missing_stadium.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            f.write("Germany,Mexico,1,2,,,\n")
            
        try:
            data = backtest.load_match_data(csv_path)
            self.assertEqual(data[0].get("elevation", 0.0), 0.0)
            self.assertEqual(data[0].get("temp", 20.0), 20.0)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_t2_f4_underperforming_model_reporting(self):
        """Asserts that if the optimized model performs worse than the baseline, the delta is reported as negative."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        results_base = {"total_points": 10.0, "predictions": []}
        results_opt = {"total_points": 8.0, "predictions": []}
        
        report = backtest.generate_summary_report(results_base, results_opt)
        self.assertLess(report["delta_total_points"], 0.0)

    def test_t2_f4_high_volume_stress(self):
        """Evaluates backtester performance with a large mock historical dataset (e.g., 1000 games)."""
        if not is_backtester_implemented():
            self.skipTest("Backtesting suite (F4) not implemented yet")
            
        import backtest
        csv_path = "temp_stress.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            for i in range(1000):
                f.write(f"Team{i},Team{i+1},1,1,100,20,50\n")
                
        try:
            data = backtest.load_match_data(csv_path)
            self.assertEqual(len(data), 1000)
            results = backtest.run_backtest(model_type="baseline", data=data)
            self.assertEqual(len(results["predictions"]), 1000)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

if __name__ == '__main__':
    unittest.main()
