import unittest
import numpy as np
import time
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from vectorized_mc import MatrixPrecomputer, VectorizedSimulator

class TestVectorizedEngine(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.matrix = MatrixPrecomputer()

    def test_routing_table_validity(self):
        """Verify the 4096-permutation routing table guarantees exactly 495 valid mappings."""
        valid_masks = 0
        for bitmask in range(4096):
            if bin(bitmask).count('1') == 8:
                valid_masks += 1
                self.assertEqual(len(self.matrix.routing_table[bitmask]), 8)
                self.assertTrue(np.all(self.matrix.routing_table[bitmask] >= 0))
                self.assertTrue(np.all(self.matrix.routing_table[bitmask] <= 11))
                
        self.assertEqual(valid_masks, 495, "Should have exactly 495 valid 3rd-place permutations")

    def test_cdf_copula_bounds(self):
        """Ensures the flattened grid maps correctly to probabilities <= 1.0"""
        sample_cdf = self.matrix.group_cdfs[0, 0]
        self.assertEqual(len(sample_cdf), 225)
        self.assertTrue(sample_cdf[-1] > 0.999) # Last element guarantees catch

    def test_ko_lambda_uses_clean_baseline_for_group_pairs(self):
        """Group-fixture context must not leak into the KO lambda tensors (S14).

        Before the fix, 4 of 6 fixtures per group overwrote lam_a/lam_b with
        matchday-specific rest/travel/form/market context, which
        _build_knockout_matrix then consumed for same-group KO rematch grids."""
        import predictor
        import tournament_bonusfragen as tb

        mx = self.matrix
        t_a, t_b = tb.GROUPS["A"][0], tb.GROUPS["A"][1]   # a group fixture stored as i<j
        i, j = mx.team_to_id[t_a], mx.team_to_id[t_b]

        elo_a = predictor.WORLD_CUP_2026_TEAMS.get(predictor.validate_team_name(t_a), {}).get("elo", 1700)
        elo_b = predictor.WORLD_CUP_2026_TEAMS.get(predictor.validate_team_name(t_b), {}).get("elo", 1700)
        la_base, lb_base = predictor.estimate_base_lambdas_from_elo(t_a, t_b, elo_a, elo_b)
        # setUpClass builds MatrixPrecomputer() without host_teams -> bare context
        la_exp, lb_exp = predictor.get_adjusted_lambdas(
            la_base, lb_base, {"team_name": t_a}, {"team_name": t_b})

        self.assertAlmostEqual(float(mx.lam_a[i, j]), la_exp, places=4)
        self.assertAlmostEqual(float(mx.lam_b[i, j]), lb_exp, places=4)

    def test_performance_benchmark(self):
        """100k simulations complete and return well-formed arrays.

        The wall-clock budget is hardware-dependent (4-5s on fast desktops,
        ~15s on CI containers), so it is only asserted when WM2026_BENCH=1.
        Shape/correctness assertions always run."""
        N = 100000
        sim = VectorizedSimulator(self.matrix, n_sims=N)

        start_time = time.time()
        g_winners, stages, boot, champion, team_goals = sim.simulate()
        duration = time.time() - start_time

        print(f"\n[BENCHMARK] {N:,} simulations executed in {duration:.3f} seconds ({N/duration:,.0f}/s).")
        if os.environ.get("WM2026_BENCH") == "1":
            self.assertTrue(duration < 5.0, f"Vectorized engine too slow: {duration:.2f}s for 100k sims")
        self.assertEqual(len(champion), N)
        self.assertEqual(stages.shape, (N, 48))

    def test_live_state_injection(self):
        """Verify that _sample_match_cdf correctly overrides outcomes based on live state."""
        N = 100
        sim = VectorizedSimulator(self.matrix, n_sims=N)
        
        tA = np.zeros(N, dtype=np.int8)  # Team 0
        tB = np.ones(N, dtype=np.int8)   # Team 1
        fatigue_status = np.zeros((N, self.matrix.N_TEAMS), dtype=bool)
        
        # Find actual team names
        team_0_name = self.matrix.id_to_team[0]
        team_1_name = self.matrix.id_to_team[1]
        
        # Define live state override
        live_key = f"{team_0_name} vs {team_1_name}"
        live_state = {live_key: [3, 0]}
        
        g_a, g_b, went_to_et = sim._sample_match_cdf(
            tA, tB, phase_idx=0, fatigue_status=fatigue_status,
            m_id="M73", live_state=live_state
        )
        
        # Assert goals are exactly 3 and 0 for all universes
        np.testing.assert_array_equal(g_a, 3)
        np.testing.assert_array_equal(g_b, 0)

    def test_live_state_injection_by_match_id(self):
        """m_id-keyed override forces the score in bracket orientation for ALL pairings.

        Regression guard: this path previously never bound val_a/val_b and
        raised UnboundLocalError on the first setup (or could have reused a
        previous setup's values had one been bound)."""
        N = 100
        sim = VectorizedSimulator(self.matrix, n_sims=N)

        # Mix two different pairings in one call -> two unique setups, so the
        # per-iteration binding (not just the first) is exercised.
        tA = np.zeros(N, dtype=np.int8)            # Team 0 in every sim
        tB = np.full(N, 2, dtype=np.int8)          # Team 2 ...
        tB[N // 2:] = 3                            # ... or Team 3
        fatigue_status = np.zeros((N, self.matrix.N_TEAMS), dtype=bool)

        g_a, g_b, went_to_et = sim._sample_match_cdf(
            tA, tB, phase_idx=0, fatigue_status=fatigue_status,
            m_id="M75", live_state={"M75": [2, 1]}
        )

        np.testing.assert_array_equal(g_a, 2)
        np.testing.assert_array_equal(g_b, 1)
        self.assertEqual(len(went_to_et), N)

    def test_live_state_unmatched_falls_through_to_sampling(self):
        """A live_state matching neither m_id nor team names must sample normally."""
        N = 50
        sim = VectorizedSimulator(self.matrix, n_sims=N)
        tA = np.zeros(N, dtype=np.int8)
        tB = np.ones(N, dtype=np.int8)
        fatigue_status = np.zeros((N, self.matrix.N_TEAMS), dtype=bool)

        g_a, g_b, _ = sim._sample_match_cdf(
            tA, tB, phase_idx=0, fatigue_status=fatigue_status,
            m_id="M73", live_state={"M99": [9, 9], "Foo vs Bar": [5, 5]}
        )

        self.assertEqual(len(g_a), N)
        # Sampled scores must not be the unrelated overrides applied verbatim.
        self.assertFalse(np.all((g_a == 9) & (g_b == 9)))
        self.assertFalse(np.all((g_a == 5) & (g_b == 5)))

    def test_matrix_cache_roundtrip(self):
        """save/load must reproduce the precomputed tensors exactly and drive
        the simulator end-to-end (S13)."""
        import tempfile
        import vectorized_mc as vmc

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "matrix.npz")
            vmc.save_matrix(self.matrix, path)
            loaded = vmc.load_matrix(path)

            for name in vmc._MATRIX_ARRAYS:
                np.testing.assert_array_equal(
                    getattr(loaded, name), getattr(self.matrix, name),
                    err_msg=f"array {name} not identical after cache roundtrip")
            self.assertEqual(loaded.team_to_id, self.matrix.team_to_id)
            self.assertEqual(loaded.GROUP_MATCHES, self.matrix.GROUP_MATCHES)
            self.assertEqual(loaded.slot_keys, self.matrix.slot_keys)

            sim = VectorizedSimulator(loaded, n_sims=500)
            g_winners, stages, boot, champs, goals = sim.simulate()
            self.assertEqual(len(champs), 500)
            self.assertEqual(stages.shape, (500, 48))

    def test_matrix_fingerprint_sensitivity(self):
        """The cache key must be stable for identical inputs and change when
        any tensor-relevant input changes (stale cache = silent wrong sims)."""
        import predictor
        import vectorized_mc as vmc

        fp_base = vmc._matrix_fingerprint(None, None)
        self.assertEqual(vmc._matrix_fingerprint(None, None), fp_base)

        team = "Spain"
        orig = predictor.WORLD_CUP_2026_TEAMS[team]["elo"]
        try:
            predictor.WORLD_CUP_2026_TEAMS[team]["elo"] = orig + 1
            self.assertNotEqual(vmc._matrix_fingerprint(None, None), fp_base)
        finally:
            predictor.WORLD_CUP_2026_TEAMS[team]["elo"] = orig

        self.assertNotEqual(vmc._matrix_fingerprint({"Mexico"}, None), fp_base)
        self.assertNotEqual(vmc._matrix_fingerprint(None, {"Spain": 0.2}), fp_base)

        saved = predictor.CONSTANTS["ko_lambda_factor_final"]
        try:
            predictor.CONSTANTS["ko_lambda_factor_final"] = saved * 1.01
            self.assertNotEqual(vmc._matrix_fingerprint(None, None), fp_base)
        finally:
            predictor.CONSTANTS["ko_lambda_factor_final"] = saved

    def test_fatigue_propagation(self):
        """Verify that fatigue carries over and executes without array shape mismatch."""
        N = 10
        sim = VectorizedSimulator(self.matrix, n_sims=N)
        
        tA = np.zeros(N, dtype=np.int8)
        tB = np.ones(N, dtype=np.int8)
        
        # When both are fresh (state 0)
        fatigue_fresh = np.zeros((N, self.matrix.N_TEAMS), dtype=bool)
        g_a_fresh, g_b_fresh, et_fresh = sim._sample_match_cdf(
            tA, tB, phase_idx=0, fatigue_status=fatigue_fresh
        )
        
        # When Team A is fatigued (state 2)
        fatigue_fatigued = np.zeros((N, self.matrix.N_TEAMS), dtype=bool)
        fatigue_fatigued[:, 0] = True
        g_a_fat, g_b_fat, et_fat = sim._sample_match_cdf(
            tA, tB, phase_idx=0, fatigue_status=fatigue_fatigued
        )
        
        # Verify sizes
        self.assertEqual(len(g_a_fresh), N)
        self.assertEqual(len(g_a_fat), N)
        self.assertEqual(len(et_fresh), N)
        self.assertEqual(len(et_fat), N)

if __name__ == '__main__':
    unittest.main()

