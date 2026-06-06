"""
Test suite for v4 features: MatchPhase, sensitivity analysis, batch mode,
team validation, EV breakdown, strategic output.
"""
import unittest
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import predictor


class TestMatchPhase(unittest.TestCase):
    """Tests for Milestone 1: Match-Phase-Aware Knockout Modeling."""

    def test_parse_phase_enum_values(self):
        """All MatchPhase enum values should parse correctly."""
        self.assertEqual(predictor.parse_match_phase("GROUP"), predictor.MatchPhase.GROUP)
        self.assertEqual(predictor.parse_match_phase("R16"), predictor.MatchPhase.R16)
        self.assertEqual(predictor.parse_match_phase("QF"), predictor.MatchPhase.QUARTER)
        self.assertEqual(predictor.parse_match_phase("SF"), predictor.MatchPhase.SEMI)
        self.assertEqual(predictor.parse_match_phase("FINAL"), predictor.MatchPhase.FINAL)
        self.assertEqual(predictor.parse_match_phase("THIRD"), predictor.MatchPhase.THIRD)

    def test_parse_phase_german_aliases(self):
        """German phase names should map correctly."""
        self.assertEqual(predictor.parse_match_phase("achtelfinale"), predictor.MatchPhase.R16)
        self.assertEqual(predictor.parse_match_phase("viertelfinale"), predictor.MatchPhase.QUARTER)
        self.assertEqual(predictor.parse_match_phase("halbfinale"), predictor.MatchPhase.SEMI)
        self.assertEqual(predictor.parse_match_phase("finale"), predictor.MatchPhase.FINAL)

    def test_parse_phase_case_insensitive(self):
        """Phase parsing should be case-insensitive."""
        self.assertEqual(predictor.parse_match_phase("group"), predictor.MatchPhase.GROUP)
        self.assertEqual(predictor.parse_match_phase("Group"), predictor.MatchPhase.GROUP)
        self.assertEqual(predictor.parse_match_phase("QUARTER"), predictor.MatchPhase.QUARTER)

    def test_parse_phase_none(self):
        """None input should return None."""
        self.assertIsNone(predictor.parse_match_phase(None))

    def test_parse_phase_unknown(self):
        """Unknown phase string should return None."""
        self.assertIsNone(predictor.parse_match_phase("unknown_phase"))

    def test_phase_rho_amplification(self):
        """Knockout phases should amplify ρ (make more negative)."""
        rho = -0.05
        lam_a, lam_b = 1.5, 1.2

        rho_group, _, _ = predictor.apply_phase_adjustments(rho, lam_a, lam_b, predictor.MatchPhase.GROUP)
        rho_r16, _, _ = predictor.apply_phase_adjustments(rho, lam_a, lam_b, predictor.MatchPhase.R16)
        rho_qf, _, _ = predictor.apply_phase_adjustments(rho, lam_a, lam_b, predictor.MatchPhase.QUARTER)
        rho_sf, _, _ = predictor.apply_phase_adjustments(rho, lam_a, lam_b, predictor.MatchPhase.SEMI)
        rho_final, _, _ = predictor.apply_phase_adjustments(rho, lam_a, lam_b, predictor.MatchPhase.FINAL)

        # Group phase should leave ρ unchanged
        self.assertEqual(rho_group, rho)
        # Each stage should be more negative (or equally negative) than the previous
        self.assertLess(rho_r16, rho_group)
        self.assertLess(rho_qf, rho_r16)
        self.assertLess(rho_sf, rho_qf)
        self.assertLess(rho_final, rho_sf)

    def test_phase_defensive_scaling(self):
        """KO phases should reduce lambdas (defensive factor)."""
        rho = -0.05
        lam_a, lam_b = 1.5, 1.2

        _, la_group, lb_group = predictor.apply_phase_adjustments(rho, lam_a, lam_b, predictor.MatchPhase.GROUP)
        _, la_r16, lb_r16 = predictor.apply_phase_adjustments(rho, lam_a, lam_b, predictor.MatchPhase.R16)

        # Group should be unchanged
        self.assertEqual(la_group, lam_a)
        self.assertEqual(lb_group, lam_b)
        # R16 should be lower (defensive factor)
        self.assertLess(la_r16, lam_a)
        self.assertLess(lb_r16, lam_b)

    def test_third_place_no_defensive_scaling(self):
        """3rd place match should NOT apply defensive scaling (it's a more open game).
        With phase-specific factors, THIRD gets factor >= 1.0 (slight offensive boost)."""
        rho = -0.05
        lam_a, lam_b = 1.5, 1.2

        _, la_third, lb_third = predictor.apply_phase_adjustments(rho, lam_a, lam_b, predictor.MatchPhase.THIRD)
        # 3rd place should NOT reduce lambdas (factor >= 1.0)
        self.assertGreaterEqual(la_third, lam_a)
        self.assertGreaterEqual(lb_third, lam_b)

    def test_ko_draw_probability_higher(self):
        """Knockout phases should produce higher draw probability than group stage."""
        config_group = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.3, mu_b=1.3, rho=-0.05, phase=predictor.MatchPhase.GROUP
        )
        config_qf = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.3 * 0.95, mu_b=1.3 * 0.95,
            rho=-0.05 * 1.6, phase=predictor.MatchPhase.QUARTER
        )

        _, _, outcomes_group = predictor.solve_optimal_tip(config_group)
        _, _, outcomes_qf = predictor.solve_optimal_tip(config_qf)

        # QF should have higher draw probability
        self.assertGreater(outcomes_qf[1], outcomes_group[1])


