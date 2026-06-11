"""Scoreboard tests (S20/S21 early slice): tips from the prediction log scored
against live_state-style results, incl. orientation swap, the Tordifferenz
draw rule, and pending handling."""
import importlib.util
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
spec = importlib.util.spec_from_file_location(
    "score_predictions", os.path.join(REPO, "scripts", "score_predictions.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


ENTRY = {"kind": "matchday", "matches": [
    {"team_a": "Mexico", "team_b": "South Africa", "tip": "2:0", "ev": 2.09},
    {"team_a": "South Korea", "team_b": "Czechia", "tip": "0:0", "ev": 1.28},
    {"team_a": "Qatar", "team_b": "Switzerland", "tip": "0:2", "ev": 2.21},
    {"team_a": "Canada", "team_b": "Bosnia", "tip": "1:0", "ev": 1.76},
]}


class TestScoreEntry(unittest.TestCase):

    def test_points_orientation_and_draw_rule(self):
        results = sp.build_results_index({
            "Mexico vs South Africa": [2, 0],          # exact -> 4
            "Tschechien vs Südkorea": [1, 1],          # swapped + German + non-exact draw -> 3 (Tordifferenz)
            "Qatar vs Switzerland": [1, 3],            # tendency only -> 2
        })
        s = sp.score_entry(ENTRY, results)
        pts = [p for (_m, res, p) in s["rows"] if res is not None]
        self.assertEqual(pts, [4, 3, 2])
        self.assertEqual(s["points"], 9)
        self.assertEqual(s["n_scored"], 3)
        self.assertEqual(s["pending"], 1)               # Canada vs Bosnia unplayed
        # EV expectation accumulates ONLY over the scored subset
        self.assertAlmostEqual(s["ev_scored"], 2.09 + 1.28 + 2.21, places=9)

    def test_zero_points_and_empty_results(self):
        results = sp.build_results_index({"Mexico vs South Africa": [0, 1]})  # wrong tendency
        s = sp.score_entry(ENTRY, results)
        self.assertEqual(s["points"], 0)
        s_empty = sp.score_entry(ENTRY, sp.build_results_index({}))
        self.assertEqual((s_empty["n_scored"], s_empty["pending"]), (0, 4))


if __name__ == "__main__":
    unittest.main()
