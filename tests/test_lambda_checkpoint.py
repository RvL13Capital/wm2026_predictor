"""Tripwire statistics of the pre-registered λ-freeze checkpoint.

Tests the pure evaluate() math and the band-conditional probability — the
engine-grid plumbing is exercised by the script's own smoke path.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.lambda_checkpoint import MIN_BANDED, Z_TRIGGER, band_conditional_p, evaluate


class TestEvaluate(unittest.TestCase):
    def test_zero_deficit_no_trigger(self):
        # realized hits exactly match the claim -> z ~ 0, no trigger
        banded = [(True, 0.5), (False, 0.5)] * 20
        s = evaluate(banded)
        self.assertAlmostEqual(s["z"], 0.0, places=9)
        self.assertFalse(s["triggered"])

    def test_known_z(self):
        # 40 in-band tips, each claimed p=0.5, only 10 exact hits:
        # z = (10 - 20) / sqrt(40 * 0.25) = -10 / sqrt(10)
        banded = [(True, 0.5)] * 10 + [(False, 0.5)] * 30
        s = evaluate(banded)
        self.assertAlmostEqual(s["z"], -10 / math.sqrt(10.0), places=9)
        self.assertTrue(s["triggered"])

    def test_min_sample_gate(self):
        # massive deficit but n < MIN_BANDED -> reported, never triggered
        banded = [(False, 0.9)] * (MIN_BANDED - 1)
        s = evaluate(banded)
        self.assertLess(s["z"], Z_TRIGGER)
        self.assertFalse(s["triggered"])

    def test_overperformance_never_triggers(self):
        banded = [(True, 0.2)] * 40
        s = evaluate(banded)
        self.assertGreater(s["z"], 0)
        self.assertFalse(s["triggered"])


class TestBandConditional(unittest.TestCase):
    def test_uniform_grid_one_zero_tip(self):
        # 3x3 uniform grid, tip 1:0. Band (>=3 pts vs 1:0) = home wins by
        # exactly 1: (1,0) and (2,1) -> P(band)=2/9, P(exact|band)=1/2.
        grid = {a: {b: 1.0 / 9.0 for b in range(3)} for a in range(3)}
        p_cond, p_band = band_conditional_p(grid, 1, 0)
        self.assertAlmostEqual(p_band, 2.0 / 9.0, places=9)
        self.assertAlmostEqual(p_cond, 0.5, places=9)

    def test_draw_tip_band_is_exact_only_under_draws2(self):
        # draws=2 (operator-verified 2026-06-27): a 0:0 tip earns 4 on exact 0:0 but only
        # 2 (TENDENCY, no Tordifferenz) on other draws (1:1, 2:2) -> the >=3-pt band is
        # JUST {(0,0)}, not the whole diagonal. (Corrects the old draws=3 assumption.)
        grid = {a: {b: 1.0 / 9.0 for b in range(3)} for a in range(3)}
        p_cond, p_band = band_conditional_p(grid, 0, 0)
        self.assertAlmostEqual(p_band, 1.0 / 9.0, places=9)
        self.assertAlmostEqual(p_cond, 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
