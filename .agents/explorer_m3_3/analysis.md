# Milestone 3 Analysis: Kicktipp Solver (EV Maximization)

This analysis evaluates the current Kicktipp optimization engine in `predictor.py`, formulates a plan to extract the solver logic to a new module `solver.py`, and designs a unit test suite to verify point calculations, draw tendencies, and Expected Value (EV) maximization.

---

## 1. Analysis of Current Implementation & Contracts

### Current `solve_optimal_tip` Flow (in `predictor.py`):
1. **Config Sanitization**: Parses either a `MatchModelConfig` object or raw `lambda_A`, `lambda_B`, `rho`, `max_goals`, `max_tip` parameters.
2. **Grid Generation**: Calls `generate_joint_grid(config)` to construct the `12x12` (or custom sized) joint probability distribution.
3. **EV Optimization Loop**:
   - Loops over all possible tips $(t_A, t_B)$ where $t_A, t_B \in [0, \text{max\_tip}]$.
   - For each tip, iterates over all actual goal outcomes $(g_A, g_B)$ from the grid.
   - Calculates the Kicktipp points for each combination via `get_points(t_A, t_B, g_A, g_B)`.
   - Weighs points by the outcome probability:
     $$E(t_A, t_B) = \sum_{g_A, g_B} \text{get\_points}(t_A, t_B, g_A, g_B) \times P(g_A, g_B)$$
4. **Outcome Aggregation**: Sums probabilities to extract aggregate home win ($P(\text{home})$), draw ($P(\text{draw})$), and away win ($P(\text{away})$) probabilities.
5. **Sorting & Selection**:
   - Sorts tips by Expected Value (EV) in descending order.
   - Sorts exact scores by probability in descending order.
6. **Return Values**: Returns `(sorted_tips, sorted_scores[:5], (prob_home, prob_draw, prob_away))`.

### Scoring Rules (`get_points`):
Kicktipp 4/3/2 rules are defined as follows:
- **4 Points (Exact)**: $t_A = g_A$ and $t_B = g_B$
- **3 Points (Difference)**: $t_A - t_B = g_A - g_B$ and $\text{sign}(t_A - t_B) = \text{sign}(g_A - g_B)$
- **2 Points (Tendency)**: $\text{sign}(t_A - t_B) = \text{sign}(g_A - g_B)$
- **0 Points**: Otherwise

**Critical Draw Rule Caveat**:
Under standard Kicktipp rules (and as implemented in `get_points`), if a draw is tipped (e.g., 1-1) and the actual result is a different draw (e.g., 2-2), the difference matches ($1 - 1 = 0$ and $2 - 2 = 0$) and the tendencies match (both are draws, sign = 0). However, the points rule designates **2 points** (tendency) rather than **3 points** for draw differences.
In `get_points`:
```python
    if diff_actual == diff_tip:
        if diff_actual == 0:
            return 2  # Draw tendency, NOT difference points
        return 3      # Win difference points
```
This is verified by existing test `test_t1_f3_draw_tendency_only`.

---

## 2. Refactoring Plan (Refactoring `predictor.py` and Creating `solver.py`)

To adhere to the interface contracts in `PROJECT.md`, we will create a dedicated `solver.py` and import/delegate from `predictor.py`.

### Avoid Circular Dependencies:
- `predictor.py` needs `solver.py` for point calculations and EV maximization.
- `solver.py` **must not** import `predictor.py` or `MatchModelConfig`.
- Therefore, the solver should operate purely on a generic joint probability distribution (represented as a 2D float dictionary `grid[g_A][g_B]`) and a `max_tip` parameter.

