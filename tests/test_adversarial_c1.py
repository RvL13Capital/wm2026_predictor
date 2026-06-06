import unittest
import os
import sys
import math
from io import StringIO

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import predictor
from solver import get_points, solve_optimal_tip_from_grid
import backtest

class TestAdversarialC1(unittest.TestCase):

    # --- 1. Bugs in predictor.py ---

    def test_negative_binomial_string_float_bug(self):
        """
        Gaps & Bugs: negative_binomial_probability evaluates alpha_is_nan using isinstance BEFORE casting.
        If alpha is passed as a string representation of a float like "0.5", alpha_is_nan becomes True,
        and it incorrectly falls back to poisson_probability.
        """
        mu = 2.0
        # For mu=2.0, alpha=0.5, correct NB probability for k=1 is 0.25
        # Poisson probability for k=1 with lam=2.0 is approx 0.27067
        
        # Call with float alpha
        p_float = predictor.negative_binomial_probability(1, mu, 0.5)
        # Call with string representation of the same float
        p_string = predictor.negative_binomial_probability(1, mu, "0.5")
        
        # They should be equal now
        self.assertAlmostEqual(p_float, p_string)

    def test_calculate_altitude_factor_none_crash(self):
        """
        Gaps & Bugs: Direct calls to calculate_altitude_factor with None values cause TypeError
        because math.isnan(None) is evaluated.
        """
        with self.assertRaises(TypeError):
            predictor.calculate_altitude_factor(None, 0.0)
            
        with self.assertRaises(TypeError):
            predictor.calculate_altitude_factor(1500.0, None)

    def test_calculate_wbgt_none_crash(self):
        """
        Gaps & Bugs: Direct calls to calculate_wbgt with None values cause TypeError.
        """
        with self.assertRaises(TypeError):
            predictor.calculate_wbgt(None, 50.0)
            
        with self.assertRaises(TypeError):
            predictor.calculate_wbgt(25.0, None)

    def test_calculate_travel_penalty_none_crash(self):
        """
        Gaps & Bugs: Direct calls to calculate_travel_penalty with None values cause TypeError.
        """
        with self.assertRaises(TypeError):
            predictor.calculate_travel_penalty(None, 1000.0, 2)
            
        with self.assertRaises(TypeError):
            predictor.calculate_travel_penalty(5.0, None, 2)
            
        with self.assertRaises(TypeError):
            predictor.calculate_travel_penalty(5.0, 1000.0, None)

    def test_calculate_context_adjustments_none_crash(self):
        """
        Gaps & Bugs: Direct calls to calculate_context_adjustments with None values cause TypeError.
        """
        with self.assertRaises(TypeError):
            predictor.calculate_context_adjustments("Neutral", "Neutral", None, 0.5, 0.0, 0.0)

    def test_get_adjusted_lambdas_none_crash(self):
        """
        Gaps & Bugs: Passing None for lambda_A_base or lambda_B_base in get_adjusted_lambdas causes TypeError.
        """
        with self.assertRaises(TypeError):
            predictor.get_adjusted_lambdas(None, 1.5, {}, {})
            
        with self.assertRaises(TypeError):
            predictor.get_adjusted_lambdas(1.5, None, {}, {})

    def test_context_status_normalization_failure(self):
        """
        Gaps & Bugs: get_adjusted_lambdas does not normalize the 'status' values in the context dicts.
        If passed as "True_Home" (which is accepted by CLI main parser) or "co-host",
        they fail to match the host_att_map/host_def_map in calculate_context_adjustments
        and are silently treated as "Neutral" (returning 0.0 adjust).
        """
        # Baseline with Neutral status
        ctx_neut = {"status": "Neutral", "fan_support_pct": 0.5}
        lam_neut, _ = predictor.get_adjusted_lambdas(1.5, 1.5, ctx_neut, ctx_neut)
        
        # Context with True_Home (normalized)
        ctx_true_home = {"status": "True_Home", "fan_support_pct": 0.5}
        lam_true_home, _ = predictor.get_adjusted_lambdas(1.5, 1.5, ctx_true_home, ctx_neut)
        
        # Since status "True_Home" is normalized to "True Home", host advantage is applied,
        # so the lambdas should be different from Neutral.
        self.assertNotEqual(lam_neut, lam_true_home)

    def test_solve_optimal_tip_unsanitized_config(self):
        """
        Gaps & Bugs: solve_optimal_tip does not sanitize/clamp mu_a or mu_b when config is a MatchModelConfig.
        If a caller passes MatchModelConfig with mu_a=None, it crashes in generate_joint_grid.
        """
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=None,
            mu_b=1.5
        )
        with self.assertRaises(TypeError):
            predictor.solve_optimal_tip(config)

    # --- 2. Bugs in solver.py ---

    def test_get_points_float_comparison_vulnerability(self):
        """
        Gaps & Bugs: get_points uses simple equivalence checks that permit float values.
        For example, a tip of 1.5 goals when actual goals is 2 can return 3 points because 1.5 - 0.5 = 1.0 == 1.
        """
        # Tipping floats is invalid, so it should return 0 points.
        points = get_points(1.5, 0.5, 2, 1)
        self.assertEqual(points, 0)

    def test_solve_optimal_tip_from_grid_none_in_grid_crash(self):
        """
        Gaps & Bugs: solve_optimal_tip_from_grid crashes when the grid contains None values.
        """
        grid = {
            0: {0: None}
        }
        with self.assertRaises(TypeError):
            solve_optimal_tip_from_grid(grid, 3)

    # --- 3. Bugs in backtest.py ---

    def test_backtest_get_team_stats_type_vulnerability(self):
        """
        Gaps & Bugs: backtest.get_team_stats calls .strip() on the team name without checking type.
        Passing a non-string (like an int) raises AttributeError.
        """
        with self.assertRaises(AttributeError):
            backtest.get_team_stats(123)

    def test_backtest_scientific_notation_float_parsing_bug(self):
        """
        Gaps & Bugs: load_match_data checks if '.' is in the value to decide if it's a float.
        Values written in scientific notation without a decimal (e.g. "1e3") are treated as strings
        or crash when trying to cast to int. This can cause TypeError down the line.
        """
        csv_content = (
            "team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n"
            "Germany,Japan,1,2,0.0,1e3,50.0\n"
        )
        # We write a mock CSV and load it
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            temp_name = f.name
            
        try:
            data = backtest.load_match_data(temp_name)
            self.assertEqual(data[0]['temp'], 1000.0)  # Stored as float!
            
            # Now let's verify that running the backtest works without error
            results = backtest.run_backtest("optimized", data)
            self.assertIsNotNone(results)
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_backtest_empty_matches_assertion_failure(self):
        """
        Gaps & Bugs: backtest.py asserts optimized_total_points > baseline_total_points in main().
        If the backtest has 0 matches (or both models score 0 points), it raises AssertionError,
        making the script crash instead of outputting a clean report.
        """
        # If we run main with an empty CSV, we expect AssertionError or ValueError
        # (ValueError is raised during load_match_data if headers are missing or file is empty,
        # but if we mock load_match_data to return empty list or mock the csv with only headers)
        csv_content = "team_a,team_b,goals_a,goals_b,elevation,temp,humidity\n"
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            temp_name = f.name
            
        try:
            # load_match_data returns empty list
            data = backtest.load_match_data(temp_name)
            self.assertEqual(data, [])
            
            # Running generate_summary_report on empty runs returns 0 for both.
            results_base = backtest.run_backtest("baseline", data)
            results_opt = backtest.run_backtest("optimized", data)
            report = backtest.generate_summary_report(results_base, results_opt)
            
            self.assertEqual(report['optimized_total_points'], 0.0)
            self.assertEqual(report['baseline_total_points'], 0.0)
            
            # If main was run, it would execute:
            # assert report['optimized_total_points'] > report['baseline_total_points']
            # which fails because 0.0 is not > 0.0.
            with self.assertRaises(AssertionError):
                assert report['optimized_total_points'] > report['baseline_total_points']
                
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

if __name__ == '__main__':
    unittest.main()
