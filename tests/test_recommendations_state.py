"""Recommendation change-detection tests — offline, temp state files only.

Pins the alerting contract of utils/recommendations_state.py: first run
baselines silently, only value CHANGES on existing keys alert, scopes are
merge-updated (partial KO re-runs keep untouched baselines), the two
tournament engines never share a scope, and a corrupt state file degrades to
re-baselining instead of crashing a tip run.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import recommendations_state as rs


class TestDiffAndUpdate(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)                     # start with no state file

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_first_run_baselines_silently(self):
        changes = rs.diff_and_update("MD1", {"Spain vs Cape Verde": "3:0"}, self.path)
        self.assertEqual(changes, [])
        self.assertEqual(json.load(open(self.path))["MD1"]["Spain vs Cape Verde"], "3:0")

    def test_value_change_alerts_with_old_and_new(self):
        rs.diff_and_update("MD1", {"Brazil vs Morocco": "0:0"}, self.path)
        changes = rs.diff_and_update("MD1", {"Brazil vs Morocco": "1:0"}, self.path)
        self.assertEqual(changes, [("Brazil vs Morocco", "0:0", "1:0")])
        # and the new value is now the baseline
        self.assertEqual(rs.diff_and_update("MD1", {"Brazil vs Morocco": "1:0"}, self.path), [])

    def test_new_keys_are_silent_and_scopes_merge(self):
        rs.diff_and_update("KO-R32", {"Spain vs Uruguay": "2:0"}, self.path)
        # partial re-run with a different match: no alert, old baseline kept
        changes = rs.diff_and_update("KO-R32", {"France vs Germany": "1:1"}, self.path)
        self.assertEqual(changes, [])
        state = json.load(open(self.path))["KO-R32"]
        self.assertEqual(state, {"Spain vs Uruguay": "2:0", "France vs Germany": "1:1"})

    def test_scopes_are_independent(self):
        rs.diff_and_update("bonusfragen:scalar", {"Weltmeister": "Spain"}, self.path)
        changes = rs.diff_and_update("bonusfragen:vectorized", {"Weltmeister": "Argentina"}, self.path)
        self.assertEqual(changes, [])            # different scope, no cross-talk

    def test_corrupt_state_rebaselines_without_raising(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        changes = rs.diff_and_update("MD1", {"Spain vs Cape Verde": "3:0"}, self.path)
        self.assertEqual(changes, [])
        self.assertEqual(json.load(open(self.path))["MD1"]["Spain vs Cape Verde"], "3:0")

    def test_env_var_overrides_default_path(self):
        with mock.patch.dict(os.environ, {rs.STATE_PATH_ENV: self.path}):
            rs.diff_and_update("MD2", {"X vs Y": "1:0"})
        self.assertEqual(json.load(open(self.path))["MD2"]["X vs Y"], "1:0")


class TestBonusfragenExtractor(unittest.TestCase):
    def test_flattens_engine_results_with_sorted_sf(self):
        results = {
            "champion": {"tip": "Spain", "probability": 0.187},
            "semifinalists": {"tips": ["Spain", "France", "Argentina", "England"]},
            "top_scorer_team": {"tip": "France"},
            "group_winners": {"A": {"tip": "Mexico"}, "H": {"tip": "Spain"}},
        }
        recs = rs.bonusfragen_recommendations(results)
        self.assertEqual(recs["Weltmeister"], "Spain")
        self.assertEqual(recs["Halbfinale"], "Argentina, England, France, Spain")  # sorted = order-stable
        self.assertEqual(recs["Torschützen-Team"], "France")
        self.assertEqual(recs["Gruppensieger A"], "Mexico")
        self.assertEqual(recs["Gruppensieger H"], "Spain")

    def test_partial_results_tolerated(self):
        self.assertEqual(rs.bonusfragen_recommendations({}), {})


class TestAlerting(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_message_format(self):
        msg = rs.format_changes_message("MD1", [("Brazil vs Morocco", "0:0", "1:0")])
        self.assertIn("MD1", msg)
        self.assertIn("Brazil vs Morocco: 0:0 → 1:0", msg)
        self.assertEqual(rs.format_changes_message("MD1", []), "")

    def test_message_caps_items(self):
        changes = [(f"M{i}", "0:0", "1:0") for i in range(12)]
        msg = rs.format_changes_message("MD1", changes, max_items=8)
        self.assertIn("… +4 more", msg)

    def test_alert_on_changes_pushes_only_on_change(self):
        with mock.patch("utils.notify.send_whatsapp", return_value=True) as m:
            rs.alert_on_changes("MD1", {"A vs B": "1:0"}, self.path)   # baseline
            m.assert_not_called()
            rs.alert_on_changes("MD1", {"A vs B": "1:0"}, self.path)   # unchanged
            m.assert_not_called()
            changes = rs.alert_on_changes("MD1", {"A vs B": "2:0"}, self.path)
            self.assertEqual(changes, [("A vs B", "1:0", "2:0")])
            m.assert_called_once()
            self.assertIn("A vs B: 1:0 → 2:0", m.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
