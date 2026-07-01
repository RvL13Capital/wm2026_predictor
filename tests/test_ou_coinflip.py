"""Offline tests for the tendency-preserving O/U coin-flip integration.

Pins the operator-validated rule (backtest 2026-07-01): re-slave the goal TOTAL to
the market coin-flip line, but NEVER flip the model's tendency (a draw stays a draw)
— which is what turned the group-stage O/U backtest from -3 (naive) to +1. Plus the
coin-flip-line interpolation and the liquidity guard. Pure-function; no network.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import predictor
from predictor import MatchModelConfig, ModelDistribution, MatchPhase
import ou_total_engine as ou


def _cfg(mu_a, mu_b, ko=False):
    return MatchModelConfig(
        dist_type=ModelDistribution.POISSON, mu_a=mu_a, mu_b=mu_b,
        alpha_a=0.0, alpha_b=0.0, rho=-0.05, max_goals=8, max_tip=6,
        pts_exact=4, pts_diff=3, pts_tend=2,
        phase=MatchPhase.R32 if ko else None,
    )


class TestCoinflipTotal(unittest.TestCase):
    def test_interpolates_crossing(self):
        totals = [{"line": 1.5, "over": 0.70, "liq": 1e5},
                  {"line": 2.5, "over": 0.45, "liq": 1e5}]
        line, liq = ou.coinflip_total(totals)
        # 0.5 is 0.8 of the way from 0.70 down to 0.45 -> line 1.5 + 0.8 = 2.30
        self.assertAlmostEqual(line, 2.30, places=6)
        self.assertEqual(liq, 1e5)

    def test_no_crossing_returns_none(self):
        totals = [{"line": 0.5, "over": 0.40, "liq": 1e5}]  # already below 0.5
        self.assertEqual(ou.coinflip_total(totals), (None, None))


class TestTendencyPreserved(unittest.TestCase):
    def test_draw_stays_draw_even_at_high_total(self):
        # Symmetric lambdas -> model tips a draw. Re-slaving to a HIGHER total must NOT
        # flip it to a win (the whole point of the fix — protects points-rich 0:0 tips).
        cfg = _cfg(0.6, 0.6)
        model = (0, 0)
        for total in (2.0, 2.5, 3.0, 3.5):
            ta, tb = ou.ou_tendency_preserving_tip(0.6, 0.6, cfg, total, model)
            self.assertEqual(ta, tb, f"draw flipped to {ta}:{tb} at total {total}")

    def test_home_win_stays_home_win(self):
        cfg = _cfg(1.8, 0.7)
        ta, tb = ou.ou_tendency_preserving_tip(1.8, 0.7, cfg, 3.5, (1, 0))
        self.assertGreater(ta, tb)

    def test_total_moves_toward_market(self):
        # The scoreline total should track the market total (goals go up when the
        # market sees more), within the preserved tendency.
        cfg = _cfg(1.4, 0.6)
        low = ou.ou_tendency_preserving_tip(1.4, 0.6, cfg, 1.6, (1, 0))
        high = ou.ou_tendency_preserving_tip(1.4, 0.6, cfg, 3.6, (1, 0))
        self.assertLessEqual(sum(low), sum(high))
        self.assertGreater(low[0], low[1])   # both still home wins
        self.assertGreater(high[0], high[1])

    def test_ko_shootout_never_draws(self):
        cfg = _cfg(2.0, 0.6, ko=True)
        ta, tb = ou.ou_tendency_preserving_tip(2.0, 0.6, cfg, 2.5, (1, 0),
                                               ko_convention="shootout_total",
                                               team_a="A", team_b="B")
        self.assertNotEqual(ta, tb)


class TestLiquidityGuard(unittest.TestCase):
    def test_low_liquidity_keeps_model_tip(self):
        cfg = _cfg(1.4, 0.6)
        extras = {"totals": [{"line": 1.5, "over": 0.70, "liq": 500.0},
                             {"line": 2.5, "over": 0.45, "liq": 500.0}]}  # 500 << 40k
        tip, meta = ou.ou_adjusted_from_extras(1.4, 0.6, cfg, extras, (1, 0))
        self.assertEqual(tip, (1, 0))
        self.assertFalse(meta["eligible"])

    def test_sufficient_liquidity_fires(self):
        cfg = _cfg(1.4, 0.6)
        extras = {"totals": [{"line": 1.5, "over": 0.70, "liq": 1e5},
                             {"line": 2.5, "over": 0.45, "liq": 1e5}]}
        tip, meta = ou.ou_adjusted_from_extras(1.4, 0.6, cfg, extras, (1, 0))
        self.assertTrue(meta["eligible"])
        self.assertGreater(tip[0], tip[1])   # tendency preserved (home win)


if __name__ == "__main__":
    unittest.main()
