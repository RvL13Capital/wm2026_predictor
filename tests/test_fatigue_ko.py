"""Offline tests for fatigue_engine.fatigue_adjusted_ko_tip.

Pins the knockout-convention correctness: the fatigue overlay must rebuild the
SAME shootout_total grid the main KO tip uses (NO draws), not the 90' draw-allowed
grid that fatigue_adjusted_tip uses for group games. Pure-function tests — no
network, no FIFA calendar.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import predictor
from predictor import (
    MatchModelConfig, ModelDistribution, MatchPhase,
    generate_ko_final_grid, solve_optimal_tip_from_grid,
)
import fatigue_engine


def _ko_config(mu_a, mu_b):
    return MatchModelConfig(
        dist_type=ModelDistribution.POISSON, mu_a=mu_a, mu_b=mu_b,
        alpha_a=0.0, alpha_b=0.0, rho=-0.06, max_goals=12, max_tip=10,
        pts_exact=4, pts_diff=3, pts_tend=2, phase=MatchPhase.R32,
    )


class TestFatigueAdjustedKoTip(unittest.TestCase):

    def test_no_draw_under_shootout_total(self):
        # A balanced tie that on a 90' grid would optimize to a draw must NOT be a
        # draw here — shootout_total has no legal draw.
        cfg = _ko_config(1.0, 1.0)
        out = fatigue_engine.fatigue_adjusted_ko_tip(1.0, 1.0, cfg, 1.0, 1.0, "A", "B")
        self.assertEqual(out["p_draw"], 0.0)
        self.assertNotEqual(out["tip_a"], out["tip_b"], "shootout_total tip must not be a draw")
        # ~1.0 up to grid truncation at 15 goals (tiny tail mass falls off the grid)
        self.assertAlmostEqual(out["p_home"] + out["p_away"], 1.0, places=3)

    def test_factor_one_matches_direct_ko_grid(self):
        # factors=1.0 must reproduce the main KO path: same grid, same solver.
        cfg = _ko_config(1.8, 0.7)
        out = fatigue_engine.fatigue_adjusted_ko_tip(1.8, 0.7, cfg, 1.0, 1.0, "A", "B")
        base = predictor.CONSTANTS["pen_conversion_rate"]
        grid = generate_ko_final_grid(
            cfg, max_final_goals=15,
            pen_conv_a=base * predictor.PENALTY_STRENGTH.get("A", 1.0),
            pen_conv_b=base * predictor.PENALTY_STRENGTH.get("B", 1.0))
        tips, _, _ = solve_optimal_tip_from_grid(grid, 10, pts_exact=4, pts_diff=3, pts_tend=2)
        self.assertEqual(out["tip"], f"{tips[0][0][0]}:{tips[0][0][1]}")
        self.assertAlmostEqual(out["ev"], tips[0][1], places=9)

    def test_symmetric_fatigue_does_not_raise_total(self):
        # Symmetric capacity cut lowers both lambdas -> the tip's goal total must not
        # increase (fatigue = fewer goals, never more).
        cfg = _ko_config(2.6, 0.5)
        main = fatigue_engine.fatigue_adjusted_ko_tip(2.6, 0.5, cfg, 1.0, 1.0, "A", "B")
        tired = fatigue_engine.fatigue_adjusted_ko_tip(2.6, 0.5, cfg, 0.75, 0.75, "A", "B")
        self.assertLessEqual(tired["tip_a"] + tired["tip_b"], main["tip_a"] + main["tip_b"])
        # winner unchanged by a symmetric cut on a clear favourite
        self.assertGreater(main["tip_a"], main["tip_b"])
        self.assertGreaterEqual(tired["tip_a"], tired["tip_b"])

    def test_asymmetric_fatigue_shifts_toward_fresher_team(self):
        # Heavily fatigue the home favourite only -> its expected margin shrinks.
        cfg = _ko_config(1.9, 1.1)
        fresh = fatigue_engine.fatigue_adjusted_ko_tip(1.9, 1.1, cfg, 1.0, 1.0, "A", "B")
        home_tired = fatigue_engine.fatigue_adjusted_ko_tip(1.9, 1.1, cfg, 0.65, 1.0, "A", "B")
        self.assertGreaterEqual(fresh["p_home"], home_tired["p_home"],
                                "fatiguing the home side must not increase its win prob")


if __name__ == "__main__":
    unittest.main()
