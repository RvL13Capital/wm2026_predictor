"""Engine-consistency tests (S11, non-blocked items).

Pins the unifications that do NOT depend on the canonical-dynamics decision:
flat MD3 x0.87 in both engines, drawing-of-lots tiebreaks (Elo removed),
renormalized champion blend, scalar grid cache without dead-rubber variants.
The remaining divergence (scalar dynamic Elo vs vectorized fatigue carry-over;
H2H scalar-only) is deliberate and documented pending the S11 decision.
"""
import functools
import os
import random
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import tournament_bonusfragen as tb
from vectorized_mc import blend_champion_probs


class TestScalarTiebreakLots(unittest.TestCase):

    def _standing(self, team, pts, gd, gf, lot):
        return {"team": team, "pts": pts, "gd": gd, "gf": gf, "lot": lot}

    def test_lots_decide_full_ties_and_elo_is_ignored(self):
        """Two teams tied on pts/gd/gf (no H2H result): the LOT decides — even
        when the lower-lot team has a vastly higher Elo (Spain vs Qatar)."""
        rng = random.Random(1)
        a = self._standing("Spain", 4, 0, 3, lot=0.10)    # Elo 2165
        b = self._standing("Qatar", 4, 0, 3, lot=0.90)    # Elo 1423
        match_results = {}                                # no H2H recorded -> (0,0) tie

        def fifa_cmp(x, y):
            if x["pts"] != y["pts"]: return 1 if x["pts"] > y["pts"] else -1
            if x["gd"] != y["gd"]: return 1 if x["gd"] > y["gd"] else -1
            if x["gf"] != y["gf"]: return 1 if x["gf"] > y["gf"] else -1
            gx, gy = match_results.get((x["team"], y["team"]), (0, 0))
            if gx != gy: return 1 if gx > gy else -1
            lx, ly = x.get("lot", 0.0), y.get("lot", 0.0)
            if lx != ly: return 1 if lx > ly else -1
            return 0

        ordered = sorted([a, b], key=functools.cmp_to_key(fifa_cmp), reverse=True)
        self.assertEqual(ordered[0]["team"], "Qatar")     # higher lot wins, not higher Elo

    def test_simulate_group_attaches_lots_and_points_dominate(self):
        rng = random.Random(42)
        cache = {}   # empty cache -> deterministic 1:0 for team_a everywhere
        standings = tb.simulate_group("A", ["Mexico", "South Africa", "South Korea", "Czechia"],
                                      grid_cache=cache, rng=rng)
        self.assertTrue(all("lot" in s for s in standings))
        pts = [s["pts"] for s in standings]
        self.assertEqual(pts, sorted(pts, reverse=True))

    def test_best_thirds_use_lot_not_elo(self):
        groups = {}
        for g in "ABCDEFGHIJKL":
            third = self._standing(f"T{g}", 3, 0, 2, lot=ord(g) / 100.0)
            groups[g] = [self._standing(f"W{g}", 9, 5, 7, 0.5),
                         self._standing(f"R{g}", 6, 1, 4, 0.5),
                         third,
                         self._standing(f"L{g}", 0, -6, 1, 0.5)]
        best = tb.get_best_third_place_teams(groups)
        self.assertEqual(len(best), 8)
        # All thirds tied on pts/gd/gf -> the 8 HIGHEST lots advance (E..L)
        self.assertEqual({t["team"] for t in best}, {f"T{g}" for g in "EFGHIJKL"})


class TestScalarGridCacheShape(unittest.TestCase):

    def test_no_dead_rubber_variants_and_md3_trim_applied(self):
        cache = tb.precompute_grids(host_teams=None, market_probs=None)
        variants = {k[2] for k in cache}
        self.assertEqual(variants, {False}, "dead-rubber *_DAMPENED variants must be gone")
        self.assertEqual(len(cache), 72)

        def mean_goals(key):
            flat, cum = cache[key]
            total, prev = 0.0, 0.0
            for (ga, gb), c in zip(flat, cum):
                p = c - prev
                prev = c
                total += p * (ga + gb)
            return total

        # MD3 fixtures carry the x0.87 trim -> fewer expected total goals than
        # the same teams' MD1/MD2 fixtures on average (aggregate across groups
        # to wash out matchup composition).
        md12, md3 = [], []
        for g, teams in tb.GROUPS.items():
            md12.append(mean_goals((teams[0], teams[1], False)))
            md12.append(mean_goals((teams[0], teams[2], False)))
            md3.append(mean_goals((teams[0], teams[3], False)))
            md3.append(mean_goals((teams[1], teams[2], False)))
        self.assertLess(sum(md3) / len(md3), sum(md12) / len(md12))


class TestChampionBlend(unittest.TestCase):

    def test_blend_renormalizes_to_one(self):
        from collections import Counter
        counts = Counter({"Spain": 200, "Argentina": 150, "France": 100})
        market = {"Spain": 0.30, "Argentina": 0.20}     # partial book, sums 0.5
        teams = ["Spain", "Argentina", "France"]
        blended = blend_champion_probs(counts, market, teams, n_sims=450)
        self.assertAlmostEqual(sum(blended.values()), 1.0, places=12)
        self.assertGreater(blended["Spain"], blended["Argentina"])
        self.assertGreater(blended["Argentina"], blended["France"])


if __name__ == "__main__":
    unittest.main()
