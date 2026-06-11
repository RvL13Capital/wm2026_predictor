"""KO scoring-convention tests (plan step S12, gate G1).

The pool scores knockout games "inkl. Elfmeterschießen" (shootout_total) —
verified 2026-06-10, validation/POOL_RULES.md. These tests pin:

  * shootout_total (default): the 3-layer no-draw grid is the tipping target,
    byte-identical to the pre-S12 library behavior;
  * 120min: draws are real scored outcomes (a shootout game = the ET draw),
    per-side goals capped at 90' + ET — no shootout inflation;
  * 90min: KO tips equal the group-style solve on the phase-adjusted grid;
  * the CLI and the library produce the SAME KO answer (the historical
    split-brain: the CLI used to solve KO tips on the 90-minute grid);
  * load_config preserves the convention's string type.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import predictor
from predictor import (
    CONSTANTS, MatchModelConfig, ModelDistribution,
    generate_ko_120_grid, generate_ko_final_grid, get_grid_val,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ROW = {"team_a": "Croatia", "team_b": "Brazil", "phase": "QF"}


def _draw_mass(grid, n=16):
    return sum(get_grid_val(grid, d, d) for d in range(n))


class _ConventionBase(unittest.TestCase):
    def setUp(self):
        self._saved = CONSTANTS.get("kicktipp_ko_convention")

    def tearDown(self):
        CONSTANTS["kicktipp_ko_convention"] = self._saved


class TestShootoutTotalDefault(_ConventionBase):

    def test_default_convention_is_shootout_total(self):
        self.assertEqual(predictor.DEFAULT_CONSTANTS["kicktipp_ko_convention"], "shootout_total")

    def test_ko_grid_has_no_draws_and_pen_inflation(self):
        CONSTANTS["kicktipp_ko_convention"] = "shootout_total"
        res = predictor.predict_single_match(dict(ROW))
        self.assertEqual(res["ko_convention"], "shootout_total")
        self.assertTrue(res["is_ko_model"])
        self.assertEqual(res["p_draw"], 0.0)
        self.assertAlmostEqual(_draw_mass(res["grid"]), 0.0, places=12)
        # Shootout inflation exists: some mass beyond 90'+ET reach (>4 goal margin
        # at high totals is shootout-only territory for this matchup).
        high = sum(get_grid_val(res["grid"], a, b)
                   for a in range(16) for b in range(16) if a + b >= 9)
        self.assertGreater(high, 0.0)


class TestConvention120min(_ConventionBase):

    def test_draws_are_real_outcomes(self):
        CONSTANTS["kicktipp_ko_convention"] = "120min"
        res = predictor.predict_single_match(dict(ROW))
        self.assertEqual(res["ko_convention"], "120min")
        # A close QF goes level after ET in a sizeable share of cases.
        self.assertGreater(res["p_draw"], 0.05)
        self.assertLess(res["p_draw"], 0.45)
        # generate_ko_120_grid renormalizes only when truncation loss exceeds
        # 0.001 (same tolerance as generate_ko_final_grid) — assert within it.
        self.assertAlmostEqual(res["p_home"] + res["p_draw"] + res["p_away"], 1.0, delta=0.002)

    def test_no_shootout_goals_in_grid(self):
        cfg = MatchModelConfig(
            dist_type=ModelDistribution.POISSON,
            mu_a=1.0, mu_b=1.0, rho=-0.08, max_goals=8, phase=predictor.MatchPhase.QUARTER)
        g120 = generate_ko_120_grid(cfg, max_final_goals=15)
        # Per-side goals are capped at 90' max (8) + ET max (4) = 12.
        beyond = sum(g120[a][b] for a in range(16) for b in range(16) if a > 12 or b > 12)
        self.assertEqual(beyond, 0.0)
        total = sum(g120[a][b] for a in range(16) for b in range(16))
        self.assertAlmostEqual(total, 1.0, places=3)
        # Draw mass equals P(draw at 90') * P(ET level) > 0
        self.assertGreater(_draw_mass(g120), 0.05)


class TestConvention90min(_ConventionBase):

    def test_equals_group_style_solve_on_phase_adjusted_grid(self):
        CONSTANTS["kicktipp_ko_convention"] = "90min"
        res = predictor.predict_single_match(dict(ROW))
        self.assertEqual(res["ko_convention"], "90min")
        self.assertFalse(res["is_ko_model"])
        # The tipping grid IS the phase-adjusted 90-minute grid.
        self.assertEqual(res["grid"], res["grid_90"])
        self.assertGreater(res["p_draw"], 0.05)


class TestCliLibraryUnification(_ConventionBase):

    def test_cli_matches_library_for_ko_match(self):
        """The CLI must produce the library's KO answer (default convention)."""
        out = subprocess.check_output(
            [sys.executable, os.path.join(REPO, "predictor.py"),
             "--teamA", "Croatia", "--teamB", "Brazil", "--phase", "QF", "--json"],
            cwd=REPO, stderr=subprocess.DEVNULL).decode()
        cli = json.loads(out)
        lib = predictor.predict_single_match(dict(ROW))
        self.assertEqual(cli["optimal_tip"], lib["optimal_tip"])
        self.assertEqual(cli["ko_convention"], "shootout_total")
        self.assertEqual(cli["p_draw"], 0.0)
        self.assertAlmostEqual(cli["p_home"], lib["p_home"], places=6)
        self.assertAlmostEqual(cli["ev"], lib["ev"], places=6)

    def test_cli_manual_lambda_override_still_works(self):
        out = subprocess.check_output(
            [sys.executable, os.path.join(REPO, "predictor.py"),
             "--teamA", "Spain", "--teamB", "Qatar",
             "--lambdaA", "2.0", "--lambdaB", "0.5", "--json"],
            cwd=REPO, stderr=subprocess.DEVNULL).decode()
        cli = json.loads(out)
        self.assertAlmostEqual(cli["lambda_a_base"], 2.0, places=6)
        self.assertAlmostEqual(cli["lambda_b_base"], 0.5, places=6)


class TestLoadConfigTypePreservation(_ConventionBase):

    def test_string_constant_survives_load_config(self):
        saved_constants = dict(CONSTANTS)
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump({"kicktipp_ko_convention": "120min",
                           "elo_baseline_goals": 1.1}, f)
                path = f.name
            predictor.load_config(path)
            self.assertEqual(CONSTANTS["kicktipp_ko_convention"], "120min")
            self.assertIsInstance(CONSTANTS["kicktipp_ko_convention"], str)
            self.assertEqual(CONSTANTS["elo_baseline_goals"], 1.1)
            self.assertIsInstance(CONSTANTS["elo_baseline_goals"], float)
        finally:
            CONSTANTS.clear()
            CONSTANTS.update(saved_constants)
            os.unlink(path)

    def test_repo_config_json_loads_clean(self):
        saved_constants = dict(CONSTANTS)
        try:
            predictor.load_config(os.path.join(REPO, "config.json"))
            self.assertEqual(CONSTANTS["kicktipp_ko_convention"], "shootout_total")
        finally:
            CONSTANTS.clear()
            CONSTANTS.update(saved_constants)


if __name__ == "__main__":
    unittest.main()
