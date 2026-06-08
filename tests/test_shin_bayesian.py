import unittest
import math
from utils.math_utils import strip_vig_shin
from predictor import blend_lambdas, predict_single_match, CONSTANTS, DEFAULT_CONSTANTS

class TestShinDeVig(unittest.TestCase):
    """Unit tests for strip_vig_shin and Shin's Method analytical de-vigging."""
    
    def test_shin_standard_overround(self):
        # Standard soccer odds: Home=2.5, Draw=3.2, Away=2.8
        pi_h, pi_d, pi_a = 1.0 / 2.5, 1.0 / 3.2, 1.0 / 2.8
        (p_h, p_d, p_a), z = strip_vig_shin(pi_h, pi_d, pi_a)
        
        # Fair probabilities must sum to 1.0
        self.assertAlmostEqual(p_h + p_d + p_a, 1.0, places=7)
        # Insider trading proportion z must be between 0.0 and 1.0
        self.assertTrue(0.0 <= z < 1.0)
        # Probabilities should be positive
        self.assertTrue(p_h > 0 and p_d > 0 and p_a > 0)

    def test_shin_fallback_no_overround(self):
        # Arbitrage or no overround: sum of pi <= 1.0
        # e.g., 2.0, 4.0, 4.0 -> sum of pi = 0.5 + 0.25 + 0.25 = 1.0
        (p_h, p_d, p_a), z = strip_vig_shin(0.5, 0.25, 0.25)
        self.assertAlmostEqual(p_h, 0.5, places=7)
        self.assertAlmostEqual(p_d, 0.25, places=7)
        self.assertAlmostEqual(p_a, 0.25, places=7)
        self.assertEqual(z, 0.0)

    def test_shin_fallback_extreme_odds(self):
        # Extreme odds violating Shin's assumption sum_pi_sq >= 1.0
        # e.g., pi = [0.95, 0.1, 0.1] -> sum_pi = 1.15, sum_pi_sq = 0.9025 + 0.01 + 0.01 = 0.9225 < 1.0 (valid)
        # but pi = [0.99, 0.1, 0.1] -> sum_pi_sq = 0.99**2 + 0.02 = 1.0001 >= 1.0 (invalid)
        (p_h, p_d, p_a), z = strip_vig_shin(0.99, 0.1, 0.1)
        self.assertEqual(z, 0.0)
        self.assertAlmostEqual(p_h + p_d + p_a, 1.0, places=7)

    def test_shin_division_by_zero_safety(self):
        # All pi are 0.0
        (p_h, p_d, p_a), z = strip_vig_shin(0.0, 0.0, 0.0)
        self.assertAlmostEqual(p_h, 1.0/3.0, places=7)
        self.assertAlmostEqual(p_d, 1.0/3.0, places=7)
        self.assertAlmostEqual(p_a, 1.0/3.0, places=7)
        self.assertEqual(z, 0.0)


class TestBayesianBlending(unittest.TestCase):
    """Unit tests for Bayesian Precision-Weighted Blending."""
    
    def setUp(self):
        # Reset CONSTANTS to defaults before each test to ensure consistency
        global CONSTANTS
        for k, v in DEFAULT_CONSTANTS.items():
            CONSTANTS[k] = v

    def test_blend_fallback_to_linear(self):
        # When volume and time are None, it should do the standard linear blend
        # With market_weight=0.8, Elo=1.0, Market=2.0 -> 0.8*2.0 + 0.2*1.0 = 1.8
        la, lb = blend_lambdas(1.0, 1.0, 2.0, 2.0, market_weight=0.8)
        self.assertAlmostEqual(la, 1.8, places=4)
        self.assertAlmostEqual(lb, 1.8, places=4)

    def test_blend_bayesian_volume_only(self):
        # Volume only: V=1,000,000, t=None
        # tau_mkt = alpha * ln(V) = 0.1 * 13.81551 = 1.381551
        # tau_mod = 1.0
        # Elo=1.0, Market=2.0
        # ln_la = (1.381551 * ln(2.0) + 1.0 * ln(1.0)) / 2.381551
        #        = (1.381551 * 0.693147 + 0) / 2.381551 = 0.402107
        # la = exp(0.402107) = 1.4950
        la, lb = blend_lambdas(1.0, 1.0, 2.0, 2.0, volume=1000000.0)
        self.assertAlmostEqual(la, 1.4950, places=3)

    def test_blend_bayesian_time_only(self):
        # Time only: V=None, t=0 (kickoff)
        # tau_mkt = beta * exp(0) = 0.5
        # tau_mod = 1.0
        # Elo=1.0, Market=2.0
        # ln_la = (0.5 * ln(2.0) + 1.0 * ln(1.0)) / 1.5 = (0.5 * 0.693147) / 1.5 = 0.231049
        # la = exp(0.231049) = 1.2599
        la, lb = blend_lambdas(1.0, 1.0, 2.0, 2.0, time_to_kickoff=0.0)
        self.assertAlmostEqual(la, 1.2599, places=3)

    def test_blend_bayesian_both(self):
        # Both: V=1,000,000, t=0
        # tau_mkt = 0.1 * ln(1e6) + 0.5 * exp(0) = 1.381551 + 0.5 = 1.881551
        # tau_mod = 1.0
        # Elo=1.0, Market=2.0
        # ln_la = (1.881551 * ln(2.0) + 1.0 * ln(1.0)) / 2.881551 = 1.30419 / 2.881551 = 0.4526
        # la = exp(0.4526) = 1.5724
        la, lb = blend_lambdas(1.0, 1.0, 2.0, 2.0, time_to_kickoff=0.0, volume=1000000.0)
        self.assertAlmostEqual(la, 1.5724, places=3)

    def test_blend_volume_safety(self):
        # Volume = 0 should be safe and not cause math domain error
        la, lb = blend_lambdas(1.0, 1.0, 2.0, 2.0, time_to_kickoff=24.0, volume=0.0)
        self.assertTrue(la > 0)


class TestIntegration(unittest.TestCase):
    """Integration tests verifying predictor pipeline uses new features."""
    
    def test_predict_single_match_market_z(self):
        # Test predict_single_match returns market_z
        row = {
            "team_a": "Spain",
            "team_b": "Germany",
            "odds_home": 2.5,
            "odds_draw": 3.2,
            "odds_away": 2.8,
            "time_to_kickoff": 12.0,
            "volume": 500000.0
        }
        res = predict_single_match(row)
        
        # Result must contain market_z and it should be > 0 (as there is overround)
        self.assertIn("market_z", res)
        self.assertTrue(res["market_z"] > 0)
        
        # Test without odds
        row_no_odds = {
            "team_a": "Spain",
            "team_b": "Germany",
        }
        res_no_odds = predict_single_match(row_no_odds)
        self.assertIn("market_z", res_no_odds)
        self.assertEqual(res_no_odds["market_z"], 0.0)
