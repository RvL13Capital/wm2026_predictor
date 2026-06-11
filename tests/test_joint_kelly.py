"""Simultaneous-Kelly tests (plan step S17).

The reference is a brute-force grid maximization of E[log wealth] over the
stake simplex — the algorithm must match it to fine tolerance on small books,
reduce to the binary Kelly formula for a single leg, and never bet without
edge. These guard the one piece of betting math the review found actually
wrong (independent sizing of mutually exclusive legs over-allocates).
"""
import itertools
import math
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.math_utils import kelly_mutually_exclusive


def expected_log_growth(probs, odds, stakes):
    """E[log(1 - Σf + f_i·o_i)] with residual mass losing all stakes."""
    total = sum(stakes)
    g = 0.0
    residual = 1.0 - sum(probs)
    for p, o, f in zip(probs, odds, stakes):
        g += p * math.log(max(1e-12, 1.0 - total + f * o))
    if residual > 0:
        g += residual * math.log(max(1e-12, 1.0 - total))
    return g


def brute_force(probs, odds, step=0.004):
    """Grid search over the stake simplex (full Kelly)."""
    n = len(probs)
    grids = [[round(k * step, 6) for k in range(int(0.6 / step))] for _ in range(n)]
    best, best_g = [0.0] * n, expected_log_growth(probs, odds, [0.0] * n)
    for combo in itertools.product(*grids):
        if sum(combo) >= 0.999:
            continue
        g = expected_log_growth(probs, odds, list(combo))
        if g > best_g:
            best_g, best = g, list(combo)
    return best, best_g


class TestJointKelly(unittest.TestCase):

    def assert_matches_brute_force(self, probs, odds):
        stakes = kelly_mutually_exclusive(probs, odds, fraction=1.0)
        _, g_ref = brute_force(probs, odds)
        g_alg = expected_log_growth(probs, odds, stakes)
        # The algorithm is exact; the grid is the approximation — so the
        # algorithm's growth must be >= the grid's minus grid resolution slack.
        self.assertGreaterEqual(g_alg, g_ref - 1e-4,
                                f"stakes {stakes} growth {g_alg:.6f} < grid ref {g_ref:.6f}")

    def test_two_outcome_book_matches_brute_force(self):
        # Complete 2-outcome book, model edge on the favourite
        self.assert_matches_brute_force([0.60, 0.40], [1.90, 2.40])

    def test_three_outcome_1x2_matches_brute_force(self):
        # 1X2 with model edge on home and draw
        self.assert_matches_brute_force([0.50, 0.28, 0.22], [2.30, 3.80, 3.20])

    def test_outright_style_partial_book_matches_brute_force(self):
        # Three favourites of a winner book (probs don't sum to 1)
        self.assert_matches_brute_force([0.22, 0.18, 0.15], [6.0, 7.0, 8.0])

    def test_single_leg_reduces_to_binary_kelly(self):
        p, o = 0.55, 2.10
        stakes = kelly_mutually_exclusive([p], [o], fraction=1.0)
        b = o - 1.0
        binary = (b * p - (1.0 - p)) / b
        self.assertAlmostEqual(stakes[0], binary, places=10)

    def test_no_edge_no_bet(self):
        # p·o < 1 on every leg → empty allocation
        stakes = kelly_mutually_exclusive([0.30, 0.30, 0.30], [3.0, 3.0, 3.0], fraction=1.0)
        self.assertEqual(stakes, [0.0, 0.0, 0.0])

    def test_independent_sizing_is_growth_suboptimal(self):
        """The point of the fix: per-leg binary Kelly ignores that every other
        stake in the book is lost when leg i wins (and that legs hedge each
        other), so its allocation is NOT growth-optimal. Note the direction is
        not fixed — on mutually exclusive legs the joint optimum can stake MORE
        in aggregate (hedging) or less; the guarantee is optimality, asserted
        here as strictly higher E[log growth] on the same book."""
        for probs, odds in ([0.40, 0.35], [3.0, 3.2]), ([0.22, 0.18, 0.15], [6.0, 7.0, 8.0]):
            joint = kelly_mutually_exclusive(probs, odds, fraction=1.0)
            independent = [max(0.0, ((o - 1.0) * p - (1.0 - p)) / (o - 1.0))
                           for p, o in zip(probs, odds)]
            g_joint = expected_log_growth(probs, odds, joint)
            g_indep = expected_log_growth(probs, odds, independent)
            self.assertGreater(g_joint, g_indep + 1e-6,
                               f"joint {joint} must out-grow independent {independent}")
            self.assertGreater(sum(joint), 0.0)

    def test_fraction_scales_linearly(self):
        probs, odds = [0.50, 0.28, 0.22], [2.30, 3.80, 3.20]
        full = kelly_mutually_exclusive(probs, odds, fraction=1.0)
        quarter = kelly_mutually_exclusive(probs, odds, fraction=0.25)
        for f, q in zip(full, quarter):
            self.assertAlmostEqual(q, 0.25 * f, places=12)

    def test_degenerate_inputs(self):
        self.assertEqual(kelly_mutually_exclusive([], []), [])
        self.assertEqual(kelly_mutually_exclusive([0.5], [1.0]), [0.0])   # odds <= 1
        self.assertEqual(kelly_mutually_exclusive([0.0], [5.0]), [0.0])   # zero prob
        # Stakes always non-negative and sum < 1
        stakes = kelly_mutually_exclusive([0.5, 0.45], [2.5, 2.6], fraction=1.0)
        self.assertTrue(all(s >= 0 for s in stakes))
        self.assertLess(sum(stakes), 1.0)


if __name__ == "__main__":
    unittest.main()
