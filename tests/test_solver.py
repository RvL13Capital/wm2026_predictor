import unittest
import os
import sys

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from predictor import get_points, solve_optimal_tip_from_grid

class TestSolver(unittest.TestCase):

    def test_get_points_exact_score(self):
        # 4 points: Exact score
        self.assertEqual(get_points(2, 1, 2, 1), 4)
        self.assertEqual(get_points(0, 0, 0, 0), 4)
        self.assertEqual(get_points(1, 3, 1, 3), 4)

    def test_get_points_difference(self):
        # 3 points: Correct goal difference and tendency (non-draws only)
        self.assertEqual(get_points(2, 0, 3, 1), 3)
        self.assertEqual(get_points(1, 2, 2, 3), 3)
        self.assertEqual(get_points(3, 1, 4, 2), 3)

    def test_get_points_tendency(self):
        # 2 points: Correct tendency only
        self.assertEqual(get_points(2, 0, 3, 2), 2)  # Home win, different diff
        self.assertEqual(get_points(0, 2, 1, 4), 2)  # Away win, different diff

    def test_get_points_draw_difference_exception(self):
        # 2 points: Draw tip on a non-exact draw outcome (Draw Difference Exception)
        self.assertEqual(get_points(1, 1, 2, 2), 2)
        self.assertEqual(get_points(2, 2, 0, 0), 2)
        self.assertEqual(get_points(0, 0, 3, 3), 2)

    def test_get_points_incorrect(self):
        # 0 points: Incorrect tendency
        self.assertEqual(get_points(2, 1, 1, 2), 0)
        self.assertEqual(get_points(1, 1, 2, 1), 0)
        self.assertEqual(get_points(0, 1, 0, 0), 0)

    def test_solve_optimal_tip_skewed_distribution(self):
        # Skewed distribution:
        # P(0,0) = 0.40
        # P(2,1) = 0.35
        # P(3,0) = 0.25
        grid = {}
        for g_a in range(4):
            grid[g_a] = {}
            for g_b in range(4):
                grid[g_a][g_b] = 0.0
        grid[0][0] = 0.40
        grid[2][1] = 0.35
        grid[3][0] = 0.25

        sorted_tips, sorted_scores, outcomes = solve_optimal_tip_from_grid(grid, max_tip=3)

        # Expected outcome probabilities:
        # prob_home = P(2,1) + P(3,0) = 0.35 + 0.25 = 0.60
        # prob_draw = P(0,0) = 0.40
        # prob_away = 0.0
        self.assertAlmostEqual(outcomes[0], 0.60)
        self.assertAlmostEqual(outcomes[1], 0.40)
        self.assertAlmostEqual(outcomes[2], 0.00)

        # Expected top 3 exact scores by probability:
        # (0,0) with 0.40
        # (2,1) with 0.35
        # (3,0) with 0.25
        self.assertEqual(sorted_scores[0][0], (0, 0))
        self.assertAlmostEqual(sorted_scores[0][1], 0.40)
        self.assertEqual(sorted_scores[1][0], (2, 1))
        self.assertAlmostEqual(sorted_scores[1][1], 0.35)
        self.assertEqual(sorted_scores[2][0], (3, 0))
        self.assertAlmostEqual(sorted_scores[2][1], 0.25)

        # Expected optimal tip is (2,1) with EV 1.90
        # Second best should be (3,0) with EV 1.70 or (0,0) with EV 1.60
        top_tip, top_ev = sorted_tips[0]
        self.assertEqual(top_tip, (2, 1))
        self.assertAlmostEqual(top_ev, 1.90)

        # Verify tip (0,0) has EV 1.60
        tip_00_ev = next(ev for tip, ev in sorted_tips if tip == (0, 0))
        self.assertAlmostEqual(tip_00_ev, 1.60)

        # Verify tips are strictly sorted descending by EV
        evs = [ev for tip, ev in sorted_tips]
        self.assertEqual(evs, sorted(evs, reverse=True))

    def test_mathematical_equivalence(self):
        import random
        
        def naive_solve(grid, max_tip):
            expected_points = {}
            flat_probs = []
            if isinstance(grid, dict):
                for g_a, row in grid.items():
                    for g_b, val in row.items():
                        flat_probs.append(((g_a, g_b), val))
            else:
                flat_probs = []
                for g_a, row in enumerate(grid):
                    for g_b, val in enumerate(row):
                        flat_probs.append(((g_a, g_b), val))
                        
            for t_a in range(max_tip + 1):
                for t_b in range(max_tip + 1):
                    ev = 0.0
                    for (g_a, g_b), val in flat_probs:
                        ev += val * get_points(t_a, t_b, g_a, g_b)
                    expected_points[(t_a, t_b)] = ev
                    
            sorted_tips = sorted(expected_points.items(), key=lambda x: x[1], reverse=True)
            return sorted_tips

        def generate_random_grid_dict(size):
            grid = {}
            total = 0.0
            for x in range(size):
                grid[x] = {}
                for y in range(size):
                    val = random.random()
                    grid[x][y] = val
                    total += val
            for x in range(size):
                for y in range(size):
                    grid[x][y] /= total
            return grid

        def generate_random_grid_list(size):
            grid = []
            total = 0.0
            for x in range(size):
                row = []
                for y in range(size):
                    val = random.random()
                    row.append(val)
                    total += val
                grid.append(row)
            for x in range(size):
                for y in range(size):
                    grid[x][y] /= total
            return grid

        # Test on 2000 random grids
        for i in range(2000):
            size = random.randint(1, 10)
            max_tip = random.randint(0, 6)
            grid_type = random.choice(["dict", "list"])
            
            if grid_type == "dict":
                grid = generate_random_grid_dict(size)
            else:
                grid = generate_random_grid_list(size)
                
            naive_tips = naive_solve(grid, max_tip)
            opt_tips, _, _ = solve_optimal_tip_from_grid(grid, max_tip)
            
            self.assertEqual(len(naive_tips), len(opt_tips))
            for (n_tip, n_ev), (o_tip, o_ev) in zip(naive_tips, opt_tips):
                if n_tip != o_tip:
                    # If EVs are extremely close, order could differ due to sort stability,
                    # so we only fail if EVs are not equal.
                    self.assertAlmostEqual(n_ev, o_ev, places=9)
                self.assertAlmostEqual(n_ev, o_ev, places=9)

if __name__ == '__main__':
    unittest.main()