class TestSensitivityAnalysis(unittest.TestCase):
    """Tests for Milestone 3: Sensitivity Analysis."""

    def test_sensitivity_returns_valid_structure(self):
        """Sensitivity analysis should return all required fields."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        result = predictor.run_sensitivity_analysis(1.5, 1.2, config)

        self.assertIn("base_tip", result)
        self.assertIn("base_ev", result)
        self.assertIn("confidence", result)
        self.assertIn("tip_consistency", result)
        self.assertIn("ev_gap", result)
        self.assertIn("unique_tips", result)
        self.assertIn("num_scenarios", result)

    def test_sensitivity_confidence_labels(self):
        """Confidence labels should be one of the 4 valid values."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        result = predictor.run_sensitivity_analysis(1.5, 1.2, config)

        self.assertIn(result["confidence"], ["LOCK", "STRONG", "MARGINAL", "COIN-FLIP"])

    def test_sensitivity_consistency_range(self):
        """Tip consistency should be between 0 and 1."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        result = predictor.run_sensitivity_analysis(1.5, 1.2, config)

        self.assertGreaterEqual(result["tip_consistency"], 0.0)
        self.assertLessEqual(result["tip_consistency"], 1.0)

    def test_sensitivity_dominant_team_not_coinflip(self):
        """A heavily dominant team should NOT yield COIN-FLIP confidence."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=3.0, mu_b=0.5, rho=-0.05
        )
        result = predictor.run_sensitivity_analysis(3.0, 0.5, config)

        # When one team is overwhelmingly dominant, the tip may still shift
        # between 2:0, 3:0, etc. under perturbation. But it should never be
        # a complete coin-flip (i.e., the tendency direction should be stable).
        self.assertIn(result["confidence"], ["LOCK", "STRONG", "MARGINAL"])

    def test_sensitivity_num_scenarios_25(self):
        """Default 5 perturbation values should yield 25 scenarios."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        result = predictor.run_sensitivity_analysis(1.5, 1.2, config)

        self.assertEqual(result["num_scenarios"], 25)


class TestEVBreakdown(unittest.TestCase):
    """Tests for Milestone 7: EV Component Breakdown."""

    def test_ev_breakdown_components_sum(self):
        """EV components should sum to the total EV."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        grid = predictor.generate_joint_grid(config)
        tips, _, _ = predictor.solve_optimal_tip(config)
        optimal_tip = tips[0][0]

        bd = predictor.compute_ev_breakdown(grid, optimal_tip)

        self.assertAlmostEqual(
            bd["ev_exact"] + bd["ev_diff"] + bd["ev_tend"],
            bd["ev_total"],
            places=10
        )

    def test_ev_breakdown_probabilities_sum_to_one(self):
        """Point probabilities should sum to 1.0."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        grid = predictor.generate_joint_grid(config)

        bd = predictor.compute_ev_breakdown(grid, (1, 0))

        total_p = bd["p_exact"] + bd["p_diff"] + bd["p_tend"] + bd["p_zero"]
        self.assertAlmostEqual(total_p, 1.0, places=6)

    def test_ev_breakdown_matches_solver_ev(self):
        """The breakdown EV should match the solver's EV."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        grid = predictor.generate_joint_grid(config)
        tips, _, _ = predictor.solve_optimal_tip(config)
        optimal_tip = tips[0][0]
        solver_ev = tips[0][1]

        bd = predictor.compute_ev_breakdown(grid, optimal_tip)

        self.assertAlmostEqual(bd["ev_total"], solver_ev, places=6)

    def test_ev_breakdown_exact_positive(self):
        """Exact match probability should be > 0 for the optimal tip."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        grid = predictor.generate_joint_grid(config)
        tips, _, _ = predictor.solve_optimal_tip(config)
        optimal_tip = tips[0][0]

        bd = predictor.compute_ev_breakdown(grid, optimal_tip)

        self.assertGreater(bd["p_exact"], 0.0)
        self.assertGreater(bd["ev_exact"], 0.0)


class TestTeamValidation(unittest.TestCase):
    """Tests for Milestone 6: Team Name Validation."""

    def test_known_team_no_error(self):
        """A known team should not raise or warn."""
        result = predictor.validate_team_name("Germany")
        self.assertEqual(result, "Germany")

    def test_german_name_resolved(self):
        """German team names should resolve to English."""
        result = predictor.validate_team_name("Deutschland")
        self.assertEqual(result, "Germany")

    def test_strict_mode_raises(self):
        """Unknown team in strict mode should raise ValueError."""
        with self.assertRaises(ValueError):
            predictor.validate_team_name("Atlantis", strict=True)

    def test_non_strict_returns_name(self):
        """Unknown team in non-strict mode should return the name."""
        result = predictor.validate_team_name("Atlantis", strict=False)
        self.assertEqual(result, "Atlantis")

    def test_empty_name_passthrough(self):
        """Empty name should pass through without error."""
        result = predictor.validate_team_name("")
        self.assertEqual(result, "")


class TestBatchPrediction(unittest.TestCase):
    """Tests for Milestone 5: Batch Prediction Mode."""

    def test_batch_prediction_from_csv(self):
        """Batch prediction should process a CSV and return results."""
        csv_content = """team_a,team_b,elevation,temp,humidity,rho
