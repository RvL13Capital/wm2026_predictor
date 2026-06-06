# Analysis & Recommendations: Kicktipp Solver (Milestone 3)

## Executive Summary
This report analyzes the prediction engine codebase to plan the implementation of the Kicktipp Solver (`solver.py`) for Milestone 3. We define the scoring algorithm for the 4/3/2 point rules, address the draw difference exception, outline the module architecture, and provide the mathematical formulation for expected value (EV) maximization.

---

## 1. Existing Codebase Analysis

### File and Interface Structure
We investigated the following files in the workspace:
1. `PROJECT.md` (lines 32-40, 48-52): Maps the requirements for the Kicktipp Solver (EV Maximization under 4/3/2 scoring rules) and defines the interface contract where the prediction engine outputs a full probability distribution grid and the solver finds the optimal tip maximizing expected points.
2. `predictor.py` (lines 116-140): Contains an existing implementation of `get_points(t_A, t_B, g_A, g_B)` and `solve_optimal_tip(...)` (lines 463-523).
3. `tests/test_predictor.py` (lines 19-200) and `tests/test_tier1_feature_coverage.py` (lines 180-204): Verify the solver's point calculation rules and expected value maximization sorting behavior.

### The Point Calculation Code in `predictor.py`
The point calculation is currently implemented in `predictor.py` as follows:

```python
# predictor.py lines 116-140
def get_points(t_A, t_B, g_A, g_B):
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
    
    sign_actual = sign(diff_actual)
    sign_tip = sign(diff_tip)
    
    if diff_actual == diff_tip:
        if diff_actual == 0:
            return 2
        return 3
    elif sign_actual == sign_tip:
        return 2
    else:
        return 0
```

---

## 2. Formulation of the Kicktipp 4/3/2 Rules

In soccer prediction games, points are awarded according to the similarity between a user's tip $(t_A, t_B)$ and the actual score $(g_A, g_B)$. 

### The Standard 4/3/2 Rule System:
- **4 Points (Exact Result)**: Awarded when the tipped score matches the actual score exactly:
  $$t_A = g_A \quad \text{and} \quad t_B = g_B$$
- **3 Points (Correct Difference)**: Awarded when the goal difference and the match tendency are correct, *excluding draws*:
  $$t_A - t_B = g_A - g_B \quad \text{and} \quad \operatorname{sign}(t_A - t_B) = \operatorname{sign}(g_A - g_B) \neq 0$$
- **2 Points (Correct Tendency)**: Awarded when the match outcome (Home Win, Away Win, or Draw) is correctly predicted, but the score is not exact and (for wins/losses) the goal difference is incorrect:
  $$\operatorname{sign}(t_A - t_B) = \operatorname{sign}(g_A - g_B)$$
- **0 Points (Incorrect)**: Awarded if the match outcome is predicted incorrectly.

### The Draw Difference Rule (Exception)
A critical rule in Kicktipp is the **Draw Difference Exception**.
- By definition, all draw matches have a goal difference of $0$ ($g_A - g_B = 0$).
- If a player tips a draw (e.g., $1:1$, so $t_A - t_B = 0$) and the match ends in a draw (e.g., $2:2$, so $g_A - g_B = 0$), the goal differences match ($0 = 0$).
- If the simple difference rule were applied blindly, tipping $1:1$ on a $2:2$ outcome would award **3 points** (since $t_A - t_B = g_A - g_B$).
- However, Kicktipp rules dictate that for draws, there is no distinct "difference" category; you either predict the score exactly (**4 points**) or you only get the correct tendency (**2 points**). No draw result can ever yield **3 points** unless it is exact (which yields 4).
- Our implementation correctly handles this by returning 2 points when `diff_actual == diff_tip` and `diff_actual == 0` (non-exact draw tip on a draw match).

### Expected Points Matrix for Tipping
The table below illustrates points awarded under different scenarios:

| Tip ($t_A : t_B$) | Actual ($g_A : g_B$) | Actual Diff | Tip Diff | Tendency Match? | Diff Match? | Points Awarded | Notes |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| **2 : 1** | **2 : 1** | +1 | +1 | Yes | Yes (Exact) | **4** | Exact score matched |
| **1 : 1** | **1 : 1** | 0 | 0 | Yes | Yes (Exact) | **4** | Exact draw score matched |
| **1 : 0** | **2 : 1** | +1 | +1 | Yes | Yes | **3** | Non-draw, correct diff and tendency |
| **1 : 2** | **2 : 3** | -1 | -1 | Yes | Yes | **3** | Non-draw away win, correct diff and tendency |
| **2 : 0** | **3 : 0** | +3 | +2 | Yes | No | **2** | Correct tendency, wrong difference |
| **1 : 1** | **2 : 2** | 0 | 0 | Yes | Yes | **2** | **Draw difference rule**: gets 2 pts, not 3 |
| **0 : 0** | **3 : 3** | 0 | 0 | Yes | Yes | **2** | **Draw difference rule**: gets 2 pts, not 3 |
| **2 : 1** | **1 : 2** | -1 | +1 | No | No | **0** | Wrong winner |
| **1 : 0** | **1 : 1** | 0 | +1 | No | No | **0** | Predicted win, ended in draw |

---

## 3. Mathematical Formulation of the Solver

The Kicktipp Solver must identify the optimal tip $t^* = (t_A, t_B)$ that maximizes the expected points $E(t)$ under the joint probability distribution of goals $P(g_A, g_B)$ generated by the prediction engine:

