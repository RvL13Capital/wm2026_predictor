"""Offline tests for scripts/prematch_alert.py (no network).

Covers: FIFA->engine name resolution over the committed schedule, the
group-MD locator vs tbf.GROUPS, the alert window, state-file roundtrip,
KO-phase mapping and message assembly/length.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import predictor                      # noqa: E402
import tournament_bonusfragen as tbf  # noqa: E402
from scripts import prematch_alert as pa  # noqa: E402

SCHEDULE = os.path.join(ROOT, "data", "match_schedule_2026.json")


class TestNameResolution(unittest.TestCase):
    def test_every_scheduled_team_resolves_to_engine_name(self):
        with open(SCHEDULE) as f:
            sched = json.load(f)
        unresolved = set()
        for m in sched:
            for side in ("home", "away"):
                name = m.get(side)
                if not name:
                    continue   # KO placeholder
                if pa.engine_name(name) not in predictor.WORLD_CUP_2026_TEAMS:
                    unresolved.add(name)
        self.assertEqual(unresolved, set(),
                         f"FIFA names without engine mapping: {sorted(unresolved)}")

    def test_alias_spellings(self):
        self.assertEqual(pa.engine_name("Bosnia and Herzegovina"), "Bosnia")
        self.assertEqual(pa.engine_name("Korea Republic"), "South Korea")
        self.assertEqual(pa.engine_name("Türkiye"), "Turkey")
        self.assertEqual(pa.engine_name("Côte d'Ivoire"), "Ivory Coast")
        self.assertEqual(pa.engine_name("Congo DR"), "DR Congo")
        self.assertEqual(pa.engine_name("Cabo Verde"), "Cape Verde")
        self.assertEqual(pa.engine_name("IR Iran"), "Iran")


class TestGroupMdLocator(unittest.TestCase):
    def test_every_group_fixture_in_schedule_is_located(self):
        with open(SCHEDULE) as f:
            sched = json.load(f)
        group_fixtures = [m for m in sched if m.get("home") and m.get("away")
                          and (m.get("group") or "").startswith("Group")]
        self.assertEqual(len(group_fixtures), 72)
        for m in group_fixtures:
            a, b = pa.engine_name(m["home"]), pa.engine_name(m["away"])
            got = pa.find_group_md(a, b)
            self.assertIsNotNone(got, f"no MD found for {a} vs {b}")

    def test_md_assignment_mirrors_matchday_tips_formula(self):
        # the locator must use exactly the run_matchday matchup formulas
        for group, teams in tbf.GROUPS.items():
            expect = {
                1: [(teams[0], teams[1]), (teams[2], teams[3])],
                2: [(teams[0], teams[2]), (teams[1], teams[3])],
                3: [(teams[0], teams[3]), (teams[1], teams[2])],
            }
            for md, matchups in expect.items():
                for a, b in matchups:
                    got = pa.find_group_md(a, b)
                    self.assertEqual((got[0], got[1]), (md, group))
                    # reversed orientation must resolve identically
                    got_rev = pa.find_group_md(b, a)
                    self.assertEqual(got_rev[2], (a, b))

    def test_canada_bosnia_is_md1_group_b(self):
        md, group, pair = pa.find_group_md("Canada", "Bosnia")
        self.assertEqual((md, group), (1, "B"))


class TestWindowAndState(unittest.TestCase):
    def _mk(self, mins_from_now, mid="m1"):
        now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        ko = now.timestamp() + mins_from_now * 60
        utc = datetime.fromtimestamp(ko, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return now, {"id": mid, "stage_id": "s", "stage": "First stage",
                     "group": "Group A", "utc": utc, "home": "Mexico", "away": "Canada"}

    def test_window_includes_only_lead_interval(self):
        now, m_in = self._mk(30)
        _, m_far = self._mk(60, "m2")
        _, m_past = self._mk(-5, "m3")
        _, m_edge = self._mk(35, "m4")
        due = pa.due_matches([m_in, m_far, m_past, m_edge], lead_min=35, now=now)
        self.assertEqual({m["id"] for m in due}, {"m1", "m4"})

    def test_ko_placeholders_are_skipped(self):
        now, _ = self._mk(30)
        placeholder = {"id": "ko", "utc": "2026-06-15T12:30:00Z",
                       "home": None, "away": None}
        self.assertEqual(pa.due_matches([placeholder], 35, now=now), [])

    def test_state_roundtrip_and_corrupt_state(self):
        with tempfile.TemporaryDirectory() as td:
            orig = pa.STATE_PATH
            pa.STATE_PATH = os.path.join(td, "state.json")
            try:
                self.assertEqual(pa.load_state(), {})
                pa.save_state({"400021449": "2026-06-12T18:27:31+00:00"})
                self.assertIn("400021449", pa.load_state())
                with open(pa.STATE_PATH, "w") as f:
                    f.write("{corrupt")
                self.assertEqual(pa.load_state(), {})   # re-baseline, never raise
            finally:
                pa.STATE_PATH = orig


class TestKoRowParity(unittest.TestCase):
    def test_ko_row_applies_xg_form_multipliers_like_ko_tips(self):
        # the quick path must mirror ko_tips.run_ko_round's row: phase +
        # compute_xg_form_multipliers (dead-legs is the one documented omission)
        row = pa.build_ko_row("Spain", "Croatia", "QF", snapshot_path=None)
        form_a, form_b = tbf.compute_xg_form_multipliers("Spain", "Croatia")
        self.assertEqual(row["phase"], "QF")
        self.assertEqual(row["form_a"], str(form_a))
        self.assertEqual(row["form_b"], str(form_b))
        self.assertNotIn("odds_home", row)   # no snapshot -> Elo-only

    def test_ko_message_discloses_quick_path(self):
        grid = {1: {0: 1.0}}
        tip_row = {"team_a": "Spain", "team_b": "Croatia", "grid": grid,
                   "optimal_tip": (2, 1), "ev": 1.2, "top_tips": [], "mc": None,
                   "note": "KO quick path: no fatigue flags — ko_tips sheet authoritative"}
        match = {"utc": "2026-07-04T19:00:00Z", "stage": "Quarter-finals", "group": ""}
        msg = pa.build_message(match, "Spain", "Croatia", tip_row, None, None)
        self.assertIn("KO quick path", msg)


class TestKoPhaseAndFormatting(unittest.TestCase):
    def test_ko_phase_mapping(self):
        self.assertEqual(pa.ko_phase("Round of 32"), "R32")
        self.assertEqual(pa.ko_phase("Round of 16"), "R16")
        self.assertEqual(pa.ko_phase("Quarter-finals"), "QF")
        self.assertEqual(pa.ko_phase("Semi-finals"), "SF")
        self.assertEqual(pa.ko_phase("Final"), "FINAL")
        self.assertIsNone(pa.ko_phase("First stage"))

    def test_surname(self):
        self.assertEqual(pa._surname("Maxime CREPEAU"), "Crepeau")
        self.assertEqual(pa._surname("Luc DE FOUGEROLLES"), "De Fougerolles")
        self.assertEqual(pa._surname("Dayne ST. CLAIR"), "St. Clair")

    def test_build_message_fits_callmebot_limit(self):
        grid = {1: {0: 0.6}, 0: {0: 0.25, 1: 0.15}}
        tip_row = {"team_a": "Canada", "team_b": "Bosnia", "grid": grid,
                   "optimal_tip": (1, 0), "ev": 1.664,
                   "top_tips": [{"tip": "1:0", "ev": 1.664}, {"tip": "2:1", "ev": 1.601}],
                   "mc": {"mean": 1.66, "std": 1.4, "p0": 0.37, "p2": 0.37,
                          "p3": 0.12, "p4": 0.14}}
        lineups_by_team = {
            "Canada": {"xi": [f"First LASTNAME{i}" for i in range(11)],
                       "bench": [], "formation": "4-4-2"},
            "Bosnia": {"xi": [f"First VERYLONGSURNAME{i}" for i in range(11)],
                       "bench": [], "formation": "4-3-3"}}
        match = {"utc": "2026-06-12T19:00:00Z", "group": "Group B", "stage": "First stage"}
        msg = pa.build_message(match, "Canada", "Bosnia", tip_row, lineups_by_team,
                               snapshot_path=None)
        self.assertIn("TIPP  1:0", msg)
        self.assertIn("STARK", msg)
        self.assertIn("Canada (4-4-2):", msg)
        self.assertLess(len(msg), 1500)

    def test_build_message_orientation_follows_caller_not_fifa(self):
        # the tip orientation (team_a/team_b) drives header + XI labelling;
        # XI blocks are matched BY NAME so a FIFA home/away flip cannot
        # attribute a lineup to the wrong team
        grid = {0: {1: 0.7}, 1: {1: 0.3}}
        tip_row = {"team_a": "Bosnia", "team_b": "Canada", "grid": grid,
                   "optimal_tip": (0, 1), "ev": 1.5, "top_tips": [], "mc": None}
        lineups_by_team = {
            "Canada": {"xi": ["A CANGUY"] * 11, "bench": [], "formation": "4-4-2"},
            "Bosnia": {"xi": ["A BIHGUY"] * 11, "bench": [], "formation": "3-5-2"}}
        match = {"utc": "2026-06-12T19:00:00Z", "group": "Group B"}
        msg = pa.build_message(match, "Bosnia", "Canada", tip_row, lineups_by_team,
                               snapshot_path=None)
        self.assertIn("Bosnia vs Canada", msg.splitlines()[0])
        xi_lines = [l for l in msg.splitlines() if "):" in l and ("Bihguy" in l or "Canguy" in l)]
        self.assertIn("Bihguy", xi_lines[0])      # first lineup line = team_a = Bosnia
        self.assertIn("Bosnia (3-5-2)", xi_lines[0])
        self.assertIn("Canguy", xi_lines[1])
        self.assertIn("Canada (4-4-2)", xi_lines[1])

    def test_build_message_without_tip_or_lineups_still_warns(self):
        match = {"utc": "2026-06-12T19:00:00Z", "group": "Group B"}
        msg = pa.build_message(match, "Canada", "Bosnia", None, None, None)
        self.assertIn("kein Tipp berechnet", msg)
        self.assertIn("noch nicht veröffentlicht", msg)


if __name__ == "__main__":
    unittest.main()