Germany,Japan,0,22,50,-0.05
France,Brazil,0,22,50,-0.05
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, dir='.') as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            results = predictor.run_batch_prediction(csv_path)
            self.assertEqual(len(results), 2)
            self.assertIn("optimal_tip", results[0])
            self.assertIn("ev", results[0])
            self.assertIn("breakdown", results[0])
        finally:
            os.remove(csv_path)

    def test_batch_output_table_format(self):
        """Table output should contain header and data rows."""
        csv_content = """team_a,team_b,elevation,temp,humidity,rho
Germany,Japan,0,22,50,-0.05
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, dir='.') as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            results = predictor.run_batch_prediction(csv_path)
            output = predictor.format_batch_output(results, json_output=False)
            self.assertIn("Germany", output)
            self.assertIn("Japan", output)
            self.assertIn("Expected Points", output)
        finally:
            os.remove(csv_path)

    def test_batch_output_json_format(self):
        """JSON output should be valid JSON."""
        csv_content = """team_a,team_b,elevation,temp,humidity,rho
Germany,Japan,0,22,50,-0.05
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, dir='.') as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            results = predictor.run_batch_prediction(csv_path)
            output = predictor.format_batch_output(results, json_output=True)
            parsed = json.loads(output)
            self.assertIsInstance(parsed, list)
            self.assertEqual(len(parsed), 1)
            self.assertIn("optimal_tip", parsed[0])
        finally:
            os.remove(csv_path)

    def test_batch_with_phase_column(self):
        """Batch prediction should handle the phase column."""
        csv_content = """team_a,team_b,elevation,temp,humidity,rho,phase
Germany,Japan,0,22,50,-0.05,QF
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, dir='.') as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            results = predictor.run_batch_prediction(csv_path)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["phase"], "QF")
        finally:
            os.remove(csv_path)


class TestStrategicOutput(unittest.TestCase):
    """Tests for Milestone 7: Strategic Output Formatting."""

    def test_strategic_output_contains_sections(self):
        """Strategic output should include all key sections."""
        result = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "Japan",
            "elevation": "0", "temp": "22", "humidity": "50",
        })
        output = predictor.format_strategic_output(
            result, "Germany", "Japan", is_estimated=True
        )

        self.assertIn("OPTIMALER TIPP", output)
        self.assertIn("EV-Zerlegung", output)
        self.assertIn("Risikoprofil", output)
        self.assertIn("Strategische Analyse", output)
        self.assertIn("Tendenzwahrscheinlichkeiten", output)

    def test_strategic_output_with_phase(self):
        """Output should show phase label for knockout matches."""
        result = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "Japan",
            "elevation": "0", "temp": "22", "humidity": "50",
            "phase": "SF",
        })
        output = predictor.format_strategic_output(
            result, "Germany", "Japan", is_estimated=True
        )

        self.assertIn("[SF]", output)

    def test_predict_single_match_returns_all_fields(self):
        """predict_single_match should return all required fields."""
        result = predictor.predict_single_match({
            "team_a": "Argentina", "team_b": "France",
            "elevation": "0", "temp": "22", "humidity": "50",
        })

        required_fields = [
            "team_a", "team_b", "phase", "lambda_a_base", "lambda_b_base",
            "lambda_a_adj", "lambda_b_adj", "rho_base", "rho_adj",
            "optimal_tip", "ev", "p_home", "p_draw", "p_away",
            "top_scores", "top_tips", "breakdown", "grid",
        ]
        for field in required_fields:
            self.assertIn(field, result, f"Missing field: {field}")


class TestMatchModelConfigPhase(unittest.TestCase):
    """Tests for MatchModelConfig with phase field."""

    def test_config_default_phase_is_none(self):
        """Default phase should be None."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2
        )
        self.assertIsNone(config.phase)

    def test_config_with_phase(self):
        """Config should accept a phase value."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2,
            phase=predictor.MatchPhase.FINAL
        )
        self.assertEqual(config.phase, predictor.MatchPhase.FINAL)


class TestMarketOddsIntegration(unittest.TestCase):
    """Tests for market odds → lambda reverse solver and blending."""

    def test_round_trip_accuracy(self):
        """λ → P(1x2) → reverse → λ should match within 0.05."""
        test_cases = [
            (1.5, 1.2, -0.05),
            (1.0, 1.0, -0.05),
            (2.0, 0.8, -0.05),
            (0.8, 2.0, -0.05),
        ]
        for la_orig, lb_orig, rho in test_cases:
            ph, pd, pa = predictor._poisson_1x2_from_lambdas(la_orig, lb_orig, rho)
            la_rev, lb_rev = predictor.odds_to_lambdas(ph, pd, pa, rho)
            self.assertAlmostEqual(la_rev, la_orig, delta=0.05,
                                   msg=f"λ_a: {la_rev} vs {la_orig}")
            self.assertAlmostEqual(lb_rev, lb_orig, delta=0.05,
                                   msg=f"λ_b: {lb_rev} vs {lb_orig}")

    def test_1x2_probabilities_sum_to_one(self):
        """Forward model P(H) + P(D) + P(A) should sum to ~1.0."""
        ph, pd, pa = predictor._poisson_1x2_from_lambdas(1.5, 1.2, -0.05)
        self.assertAlmostEqual(ph + pd + pa, 1.0, places=3)

    def test_odds_to_lambdas_rejects_bad_input(self):
        """Should raise ValueError for probabilities not summing to ~1."""
        with self.assertRaises(ValueError):
            predictor.odds_to_lambdas(0.3, 0.3, 0.1)  # Sum = 0.7

    def test_blend_lambdas_pure_market(self):
        """market_weight=1.0 should return pure market lambdas."""
        la, lb = predictor.blend_lambdas(1.5, 1.2, 2.0, 0.8, market_weight=1.0)
        self.assertAlmostEqual(la, 2.0, places=3)
        self.assertAlmostEqual(lb, 0.8, places=3)

    def test_blend_lambdas_pure_elo(self):
        """market_weight=0.0 should return pure Elo lambdas."""
        la, lb = predictor.blend_lambdas(1.5, 1.2, 2.0, 0.8, market_weight=0.0)
        self.assertAlmostEqual(la, 1.5, places=3)
        self.assertAlmostEqual(lb, 1.2, places=3)

    def test_blend_lambdas_default_weight(self):
        """Default 80/20 blend should be 80% market + 20% Elo."""
        la, lb = predictor.blend_lambdas(1.0, 1.0, 2.0, 2.0, market_weight=0.8)
        self.assertAlmostEqual(la, 1.8, places=3)  # 0.8*2.0 + 0.2*1.0
        self.assertAlmostEqual(lb, 1.8, places=3)

    def test_predict_with_odds_changes_result(self):
        """Providing odds should change the prediction compared to Elo-only."""
        r_elo = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "Japan",
        })
        r_odds = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "Japan",
            "odds_home": "1.85", "odds_draw": "3.40", "odds_away": "4.50",
        })
        # Lambdas should differ
        self.assertNotAlmostEqual(r_elo["lambda_a_base"], r_odds["lambda_a_base"], places=1)
        # Odds source should be set
        self.assertEqual(r_odds["odds_source"], "manual")
        # Elo-only has no odds source
        self.assertIsNone(r_elo["odds_source"])

    def test_predict_with_odds_in_csv_format(self):
        """Odds can be provided as CSV string values."""
        r = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "Japan",
            "odds_home": "1.85", "odds_draw": "3.40", "odds_away": "4.50",
            "market_weight": "0.5",
        })
        self.assertEqual(r["odds_source"], "manual")

    def test_real_world_odds_produce_valid_lambdas(self):
        """Real bookmaker odds should produce reasonable λ values."""
        # Pinnacle-style odds for a typical WC match
        oh, od, oa = 2.10, 3.20, 3.60
        raw_h, raw_d, raw_a = 1/oh, 1/od, 1/oa
        total = raw_h + raw_d + raw_a
        p_h, p_d, p_a = raw_h/total, raw_d/total, raw_a/total
        
        la, lb = predictor.odds_to_lambdas(p_h, p_d, p_a)
        
        # Lambdas should be reasonable (0.5 to 3.0 for football)
        self.assertGreater(la, 0.5)
        self.assertLess(la, 3.0)
        self.assertGreater(lb, 0.5)
        self.assertLess(lb, 3.0)


class TestKnockoutModel(unittest.TestCase):
    """Tests for the 3-layer KO model (90min → ET → Penalties)."""

    def test_penalty_distribution_no_draws(self):
        """Penalty shootout distribution should never produce draws."""
        dist = predictor.penalty_shootout_distribution(0.75, 0.75, 0.72, 0.72, 5)
        for (a, b), p in dist.items():
            self.assertNotEqual(a, b, f"Draw outcome {a}:{b} in penalty distribution")

    def test_penalty_distribution_sums_to_one(self):
        """Penalty probabilities should sum to ~1.0."""
        dist = predictor.penalty_shootout_distribution(0.75, 0.75, 0.72, 0.72, 5)
        total = sum(dist.values())
        self.assertAlmostEqual(total, 1.0, places=4)

    def test_penalty_symmetry_equal_rates(self):
        """With equal conversion rates, P(A wins) should equal P(B wins)."""
        dist = predictor.penalty_shootout_distribution(0.75, 0.75, 0.72, 0.72, 5)
        p_a_wins = sum(v for (a, b), v in dist.items() if a > b)
        p_b_wins = sum(v for (a, b), v in dist.items() if b > a)
        self.assertAlmostEqual(p_a_wins, p_b_wins, places=6)

    def test_penalty_asymmetry_different_rates(self):
        """With different rates, the better team should win more often."""
        dist = predictor.penalty_shootout_distribution(0.85, 0.65, 0.85, 0.65, 5)
        p_a_wins = sum(v for (a, b), v in dist.items() if a > b)
        p_b_wins = sum(v for (a, b), v in dist.items() if b > a)
        self.assertGreater(p_a_wins, p_b_wins)

    def test_ko_grid_no_draws(self):
        """KO final grid should have zero draw probability."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        grid = predictor.generate_ko_final_grid(config, max_final_goals=12)
        draw_prob = sum(grid[d][d] for d in range(13))
        self.assertAlmostEqual(draw_prob, 0.0, places=10)

    def test_ko_grid_sums_to_one(self):
        """KO grid probabilities should sum to ~1.0."""
        config = predictor.MatchModelConfig(
            dist_type=predictor.ModelDistribution.POISSON,
            mu_a=1.5, mu_b=1.2, rho=-0.05
        )
        grid = predictor.generate_ko_final_grid(config, max_final_goals=15)
        total = sum(grid[a][b] for a in range(16) for b in range(16))
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_ko_predict_single_match_uses_ko_model(self):
        """predict_single_match with a KO phase should use the KO model."""
        result = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "Japan",
            "elevation": "0", "temp": "22", "humidity": "50",
            "phase": "QF",
        })
        self.assertTrue(result["is_ko_model"])
        self.assertEqual(result["p_draw"], 0.0)

    def test_group_predict_does_not_use_ko_model(self):
        """predict_single_match without phase should NOT use KO model."""
        result = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "Japan",
            "elevation": "0", "temp": "22", "humidity": "50",
        })
        self.assertFalse(result["is_ko_model"])
        self.assertGreater(result["p_draw"], 0.0)

    def test_ko_tips_include_penalty_scores(self):
        """KO model tips should include high-scoring penalty scenarios."""
        result = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "France",
            "elevation": "0", "temp": "22", "humidity": "50",
            "phase": "FINAL",
        })
        # At least one tip should have total goals >= 8 (penalty territory)
        high_scoring_tips = [t for t in result["top_tips"] 
                            if sum(int(x) for x in t["tip"].split(":")) >= 8]
        self.assertGreater(len(high_scoring_tips), 0, 
                          "No penalty-range tips found in Final tips")

    def test_third_place_uses_ko_model(self):
        """3rd place match should also use KO model (goes to ET/pens)."""
        result = predictor.predict_single_match({
            "team_a": "Croatia", "team_b": "Morocco",
            "elevation": "0", "temp": "22", "humidity": "50",
            "phase": "THIRD",
        })
        self.assertTrue(result["is_ko_model"])
        self.assertEqual(result["p_draw"], 0.0)


