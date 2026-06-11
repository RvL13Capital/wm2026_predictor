import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import predictor
import matchday_tips
import tournament_bonusfragen as tbf


class TestEloOverrideRestoration(unittest.TestCase):
    """The global Elo table must survive exceptions inside the override scope.

    Regression guard for the forensic-audit finding (W7 follow-up): the old
    mutate -> predict -> restore sequence had no try/finally, so one raising
    match corrupted the ratings for every subsequent match in the run.
    """

    def test_applies_adjustments_inside_scope(self):
        team_a, team_b = "Spain", "Qatar"
        orig_a = predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"]
        orig_b = predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"]
        squad_adj = {team_a: 10.0, team_b: -5.0}

        with matchday_tips._elo_overrides(team_a, team_b, squad_adj):
            expected_a = orig_a + 10.0 + tbf.INJURY_ELO_ADJUSTMENTS.get(team_a, 0.0)
            expected_b = orig_b - 5.0 + tbf.INJURY_ELO_ADJUSTMENTS.get(team_b, 0.0)
            self.assertEqual(predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"], expected_a)
            self.assertEqual(predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"], expected_b)

        self.assertEqual(predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"], orig_a)
        self.assertEqual(predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"], orig_b)

    def test_restores_on_exception(self):
        team_a, team_b = "Mexico", "Qatar"
        orig_a = predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"]
        orig_b = predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"]

        with self.assertRaises(RuntimeError):
            with matchday_tips._elo_overrides(team_a, team_b, {team_a: 50.0}):
                raise RuntimeError("prediction blew up")

        self.assertEqual(predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"], orig_a)
        self.assertEqual(predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"], orig_b)

    def test_unknown_team_is_a_noop(self):
        snapshot = {t: d["elo"] for t, d in predictor.WORLD_CUP_2026_TEAMS.items()}
        with matchday_tips._elo_overrides("Atlantis", "Mu", {"Atlantis": 100.0}):
            pass
        for t, elo in snapshot.items():
            self.assertEqual(predictor.WORLD_CUP_2026_TEAMS[t]["elo"], elo)


if __name__ == "__main__":
    unittest.main()
