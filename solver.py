# solver.py
import math
from typing import Dict, Tuple, List, Union

def sign(val: Union[int, float]) -> int:
    return 1 if val > 0 else (-1 if val < 0 else 0)

def is_integer_like(val) -> bool:
    if isinstance(val, (int, float)):
        return not math.isnan(val) and not math.isinf(val) and float(val).is_integer()
    return False

def flatten_grid(grid) -> List[Tuple[int, int, float]]:
    flat = []
    if isinstance(grid, dict):
        for r, row in grid.items():
            if isinstance(row, dict):
                for c, val in row.items():
                    flat.append((int(r), int(c), val))
            elif isinstance(row, (list, tuple)):
                for c, val in enumerate(row):
                    flat.append((int(r), int(c), val))
    elif isinstance(grid, (list, tuple)):
        for r, row in enumerate(grid):
            if isinstance(row, dict):
                for c, val in row.items():
                    flat.append((int(r), int(c), val))
            elif isinstance(row, (list, tuple)):
                for c, val in enumerate(row):
                    flat.append((int(r), int(c), val))
    return flat

def get_grid_val(grid, r: int, c: int) -> float:
    try:
        if isinstance(grid, dict):
            row = grid.get(r)
        elif isinstance(grid, list):
            if r < 0 or r >= len(grid):
                return 0.0
            row = grid[r]
        else:
            return 0.0

        if row is None:
            return 0.0

        if isinstance(row, dict):
            if c not in row:
                return 0.0
            val = row[c]
        elif isinstance(row, list):
            if c < 0 or c >= len(row):
                return 0.0
            val = row[c]
        else:
            return 0.0
            
        if val is None:
            raise TypeError("Grid contains None value")
        return float(val)
    except TypeError as te:
        raise te
    except Exception:
        return 0.0

def get_points(t_a: int, t_b: int, g_a: int, g_b: int) -> int:
    """
    Calculates tipping points according to the rules:
    - 4 points: Exact score (t_a == g_a and t_b == g_b)
    - 3 points: Correct goal difference and tendency (non-draws only)
    - 2 points: Correct tendency or non-exact draw on a draw outcome
    - 0 points: Otherwise
    """
    if not (is_integer_like(t_a) and is_integer_like(t_b) and is_integer_like(g_a) and is_integer_like(g_b)):
        return 0

    t_a = int(t_a)
    t_b = int(t_b)
    g_a = int(g_a)
    g_b = int(g_b)

    if t_a == g_a and t_b == g_b:
        return 4
    
    diff_actual = g_a - g_b
    diff_tip = t_a - t_b
    
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

def solve_optimal_tip_from_grid(
    grid: Union[Dict[int, Dict[int, float]], List[List[float]]], 
    max_tip: int
) -> Tuple[List[Tuple[Tuple[int, int], float]], List[Tuple[Tuple[int, int], float]], Tuple[float, float, float]]:
    """
    Solves for the optimal tip (t_a, t_b) maximizing Expected Value (EV) from a goal probability grid.
    Uses an optimized aggregate search algorithm in O(N^2 + T^2) complexity.
    
    Returns:
    - sorted_tips: List of ((t_a, t_b), ev) sorted by EV descending
    - sorted_scores: List of ((g_a, g_b), prob) sorted by probability descending
    - outcomes: Tuple of (prob_home, prob_draw, prob_away)
    """
    try:
        max_tip = int(max_tip)
    except (TypeError, ValueError):
        raise TypeError("max_tip must be an integer")

    flat = flatten_grid(grid)
    
    prob_home = 0.0
    prob_draw = 0.0
    prob_away = 0.0
    diff_probs = {}
    flat_probs = []
    
    for r, c, val in flat:
        if val is None:
            raise TypeError("Grid contains None value")
        
        val = float(val)
        
        if r > c:
            prob_home += val
        elif r == c:
            prob_draw += val
        else:
            prob_away += val
            
        diff = r - c
        diff_probs[diff] = diff_probs.get(diff, 0.0) + val
        flat_probs.append(((r, c), val))
        
    # Sort exact scores by probability descending
    sorted_scores = sorted(flat_probs, key=lambda x: x[1], reverse=True)
    
    # Calculate EV for each tip (t_a, t_b) in 0..max_tip
    expected_points = {}
    for t_a in range(max_tip + 1):
        for t_b in range(max_tip + 1):
            p_t = get_grid_val(grid, t_a, t_b)
            
            d = t_a - t_b
            if d > 0:
                ev = p_t + diff_probs.get(d, 0.0) + 2.0 * prob_home
            elif d < 0:
                ev = p_t + diff_probs.get(d, 0.0) + 2.0 * prob_away
            else:
                ev = 2.0 * p_t + 2.0 * prob_draw
                
            expected_points[(t_a, t_b)] = ev
            
    sorted_tips = sorted(expected_points.items(), key=lambda x: x[1] if not math.isnan(x[1]) else -float('inf'), reverse=True)
    
    return sorted_tips, sorted_scores, (prob_home, prob_draw, prob_away)