$$t^* = \operatorname{arg\,max}_{t_A, t_B \in [0, \text{max\_tip}]} E(t_A, t_B)$$

Where:
$$E(t_A, t_B) = \sum_{g_A=0}^{\text{max\_goals}} \sum_{g_B=0}^{\text{max\_goals}} P(g_A, g_B) \times \text{get\_points}(t_A, t_B, g_A, g_B)$$

### Algorithm and Complexity Analysis
1. **Search Space**:
   - The tip space is bounded by `max_tip` (typically $6$). Thus, the number of candidate tips is $(6 + 1) \times (6 + 1) = 49$.
   - The score space is bounded by `max_goals` (typically $12$). Thus, the size of the probability grid is $(12 + 1) \times (12 + 1) = 169$.
2. **Computational Cost**:
   - Calculating the expected value for a single tip requires iterating over all grid cells: $169$ operations.
   - Evaluating all $49$ candidate tips requires $49 \times 169 = 8,281$ point calculations.
   - Since $8,281$ operations take less than 1-2 milliseconds in pure Python, we recommend using a straightforward nested double loop for absolute clarity, readability, and ease of unit testing. No complex vectorization or optimization packages (e.g., NumPy) are required.

---

## 4. Architectural & Implementation Recommendations

To implement Milestone 3 clean and compliant with the project's layout:
1. **Create `solver.py`**:
   - Implement the scoring function `get_points` (or `calculate_points`).
   - Implement the EV maximizing solver `solve_optimal_tip` which takes the probability grid from the predictor.
2. **Refactor `predictor.py`**:
   - Remove the duplicate solver and point calculation logic.
   - Import the points calculator and solver from `solver.py` to maintain backwards compatibility and CLI execution support:
     ```python
     from solver import get_points, solve_optimal_tip
     ```
3. **Module Cleanliness and Decoupling**:
   - `predictor.py` focuses entirely on probabilistic modeling (Dixon-Coles, Negative Binomial, environmental factors).
   - `solver.py` focuses entirely on utility calculations, expected value search, and rule sets.
4. **Co-locating Tests**:
   - Create `tests/test_solver.py` to run unit tests specifically verifying point assignments and optimal tips under various mock probability distributions (e.g., high home win likelihood, guaranteed draw, etc.).

Below is the proposed implementation sketch for `solver.py`:

```python
# Proposed solver.py implementation

from typing import Dict, Tuple, List

def get_points(t_A: int, t_B: int, g_A: int, g_B: int) -> int:
    """
    Calculates Kicktipp points under the 4/3/2 rule set.
    """
    # 1. Exact match -> 4 points
    if t_A == g_A and t_B == g_B:
        return 4
    
    diff_tip = t_A - t_B
    diff_actual = g_A - g_B
    
    sign_tip = 1 if diff_tip > 0 else (-1 if diff_tip < 0 else 0)
    sign_actual = 1 if diff_actual > 0 else (-1 if diff_actual < 0 else 0)
    
    # 2. Correct difference -> 3 points (applies only to non-draws)
    if diff_tip == diff_actual and diff_actual != 0:
        return 3
        
    # 3. Correct tendency -> 2 points (applies to incorrect exact score wins and draws)
    if sign_tip == sign_actual:
        return 2
        
    # 4. Incorrect outcome -> 0 points
    return 0

def solve_optimal_tip(
    grid: Dict[int, Dict[int, float]],
    max_tip: int = 6
) -> Tuple[List[Tuple[Tuple[int, int], float]], List[Tuple[Tuple[int, int], float]], Tuple[float, float, float]]:
    """
    Solves for the optimal tip maximizing the expected Kicktipp points.
    
    Args:
        grid: Nested dictionary where grid[g_A][g_B] is the probability of actual score (g_A, g_B).
        max_tip: Maximum goal tip to consider (default: 6).
        
    Returns:
        1. A list of ((t_A, t_B), expected_points) sorted in descending order of EV.
        2. A list of the top 5 most likely exact scores.
        3. A tuple representing outcome probabilities: (P(Home Win), P(Draw), P(Away Win)).
    """
    expected_points = {}
    
    # 1. Calculate EV for all candidate tips in [0, max_tip] x [0, max_tip]
    for t_A in range(max_tip + 1):
        for t_B in range(max_tip + 1):
            ev = 0.0
            for g_A, row in grid.items():
                for g_B, prob in row.items():
                    pts = get_points(t_A, t_B, g_A, g_B)
                    ev += pts * prob
            expected_points[(t_A, t_B)] = ev
            
    # 2. Compute outcomes probabilities
    prob_home = sum(prob for g_A, row in grid.items() for g_B, prob in row.items() if g_A > g_B)
    prob_draw = sum(prob for g_A, row in grid.items() for g_B, prob in row.items() if g_A == g_B)
    prob_away = sum(prob for g_A, row in grid.items() for g_B, prob in row.items() if g_A < g_B)
    
    # Sort tips by EV descending
    sorted_tips = sorted(expected_points.items(), key=lambda x: x[1], reverse=True)
    
    # Sort exact scores by probability descending
    flat_probs = [((g_A, g_B), prob) for g_A, row in grid.items() for g_B, prob in row.items()]
    sorted_scores = sorted(flat_probs, key=lambda x: x[1], reverse=True)
    
    return sorted_tips, sorted_scores[:5], (prob_home, prob_draw, prob_away)
```