### Design of `solver.py`:
```python
# solver.py
from typing import Dict, Tuple, List

def get_points(t_A: int, t_B: int, g_A: int, g_B: int) -> int:
    """
    Calculates tipping points according to the rules:
    - 4 points: Exact score
    - 3 points: Correct goal difference and tendency (e.g. Tip 2:0, Actual 3:1)
    - 2 points: Correct tendency only (Heimsieg / Remis / Auswärtssieg)
    - 0 points: Otherwise
    """
    if t_A == g_A and t_B == g_B:
        return 4
    
    diff_actual = g_A - g_B
    diff_tip = t_A - t_B
    
    sign_actual = 1 if diff_actual > 0 else (-1 if diff_actual < 0 else 0)
    sign_tip = 1 if diff_tip > 0 else (-1 if diff_tip < 0 else 0)
    
    if diff_actual == diff_tip:
        if diff_actual == 0:
            return 2
        return 3
    elif sign_actual == sign_tip:
        return 2
    else:
        return 0

def solve_optimal_tip_from_grid(
    grid: Dict[int, Dict[int, float]], 
    max_tip: int = 6
) -> Tuple[List[Tuple[Tuple[int, int], float]], List[Tuple[Tuple[int, int], float]], Tuple[float, float, float]]:
    """
    Takes a pre-computed joint probability grid and maximizes expected Kicktipp points.
    Returns:
      - sorted_tips: List of ((t_A, t_B), expected_points) sorted by EV descending.
      - sorted_scores: List of ((g_A, g_B), probability) sorted by probability descending.
      - outcomes: Tuple of (prob_home, prob_draw, prob_away).
    """
    expected_points = {}
    for t_a in range(max_tip + 1):
        for t_b in range(max_tip + 1):
            ev = 0.0
            for g_a in grid:
                for g_b in grid[g_a]:
                    pts = get_points(t_a, t_b, g_a, g_b)
                    ev += pts * grid[g_a][g_b]
            expected_points[(t_a, t_b)] = ev

    # Aggregate outcome probabilities
    prob_home = sum(grid[g_a][g_b] for g_a in grid for g_b in grid[g_a] if g_a > g_b)
    prob_draw = sum(grid[g_a][g_b] for g_a in grid for g_b in grid[g_a] if g_a == g_b)
    prob_away = sum(grid[g_a][g_b] for g_a in grid for g_b in grid[g_a] if g_a < g_b)

    # Sort tips descending by EV
    sorted_tips = sorted(expected_points.items(), key=lambda x: x[1], reverse=True)

    # Sort exact scores descending by probability
    flat_probs = []
    for g_a in grid:
        for g_b in grid[g_a]:
            flat_probs.append(((g_a, g_b), grid[g_a][g_b]))
    sorted_scores = sorted(flat_probs, key=lambda x: x[1], reverse=True)

    return sorted_tips, sorted_scores, (prob_home, prob_draw, prob_away)
```

### Refactoring `predictor.py` (Backward Compatible):
To keep existing tests passing, `predictor.py` should import `get_points` and wrap `solve_optimal_tip` by delegating the solver portion:

```python
# predictor.py changes

# 1. Imports from solver
from solver import get_points, solve_optimal_tip_from_grid

# 2. Modify solve_optimal_tip to delegate to solver.py
def solve_optimal_tip(config_or_lamA, lam_B=None, rho=0.0, max_goals=12, max_tip=6):
    if isinstance(config_or_lamA, MatchModelConfig):
        config = config_or_lamA
    else:
        config = MatchModelConfig(
            dist_type=ModelDistribution.POISSON,
            mu_a=config_or_lamA,
            mu_b=lam_B if lam_B is not None else config_or_lamA,
            alpha_a=0.0,
            alpha_b=0.0,
            rho=rho,
            max_goals=max_goals,
            max_tip=max_tip
        )
        
    grid = generate_joint_grid(config)

    try:
        raw_max_tip = int(config.max_tip)
        if math.isnan(raw_max_tip) or math.isinf(raw_max_tip):
            raw_max_tip = 6
    except (ValueError, TypeError):
        raw_max_tip = 6
    max_tip_clamped = max(0, min(100, raw_max_tip))

    # Delegate core mathematical solver to solver.py
    sorted_tips, sorted_scores, outcomes = solve_optimal_tip_from_grid(grid, max_tip=max_tip_clamped)
    
    # Existing E2E tests expect only the top 5 exact scores
    return sorted_tips, sorted_scores[:5], outcomes
```

---

## 3. Unit Test Suite Design (`tests/test_solver.py`)

A new test file `tests/test_solver.py` will be discovered automatically by `run_e2e.py`. It should verify:
1. **Scoring Logic**: Exact matches (4 pts), differences (3 pts), wins/away/home tendencies (2 pts), misses (0 pts).
2. **Draw Differences**: Confirm draw differences return 2 points instead of 3 points.
3. **EV Maximization**: Confirm the solver selects the optimal tip over the most probable one when expectations favor another outcome.

### Mathematical EV Maximization Test Case:
Suppose we construct a joint probability distribution with three non-zero probabilities:
- $P(0,0) = 0.40$ (Draw)
- $P(2,1) = 0.35$ (Home win)
- $P(3,0) = 0.25$ (Home win)

Expected values for potential tips:
- **Tip (0, 0)**:
  - Actual (0, 0): exact match (4 points) $\rightarrow 4 \times 0.40 = 1.60$
  - Actual (2, 1) or (3, 0): 0 points
  - **$EV(0,0) = 1.60$**
- **Tip (2, 1)**:
  - Actual (0, 0): 0 points
  - Actual (2, 1): exact match (4 points) $\rightarrow 4 \times 0.35 = 1.40$
  - Actual (3, 0): tendency match (2 points) $\rightarrow 2 \times 0.25 = 0.50$
  - **$EV(2,1) = 1.40 + 0.50 = 1.90$**
- **Tip (1, 0)**:
  - Actual (0, 0): 0 points
  - Actual (2, 1): difference match (3 points) $\rightarrow 3 \times 0.35 = 1.05$
  - Actual (3, 0): tendency match (2 points) $\rightarrow 2 \times 0.25 = 0.50$
  - **$EV(1,0) = 1.05 + 0.50 = 1.55$**

