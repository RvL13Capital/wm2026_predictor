"""Live-state validator tests (plan step S18)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.live_state import validate_live_state

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class TestValidateLiveState(unittest.TestCase):

    def test_valid_entries(self):
        errors, warnings = validate_live_state({
            "Mexico vs South Africa": [2, 0],
            "Spain vs Cape Verde": [3, 0],
            "M73": [2, 1],
            "M104": [5, 3],       # shootout-inflated final score (G1 convention)
        })
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_unknown_team_is_error_not_silent(self):
        errors, _ = validate_live_state({"Atlantis vs Qatar": [1, 0]})
        self.assertEqual(len(errors), 1)
        self.assertIn("Atlantis", errors[0])
        self.assertIn("silent", errors[0])

    def test_non_canonical_spelling_warns_with_rewrite(self):
        errors, warnings = validate_live_state({"Deutschland vs Ecuador": [2, 1]})
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("Germany vs Ecuador", warnings[0])

    def test_ko_draw_and_bad_ids_rejected(self):
        errors, _ = validate_live_state({
            "M89": [1, 1],          # KO draw — bracket needs a winner
            "M72": [1, 0],          # outside the bracket
            "M999": [1, 0],
        })
        self.assertEqual(len(errors), 3)

    def test_malformed_values_rejected(self):
        bad = {"Mexico vs South Africa": [2],          # wrong arity
               "Spain vs Cape Verde": ["3", 0],         # non-int
               "France vs Senegal": [1, True],          # bool is not goals
               "England vs Croatia": [1, 99]}           # out of range
        errors, _ = validate_live_state(bad)
        self.assertEqual(len(errors), 4)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            good = os.path.join(td, "good.json")
            bad = os.path.join(td, "bad.json")
            json.dump({"Mexico vs South Africa": [2, 0]}, open(good, "w"))
            json.dump({"Atlantis vs Qatar": [1, 0]}, open(bad, "w"))
            script = os.path.join(REPO, "scripts", "validate_live_state.py")
            self.assertEqual(subprocess.run(
                [sys.executable, script, good], cwd=REPO,
                capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(
                [sys.executable, script, bad], cwd=REPO,
                capture_output=True).returncode, 1)
            self.assertEqual(subprocess.run(
                [sys.executable, script, os.path.join(td, "missing.json")],
                cwd=REPO, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