class TestBugfixRegressions(unittest.TestCase):
    """Regression tests for bugs found during code review."""

    def test_rho_zero_with_knockout_phase(self):
        """When base ρ=0, knockout phase should still apply draw inflation.
        
        Bug: rho * multiplier = 0 * anything = 0, so knockout modeling
        had zero effect when users passed --rho 0 or defaulted to 0.
        Fix: additive fallback when rho ≈ 0.
        """
        lam_a, lam_b = 1.5, 1.2

        rho_group, _, _ = predictor.apply_phase_adjustments(0.0, lam_a, lam_b, predictor.MatchPhase.GROUP)
        rho_final, _, _ = predictor.apply_phase_adjustments(0.0, lam_a, lam_b, predictor.MatchPhase.FINAL)

        # Group with rho=0 should stay 0
        self.assertEqual(rho_group, 0.0)
        # Final with rho=0 should NOT stay 0 — it should apply a base offset
        self.assertLess(rho_final, 0.0, "ρ should become negative in the Final even when base ρ=0")

    def test_tz_crossed_float_string_from_csv(self):
        """CSV values like '5.0' for tz_crossed should parse correctly.
        
        Bug: int('5.0') throws ValueError. 
        Fix: int(float('5.0')) = 5.
        """
        result = predictor.predict_single_match({
            "team_a": "Germany", "team_b": "Japan",
            "elevation": "0", "temp": "22", "humidity": "50",
            "tz_crossed_a": "5.0", "tz_crossed_b": "8.0",
        })
        self.assertIn("optimal_tip", result)

    def test_batch_with_float_tz_values(self):
        """Batch prediction with float tz_crossed values from CSV should work."""
        import tempfile
        csv_content = """team_a,team_b,elevation,temp,humidity,rho,tz_crossed_a,tz_crossed_b
Germany,Japan,0,22,50,-0.05,5.0,8.0
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, dir='.') as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            results = predictor.run_batch_prediction(csv_path)
            self.assertEqual(len(results), 1)
            self.assertNotIn("error", results[0])
        finally:
            os.remove(csv_path)

    def test_rho_nonzero_still_multiplicative(self):
        """When base ρ is non-zero, the multiplicative path should still work."""
        rho = -0.10
        rho_adj, _, _ = predictor.apply_phase_adjustments(rho, 1.5, 1.2, predictor.MatchPhase.R16)
        expected = rho * 1.4  # ko_rho_multiplier_r16
        self.assertAlmostEqual(rho_adj, expected, places=10)


if __name__ == '__main__':
    unittest.main()
