"""In-play/settled book guard (odds_client.is_degenerate_1x2).

Polymarket's `closed` flag lags the final whistle: on opening day the finished
Korea Republic|Czechia game listed 1.001/2000/2000 and reached the matchday
blend (tip flipped to 4:0) before being caught. The guard excludes such books
at the fetch boundary so neither tips blending nor the scanner ever sees them.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odds_client import DEGENERATE_MAX_ODDS, DEGENERATE_MIN_ODDS, is_degenerate_1x2


class TestDegenerateGuard(unittest.TestCase):
    def test_settled_book_excluded(self):
        # the observed opening-day case
        self.assertTrue(is_degenerate_1x2(1.001, 2000.0, 2000.0))

    def test_high_side_alone_triggers(self):
        self.assertTrue(is_degenerate_1x2(1.30, 4.0, 250.0))

    def test_low_side_alone_triggers(self):
        self.assertTrue(is_degenerate_1x2(1.01, 15.0, 30.0))

    def test_premarket_extremes_pass(self):
        # opener-day real extremes: Germany 1.07 favourite, Iraq 28.2 longshot
        self.assertFalse(is_degenerate_1x2(1.07, 9.5, 41.0))
        self.assertFalse(is_degenerate_1x2(1.16, 7.6, 28.2))

    def test_normal_book_passes(self):
        self.assertFalse(is_degenerate_1x2(1.46, 4.88, 9.52))

    def test_bounds_are_sane(self):
        # margin between the pre-match world and the guard must stay wide
        self.assertLess(DEGENERATE_MIN_ODDS, 1.05)
        self.assertGreater(DEGENERATE_MAX_ODDS, 100.0)


if __name__ == "__main__":
    unittest.main()
