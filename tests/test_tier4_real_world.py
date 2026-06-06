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

class TestTier4RealWorld(unittest.TestCase):

    def test_t4_rw1_mexico_city_azteca(self):
        """Simulates Mexico vs. Germany at Estadio Azteca (2240m altitude)."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        context_mex = {
            "status": "True Home",
            "fan_support_pct": 0.8,
            "elevation": 2240.0,
            "accl_days": 14.0,
            "temp": 22.0,
            "humidity": 45.0
        }
        
        context_ger = {
            "status": "Neutral",
            "fan_support_pct": 0.2,
            "elevation": 2240.0,
            "accl_days": 0.0,
            "temp": 22.0,
            "humidity": 45.0,
            "travel_miles": 6000.0,
            "tz_crossed": 7,
            "direction": "West",
            "rest_days": 3.0
        }
        
        lambda_mex_adj, lambda_ger_adj = predictor.get_adjusted_lambdas(1.2, 1.8, context_mex, context_ger)
        
        self.assertGreater(lambda_mex_adj / 1.2, 1.0)
        self.assertLess(lambda_ger_adj / 1.8, 1.0)

    def test_t4_rw2_miami_heat_humidity(self):
        """Simulates Ecuador vs. England in Miami in July (36°C, 85% humidity)."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        context_ecu = {
            "status": "Neutral",
            "fan_support_pct": 0.5,
            "elevation": 0.0,
            "temp": 36.0,
            "humidity": 85.0,
            "heat_accl_days": 10.0
        }
        
        context_eng = {
            "status": "Neutral",
            "fan_support_pct": 0.5,
            "elevation": 0.0,
            "temp": 36.0,
            "humidity": 85.0,
            "heat_accl_days": 1.0
        }
        
        lambda_ecu_adj, lambda_eng_adj = predictor.get_adjusted_lambdas(1.5, 1.5, context_ecu, context_eng)
        self.assertGreater(lambda_ecu_adj, lambda_eng_adj)

    def test_t4_rw3_canada_vancouver_travel(self):
        """Simulates Canada vs. Japan in Vancouver."""
        if not is_contextual_factors_implemented():
            self.skipTest("Contextual factors (F2) not implemented yet")
            
        context_can = {
            "status": "Co-Host",
            "fan_support_pct": 0.75,
            "elevation": 0.0,
            "temp": 18.0,
            "humidity": 50.0,
            "travel_miles": 0.0,
            "tz_crossed": 0,
            "direction": "None",
            "rest_days": 7.0
        }
        
        context_jap = {
            "status": "Neutral",
            "fan_support_pct": 0.25,
            "elevation": 0.0,
            "temp": 18.0,
            "humidity": 50.0,
            "travel_miles": 4700.0,
            "tz_crossed": 8,
            "direction": "East",
            "rest_days": 3.0
        }
        
        lambda_can_adj, lambda_jap_adj = predictor.get_adjusted_lambdas(1.4, 1.4, context_can, context_jap)
        self.assertGreater(lambda_can_adj, 1.4)
        self.assertLess(lambda_jap_adj, 1.4)

    def test_t4_rw4_france_nb_blowout(self):
        """Simulates France vs. Saudi Arabia using the Negative Binomial model to evaluate blowouts."""
        if not is_negative_binomial_implemented():
            self.skipTest("Negative Binomial (F1) not implemented yet")
            
        mu_fra = 3.0
        p_poisson_5plus = sum(predictor.negative_binomial_prob(k, mu_fra, 0.0) for k in range(5, 13))
        p_nb_5plus = sum(predictor.negative_binomial_prob(k, mu_fra, 0.4) for k in range(5, 13))
        self.assertGreater(p_nb_5plus, p_poisson_5plus)

    def test_t4_rw5_italy_uruguay_draw(self):
        """Simulates defensive Italy (lambda = 1.0) vs. Uruguay (lambda = 1.0) with Dixon-Coles draw inflation."""
        # Using Dixon-Coles draw inflation with negative rho (e.g. rho = -0.2)
        tips, _, outcomes = predictor.solve_optimal_tip(1.0, 1.0, rho=-0.2)
        optimal_tip = tips[0][0]
        # The draw inflation should cause the solver to recommend tipping a draw
        self.assertEqual(optimal_tip[0], optimal_tip[1], f"Expected a draw tip, but got {optimal_tip}")

if __name__ == '__main__':
    unittest.main()