Even though the most likely individual outcome is a (0, 0) draw (40%), the EV of tipping (2, 1) is higher (1.90 vs 1.60) because it captures points from the home win tendency of (3, 0). The solver must identify (2, 1) as the optimal tip.

### `tests/test_solver.py` Implementation Code:
```python
# tests/test_solver.py
import unittest
from solver import get_points, solve_optimal_tip_from_grid

class TestSolver(unittest.TestCase):
    
    def test_get_points_exact(self):
        """Verify exact scores yield 4 points."""
        self.assertEqual(get_points(2, 1, 2, 1), 4)
        self.assertEqual(get_points(0, 0, 0, 0), 4)
        
    def test_get_points_difference(self):
        """Verify matching win difference yields 3 points."""
        # Tip 2-1 vs Actual 3-2 (difference +1)
        self.assertEqual(get_points(2, 1, 3, 2), 3)
        # Tip 0-2 vs Actual 1-3 (difference -2)
        self.assertEqual(get_points(0, 2, 1, 3), 3)
        
    def test_get_points_tendency_win(self):
        """Verify matching win tendency only yields 2 points."""
        # Tip 2-0 vs Actual 3-2 (both home wins, different differences)
        self.assertEqual(get_points(2, 0, 3, 2), 2)
        # Tip 1-3 vs Actual 0-1 (both away wins, different differences)
        self.assertEqual(get_points(1, 3, 0, 1), 2)

    def test_get_points_draw_tendency_only(self):
        """Verify that different draws yield 2 points (tendency), not 3 points (difference)."""
        # Tip 1-1 vs Actual 2-2 (both draws, but not exact)
        self.assertEqual(get_points(1, 1, 2, 2), 2)
        self.assertEqual(get_points(0, 0, 3, 3), 2)
        
    def test_get_points_incorrect(self):
        """Verify incorrect tendencies yield 0 points."""
        self.assertEqual(get_points(2, 1, 1, 2), 0) # Home win vs Away win
        self.assertEqual(get_points(1, 1, 2, 1), 0) # Draw vs Home win
        self.assertEqual(get_points(0, 1, 0, 0), 0) # Away win vs Draw

    def test_ev_maximization_certainty(self):
        """With 100% certainty on one score, that score must be the optimal tip with EV=4.0."""
        grid = {
            2: {1: 1.0}
        }
        sorted_tips, _, _ = solve_optimal_tip_from_grid(grid, max_tip=3)
        # Top tip should be (2, 1)
        self.assertEqual(sorted_tips[0][0], (2, 1))
        self.assertAlmostEqual(sorted_tips[0][1], 4.0)

    def test_ev_maximization_skewed(self):
        """Verify that solver chooses a less probable score that maximizes total EV."""
        # P(0,0) = 0.40, P(2,1) = 0.35, P(3,0) = 0.25
        grid = {
            0: {0: 0.40},
            2: {1: 0.35},
            3: {0: 0.25}
        }
        # Tips should be sorted by EV descending
        # EV((2,1)) = 4*0.35 + 2*0.25 = 1.90
        # EV((0,0)) = 4*0.40 = 1.60
        # EV((1,0)) = 3*0.35 + 2*0.25 = 1.55
        sorted_tips, _, _ = solve_optimal_tip_from_grid(grid, max_tip=3)
        
        self.assertEqual(sorted_tips[0][0], (2, 1))
        self.assertAlmostEqual(sorted_tips[0][1], 1.90)
        self.assertEqual(sorted_tips[1][0], (0, 0))
        self.assertAlmostEqual(sorted_tips[1][1], 1.60)
        self.assertEqual(sorted_tips[2][0], (1, 0))
        self.assertAlmostEqual(sorted_tips[2][1], 1.55)

    def test_solve_optimal_tip_from_grid_symmetry(self):
        """Symmetric grid should yield symmetric expected values."""
        grid = {
            1: {0: 0.30},
            0: {1: 0.30},
            0: {0: 0.40}
        }
        sorted_tips, _, (p_home, p_draw, p_away) = solve_optimal_tip_from_grid(grid, max_tip=2)
        ev_dict = dict(sorted_tips)
        
        self.assertAlmostEqual(p_home, 0.30)
        self.assertAlmostEqual(p_away, 0.30)
        self.assertAlmostEqual(p_draw, 0.40)
        self.assertAlmostEqual(ev_dict[(1, 0)], ev_dict[(0, 1)])
```

---

## 4. Verification Plan

To verify this implementation once code files are modified by the implementer agent:
1. Run the test suite:
   ```bash
   python3 tests/run_e2e.py
   ```
2. Verify that the test output reports execution and success of `tests/test_solver.py` alongside the existing E2E tiers.
3. Check code layout compatibility: ensure all imports function correctly and no circular imports exist.
