"""KO tip generator tests (plan step S19)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import predictor
import ko_tips

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class TestKoTips(unittest.TestCase):

    def test_basic_round_under_pool_convention(self):
        results = ko_tips.run_ko_round(
            "QF", [{"team_a": "Croatia", "team_b": "Brazil"}],
            n_simulations=50, seed=7)
        self.assertEqual(len(results), 1)
        res = results[0]
        # Gate G1: tips target the shootout_total outcome space (no draws)
        self.assertEqual(res["ko_convention"], "shootout_total")
        self.assertEqual(res["p_draw"], 0.0)
        self.assertGreater(res["ev"], 0.0)
        t_a, t_b = res["optimal_tip"]
        self.assertNotEqual(t_a, t_b, "a draw tip can never be optimal in a no-draw outcome space")
        self.assertIsNotNone(res["mc"])

    def test_dead_legs_fatigue_moves_lambdas(self):
        fresh = ko_tips.run_ko_round(
            "R16", [{"team_a": "Croatia", "team_b": "Brazil"}], 0, 7)[0]
        tired = ko_tips.run_ko_round(
            "R16", [{"team_a": "Croatia", "team_b": "Brazil"}], 0, 7,
            fatigued=["Croatia"])[0]
        # Fatigued Croatia: their attack drops, Brazil's expected goals rise.
        self.assertLess(tired["lambda_adj_a"], fresh["lambda_adj_a"])
        self.assertGreater(tired["lambda_adj_b"], fresh["lambda_adj_b"])
        self.assertTrue(any("dead legs" in f.lower() for f in tired["flags"]))

    def test_determinism_per_seed(self):
        a = ko_tips.run_ko_round("SF", [{"team_a": "Spain", "team_b": "France"}], 200, 11)[0]
        b = ko_tips.run_ko_round("SF", [{"team_a": "Spain", "team_b": "France"}], 200, 11)[0]
        self.assertEqual(a["optimal_tip"], b["optimal_tip"])
        self.assertEqual(a["mc"], b["mc"])

    def test_inline_matches_parser(self):
        class Args:
            fixtures = None
            matches = "Spain vs Uruguay; France vs Germany"
        fx = ko_tips.parse_fixtures(Args)
        self.assertEqual(fx, [{"team_a": "Spain", "team_b": "Uruguay"},
                              {"team_a": "France", "team_b": "Germany"}])

    def test_output_parses_into_prediction_log(self):
        """End-to-end ops guarantee: ko_tips output → log_predictions --kind ko."""
        out = subprocess.check_output(
            [sys.executable, os.path.join(REPO, "ko_tips.py"),
             "--round", "R32", "--matches", "England vs Senegal",
             "--simulations", "20", "--seed", "3"],
            cwd=REPO, stderr=subprocess.DEVNULL).decode()
        with tempfile.TemporaryDirectory() as td:
            artifact = os.path.join(td, "r32_tips_test.txt")
            log = os.path.join(td, "log.jsonl")
            with open(artifact, "w", encoding="utf-8") as f:
                f.write(out)
            subprocess.check_call(
                [sys.executable, os.path.join(REPO, "scripts", "log_predictions.py"),
                 "--kind", "ko", "--file", artifact, "--log", log, "--allow-dirty"],
                cwd=REPO, stdout=subprocess.DEVNULL)
            with open(log, encoding="utf-8") as f:
                entry = json.loads(f.readline())
            self.assertEqual(entry["kind"], "ko")
            self.assertEqual(len(entry["matches"]), 1)
            self.assertEqual(entry["matches"][0]["team_a"], "England")
            self.assertEqual(entry["matches"][0]["phase"], "R32")
            self.assertIn("tip", entry["matches"][0])


if __name__ == "__main__":
    unittest.main()
