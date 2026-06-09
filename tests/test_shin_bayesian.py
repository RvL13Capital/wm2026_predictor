import unittest
import math
from utils.math_utils import strip_vig_shin, devig_shin, devig_book
from predictor import blend_lambdas, predict_single_match, CONSTANTS, DEFAULT_CONSTANTS

class TestShinDeVig(unittest.TestCase):
    """Unit tests for strip_vig_shin — canonical (iterative) Shin de-vigging.

    These assert against the *true* Shin estimator (Newton-Raphson on the
    sqrt model), cross-checked with an independent bisection reference. The
    previously shipped quadratic stand-in returned a meaningless z (~0.90 on
    these odds); the guards below lock that regression out for good.
    """

    def test_shin_standard_overround(self):
        # Standard soccer odds: Home=2.5, Draw=3.2, Away=2.8 (booksum 1.0696).
        pi_h, pi_d, pi_a = 1.0 / 2.5, 1.0 / 3.2, 1.0 / 2.8
        (p_h, p_d, p_a), z = strip_vig_shin(pi_h, pi_d, pi_a)

        # Fair probabilities must sum to 1.0.
        self.assertAlmostEqual(p_h + p_d + p_a, 1.0, places=7)
        # Canonical Shin values (verified vs. independent bisection solver).
        self.assertAlmostEqual(z, 0.0348, places=3)
        self.assertAlmostEqual(p_h, 0.3760, places=3)
        self.assertAlmostEqual(p_d, 0.2900, places=3)
        self.assertAlmostEqual(p_a, 0.3339, places=3)
        # Direction: Shin shades the favourite UP vs. naive normalisation.
        naive_h = pi_h / (pi_h + pi_d + pi_a)
        self.assertGreater(p_h, naive_h)

    def test_shin_z_is_realistic_not_quadratic_fake(self):
        # Regression guard for the integrity hotfix: the insider proportion z
        # for ordinary football odds is a few percent — NOT ~0.9 as the old
        # quadratic fake produced.
        for odds in ([2.5, 3.2, 2.8], [1.8, 3.6, 4.5], [1.2, 7.0, 15.0]):
            pi = [1.0 / o for o in odds]
            _probs, z = strip_vig_shin(*pi)
            self.assertTrue(0.0 < z < 0.10, f"z={z} out of realistic range for {odds}")

    def test_shin_fallback_no_overround(self):
        # No overround (booksum == 1.0): Shin undefined -> proportional normalise.
        (p_h, p_d, p_a), z = strip_vig_shin(0.5, 0.25, 0.25)
        self.assertAlmostEqual(p_h, 0.5, places=7)
        self.assertAlmostEqual(p_d, 0.25, places=7)
        self.assertAlmostEqual(p_a, 0.25, places=7)
        self.assertEqual(z, 0.0)

    def test_shin_strong_favourite(self):
        # Strong favourite, real overround (booksum 1.19). Canonical Shin is
        # well-defined here (no artificial fallback); values vs. bisection ref.
        (p_h, p_d, p_a), z = strip_vig_shin(0.99, 0.1, 0.1)
        self.assertAlmostEqual(p_h + p_d + p_a, 1.0, places=7)
        self.assertTrue(0.0 < z < 1.0)
        self.assertAlmostEqual(z, 0.1272, places=3)
        self.assertAlmostEqual(p_h, 0.9013, places=3)

    def test_shin_division_by_zero_safety(self):
        # All pi are 0.0 -> uniform, z = 0.
        (p_h, p_d, p_a), z = strip_vig_shin(0.0, 0.0, 0.0)
        self.assertAlmostEqual(p_h, 1.0/3.0, places=7)
        self.assertAlmostEqual(p_d, 1.0/3.0, places=7)
        self.assertAlmostEqual(p_a, 1.0/3.0, places=7)
        self.assertEqual(z, 0.0)

    def test_devig_book_nway(self):
        # N-way book de-vig (used by edge_scanner). Favourite first.
        implied = [1.0/1.5, 1.0/4.0, 1.0/7.0]  # booksum 1.0595 (real overround)
        basic = devig_book(implied, method="basic")
        shin = devig_book(implied, method="shin")
        self.assertAlmostEqual(sum(basic), 1.0, places=7)
        self.assertAlmostEqual(sum(shin), 1.0, places=7)
        # Basic = proportional normalisation.
        s = sum(implied)
        self.assertAlmostEqual(basic[0], implied[0] / s, places=7)
        # Shin shades favourite up, longshot down vs. basic.
        self.assertGreater(shin[0], basic[0])
        self.assertLess(shin[-1], basic[-1])


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
