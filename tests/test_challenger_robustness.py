import unittest
import os
import sys
import math

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from predictor import get_points, solve_optimal_tip_from_grid
import predictor

class TestChallengerRobustness(unittest.TestCase):

    def test_max_tip_greater_than_max_goals(self):
        """1. Verify robustness when max_tip > max_goals (e.g. max_tip=8, max_goals=3)"""
        # Create a simple grid with max_goals=3 (dimensions 4x4)
        grid = {
            0: {0: 0.2, 1: 0.1, 2: 0.0, 3: 0.0},
            1: {0: 0.1, 1: 0.2, 2: 0.1, 3: 0.0},
            2: {0: 0.0, 1: 0.1, 2: 0.1, 3: 0.0},
            3: {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.1}
        }
        # Run solver with max_tip = 8
        sorted_tips, sorted_scores, outcomes = solve_optimal_tip_from_grid(grid, max_tip=8)
        
        # Verify that lookup outside grid boundaries (e.g. t_a = 8, t_b = 8) does not crash
        self.assertTrue(len(sorted_tips) > 0)
        # Total number of tips should be (8+1)*(8+1) = 81
        self.assertEqual(len(sorted_tips), 81)
        
        # Check EV for a tip outside grid boundaries (e.g. (8, 0))
        # diff = 8 > 0, so ev = p_t + diff_probs.get(8, 0) + 2.0 * prob_home
        # since max_goals=3, diff_probs has no entry for 8, and p_t = 0.0
        # prob_home = P(1,0)+P(2,0)+P(2,1)+P(3,0)+P(3,1)+P(3,2) = 0.1 + 0.0 + 0.1 + 0.0 + 0.0 + 0.0 = 0.2
        # ev = 0.0 + 0.0 + 2.0 * 0.2 = 0.4
        tip_80_ev = next(ev for tip, ev in sorted_tips if tip == (8, 0))
        self.assertAlmostEqual(tip_80_ev, 0.4)

    def test_negative_inputs(self):
        """2. Verify robustness under negative inputs"""
        # Negative parameters passed to solve_optimal_tip should be clamped or handled safely.
        # solve_optimal_tip clamps max_tip and max_goals to [0, 100], and lambdas to >= 0.
        tips, scores, outcomes = predictor.solve_optimal_tip(
            config_or_lamA=-1.5, lam_B=-2.0, rho=-0.5, max_goals=-5, max_tip=-3
        )
        # Clamped: lambda_A=0.0, lambda_B=0.0, max_goals=0, max_tip=0
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0][0], (0, 0))
        self.assertAlmostEqual(scores[0][1], 1.0)
        self.assertEqual(len(tips), 1)
        self.assertEqual(tips[0][0], (0, 0))

    def test_division_by_zero(self):
        """3. Verify robustness against division by zero"""
        # Ensure that zero inputs do not cause division by zero in probability engine
        # e.g., temperature = -237.3 (where denom = temp + 237.3 is 0)
        wbgt = predictor.calculate_wbgt(-237.3, 50.0)
        # Should not raise division by zero
        self.assertIsNotNone(wbgt)

        # Extreme alpha and mu in negative binomial
        p = predictor.negative_binomial_probability(2, 0.0, 0.0)
        self.assertIsNotNone(p)

    def test_empty_grids(self):
        """4. Verify robustness under empty grids"""
        # Empty dict grid
        sorted_tips, sorted_scores, outcomes = solve_optimal_tip_from_grid({}, max_tip=3)
        self.assertEqual(sorted_scores, [])
        self.assertEqual(outcomes, (0.0, 0.0, 0.0))
        # Total number of tips should be (3+1)*(3+1) = 16, all with EV = 0.0
        self.assertEqual(len(sorted_tips), 16)
        for tip, ev in sorted_tips:
            self.assertEqual(ev, 0.0)

        # Empty list grid
        sorted_tips, sorted_scores, outcomes = solve_optimal_tip_from_grid([], max_tip=3)
        self.assertEqual(sorted_scores, [])
        self.assertEqual(outcomes, (0.0, 0.0, 0.0))
        self.assertEqual(len(sorted_tips), 16)
        for tip, ev in sorted_tips:
            self.assertEqual(ev, 0.0)

        # List of empty list grid
        sorted_tips, sorted_scores, outcomes = solve_optimal_tip_from_grid([[]], max_tip=3)
        self.assertEqual(sorted_scores, [])
        self.assertEqual(outcomes, (0.0, 0.0, 0.0))
        self.assertEqual(len(sorted_tips), 16)
        for tip, ev in sorted_tips:
            self.assertEqual(ev, 0.0)

    def test_very_large_parameters(self):
        """5. Verify robustness under very large parameters"""
        # Very large lambdas / max_goals / max_tip
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1e10,
            mu_b=1e10,
            rho=0.1,
            max_goals=1000000,
            max_tip=1000000
        )
        # solve_optimal_tip clamps max_goals and max_tip to 100, and mu_a/mu_b to 10000.0
        tips, scores, outcomes = predictor.solve_optimal_tip(config)
        self.assertTrue(len(tips) > 0)
        self.assertAlmostEqual(sum(outcomes), 1.0, delta=1e-5)

if __name__ == '__main__':
    unittest.main()
