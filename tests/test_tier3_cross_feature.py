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

class TestTier3CrossFeature(unittest.TestCase):

    def test_t3_cf1_elevation_draw_solver(self):
        """Integrates altitude adjustments, Dixon-Coles draw adjustments, and the solver."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        context_A = {"elevation": 3000.0, "accl_days": 0.0, "status": "Neutral", "fan_support_pct": 0.5}
        context_B = {"elevation": 3000.0, "accl_days": 10.0, "status": "Neutral", "fan_support_pct": 0.5}
        
        lambda_A_adj, lambda_B_adj = predictor.get_adjusted_lambdas(2.0, 2.0, context_A, context_B)
        
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=lambda_A_adj,
            mu_b=lambda_B_adj,
            rho=-0.15
        )
        tips, scores, outcomes = predictor.solve_optimal_tip(config)
        
        self.assertAlmostEqual(sum(outcomes), 1.0, delta=1e-5)
        self.assertTrue(len(tips) > 0)
        self.assertTrue(0 <= tips[0][0][0] <= 6)
        self.assertTrue(0 <= tips[0][0][1] <= 6)

    def test_t3_cf2_nb_travel_solver(self):
        """Integrates the Negative Binomial model, severe travel fatigue, and the solver."""
        if not is_negative_binomial_implemented() or not is_contextual_factors_implemented():
            self.skipTest("Negative Binomial (F1) or Contextual factors (F2) not implemented yet")
            
        context_A = {"travel_miles": 8000.0, "tz_crossed": 10, "direction": "East", "rest_days": 1.0}
        context_B = {"travel_miles": 0.0, "tz_crossed": 0, "direction": "None", "rest_days": 7.0}
        
        lambda_A_adj, lambda_B_adj = predictor.get_adjusted_lambdas(1.8, 1.5, context_A, context_B)
        
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.NEGATIVE_BINOMIAL,
            mu_a=lambda_A_adj,
            mu_b=lambda_B_adj,
            alpha_a=0.3,
            alpha_b=0.2
        )
        tips, scores, outcomes = predictor.solve_optimal_tip(config)
        self.assertAlmostEqual(sum(outcomes), 1.0, delta=1e-5)
        self.assertLess(lambda_A_adj, 1.8)
        self.assertGreater(lambda_B_adj, 1.5)

    def test_t3_cf3_host_climate_solver(self):
        """Integrates host advantage, climate penalty, and the solver."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        context_A = {"status": "True Home", "fan_support_pct": 0.7, "temp": 34.0, "humidity": 75.0, "heat_accl_days": 10.0}
        context_B = {"status": "Neutral", "fan_support_pct": 0.3, "temp": 34.0, "humidity": 75.0, "heat_accl_days": 1.0}
        
        lambda_A_adj, lambda_B_adj = predictor.get_adjusted_lambdas(1.6, 1.6, context_A, context_B)
        self.assertGreater(lambda_A_adj, lambda_B_adj)
        
        tips, _, outcomes = predictor.solve_optimal_tip(lambda_A_adj, lambda_B_adj)
        self.assertAlmostEqual(sum(outcomes), 1.0, delta=1e-5)

    def test_t3_cf4_backtest_pipeline_integration(self):
        """Executes the complete pipeline from parsing metadata, running models, applying factors, solving, and comparing."""
        if not is_backtester_implemented() or not is_contextual_factors_implemented():
            self.skipTest("Backtesting suite (F4) or Contextual factors (F2) not implemented yet")
            
        import backtest
        csv_path = "temp_pipeline.csv"
        with open(csv_path, "w") as f:
            f.write("team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n")
            f.write("Germany,Mexico,1,2,2240,25,50\n")
            f.write("USA,England,1,1,0,20,40\n")
            
        try:
            data = backtest.load_match_data(csv_path)
            results_base = backtest.run_backtest(model_type="baseline", data=data)
            results_opt = backtest.run_backtest(model_type="optimized", data=data)
            report = backtest.generate_summary_report(results_base, results_opt)
            self.assertIn("delta_total_points", report)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

if __name__ == '__main__':
    unittest.main()
