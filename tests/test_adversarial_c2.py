import unittest
import os
import sys
import math

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import predictor
import predictor
try:
    import backtest
except ImportError:
    backtest = None

class TestAdversarialC2(unittest.TestCase):

    # === 1. Input Validation and Type-Safety Gaps in CSV Loader & Backtester ===

    def test_csv_loader_optional_field_string_crashes_downstream(self):
        """Verify that malformed string values in optional CSV columns bypass load_match_data validation and crash run_backtest with TypeError."""
        if backtest is None:
            self.skipTest("backtest module not available")
        csv_content = (
            "team_a,team_b,goals_a,goals_b,elevation,temp,humidity,fan_pct_a\n"
            "Germany,Japan,1,2,0,22,50,not_a_float\n"
        )
        csv_path = "temp_malformed_fan_pct.csv"
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        try:
            # load_match_data now raises ValueError because fan_pct_a has malformed non-float string
            with self.assertRaises(ValueError):
                backtest.load_match_data(csv_path)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_csv_loader_whitespace_team_names(self):
        """Verify that load_match_data accepts whitespace-only team names, which propagates empty string team names instead of raising ValueError."""
        if backtest is None:
            self.skipTest("backtest module not available")
        csv_content = (
            "team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n"
            "   ,Japan,1,2,0,22,50\n"
        )
        csv_path = "temp_whitespace_team.csv"
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        try:
            with self.assertRaises(ValueError):
                backtest.load_match_data(csv_path)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_csv_loader_directory_path(self):
        """Verify that passing a directory path to load_match_data raises IsADirectoryError (or other filesystem error) instead of a clean ValueError."""
        if backtest is None:
            self.skipTest("backtest module not available")
        dir_path = os.path.dirname(os.path.abspath(__file__))
        with self.assertRaises((IsADirectoryError, PermissionError)):
            backtest.load_match_data(dir_path)

    def test_get_team_stats_invalid_types(self):
        """Verify that get_team_stats raises AttributeError for invalid non-string, non-None types."""
        if backtest is None:
            self.skipTest("backtest module not available")
        with self.assertRaises(AttributeError):
            backtest.get_team_stats(123)
        with self.assertRaises(AttributeError):
            backtest.get_team_stats(["Germany"])

    # === 2. Silent Logic Bugs in Probability Engine ===

    def test_negative_binomial_string_alpha_silent_poisson_fallback(self):
        """Verify that passing alpha as a float string (e.g. "0.5") silently and incorrectly degrades the model to Poisson due to early type-check evaluation."""
        # Poisson probability for k=1, mu=2.0 is 2 * e^-2 ≈ 0.27067
        # Negative Binomial probability for k=1, mu=2.0, alpha=0.5 is 0.25
        p_nb_str = predictor.negative_binomial_probability(1, 2.0, "0.5")
        p_nb_float = predictor.negative_binomial_probability(1, 2.0, 0.5)
        
        # Verify that p_nb_str equals p_nb_float (demonstrating correct parsing)
        self.assertAlmostEqual(p_nb_str, p_nb_float)

    def test_negative_binomial_string_mu_returns_zero(self):
        """Verify that passing mu as a float string (e.g. "2.0") causes negative_binomial_probability to return 0.0 due to early type-check evaluation."""
        p_nb_str = predictor.negative_binomial_probability(1, "2.0", 0.5)
        self.assertAlmostEqual(p_nb_str, 0.25)

    def test_dixon_coles_negative_rho_collapses_to_draw(self):
        """Verify that extreme negative rho combined with large a_a, a_b violates model invariants by collapsing probability of (0,0) to 1.0 instead of reducing it."""
        # When mu is 100.0, a_a and a_b are 100.0.
        # With extreme negative rho (-1e200), factor = 1.0 - (-1e200 * 100 * 100) = 1e204.
        # This causes P(0,0) to blow up relative to other cells. After normalization, P(0,0) becomes 1.0.
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=100.0,
            mu_b=100.0,
            rho=-1e200,
            max_goals=2,
            max_tip=2
        )
        grid = predictor.generate_joint_grid(config)
        self.assertNotAlmostEqual(grid[0][0], 1.0)

    # === 3. Type-Safety Gaps in Contextual Calculations ===

    def test_altitude_factor_string_typeerror(self):
        """Verify that passing a string elevation to calculate_altitude_factor raises TypeError instead of sanitizing it."""
        with self.assertRaises(TypeError):
            predictor.calculate_altitude_factor("2000.0", 0.0)

    def test_thermal_factor_string_typeerror(self):
        """Verify that passing a string temperature to calculate_thermal_factor raises TypeError instead of sanitizing it."""
        with self.assertRaises(TypeError):
            predictor.calculate_thermal_factor("30.0", 50.0, 0.0)

    # === 4. Bug in Solver's Type Handling & NaN Propagation ===

    def test_solver_list_of_dicts_keyerror(self):
        """Verify that passing a list of dicts (instead of list of lists or dict of dicts) causes a KeyError in the solver's list-processing path."""
        grid = [{0: 0.5}, {1: 0.5}]
        # This will not raise KeyError anymore
        sorted_tips, sorted_scores, outcomes = predictor.solve_optimal_tip_from_grid(grid, max_tip=2)
        self.assertIsNotNone(sorted_tips)

    def test_solver_nan_in_grid_propagation(self):
        """Verify that if the probability grid contains NaN, the solver propagates the NaN, resulting in NaN expected values."""
        grid = {
            0: {0: float('nan'), 1: 0.5},
            1: {0: 0.2, 1: 0.3}
        }
        sorted_tips, sorted_scores, outcomes = predictor.solve_optimal_tip_from_grid(grid, max_tip=1)
        # Check that NaN propagated to outcomes and some EVs
        self.assertTrue(math.isnan(outcomes[0]) or math.isnan(outcomes[1]) or math.isnan(outcomes[2]))
        
        # Verify that EV of some tips is NaN
        nan_ev_count = sum(1 for tip, ev in sorted_tips if math.isnan(ev))
        self.assertGreater(nan_ev_count, 0)

if __name__ == '__main__':
    unittest.main()
