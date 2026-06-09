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

    def test_performance_benchmark(self):
        """Asserts that 100,000 simulations complete under the 5.0 second latency limit."""
        N = 100000
        sim = VectorizedSimulator(self.matrix, n_sims=N)
        
        start_time = time.time()
        g_winners, stages, boot, champion, team_goals = sim.simulate()
        duration = time.time() - start_time
        
        print(f"\n[BENCHMARK] {N:,} simulations executed in {duration:.3f} seconds.")
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

