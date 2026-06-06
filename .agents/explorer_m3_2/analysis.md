# Analysis & Recommendations: Kicktipp Solver (Milestone 3)

## 1. Overview of the Kicktipp Solver
The objective of Milestone 3 is to implement the Kicktipp Solver in `solver.py`. 
The solver's job is to take a joint probability distribution over match scores $(g_A, g_B)$ from the prediction engine (`predictor.py`) and determine the tip $(t_A, t_B)$ up to `max_tip` that maximizes the expected points under the Kicktipp **4/3/2** scoring rules.

---

## 2. Codebase Analysis & Current Implementation

### 2.1 Current `solve_optimal_tip` Implementation
Currently, `solve_optimal_tip` is located in `predictor.py` (lines 463–523) and performs:
1. **Grid Generation**: Calls `generate_joint_grid(config)` to compute the normalized joint probability matrix $P(g_A, g_B)$ up to `max_goals`.
2. **Parameters Clamping**: Clamps `max_goals` and `max_tip` within $[0, 100]$.
3. **Double Loop search**: Loops over all possible tips $(t_A, t_B)$ up to `max_tip` and all actual scores $(g_A, g_B)$ up to `max_goals` to calculate the expected value $E(t_A, t_B)$.
4. **Aggregate Outcomes**: Calculates overall probabilities $P(\text{Home})$, $P(\text{Draw})$, and $P(\text{Away})$.
5. **Sorting**: Sorts tips by expected value descending and returns:
   - `sorted_tips`: list of `((t_A, t_B), expected_points)`
   - `sorted_scores`: list of top 5 exact scores by probability
   - `outcomes`: tuple of `(prob_home, prob_draw, prob_away)`

### 2.2 Interface Contract: `predictor.py` ↔ `solver.py`
As defined in `PROJECT.md`, the interface contract expects:
- **Prediction engine (`predictor.py`)** to output the full probability distribution over scores (the grid of size `(max_goals + 1) * (max_goals + 1)`).
- **Solver (`solver.py`)** to consume this grid (and `max_tip`) and output the optimal tip.

To preserve backwards compatibility with the existing test suite (which imports `predictor` and calls `predictor.solve_optimal_tip(...)`), we recommend:
1. Implementing the mathematical optimization engine in `solver.py`.
2. Having `predictor.py` import `solver` and delegate the actual search logic of `solve_optimal_tip` to `solver.py`.

---

## 3. Mathematical Formulation of expected Value (EV)

The Kicktipp scoring system rules are:
- **4 Points**: Exact score ($t_A = g_A$ and $t_B = g_B$)
- **3 Points**: Correct goal difference and tendency ($t_A - t_B = g_A - g_B$ and $\text{sign}(t_A - t_B) = \text{sign}(g_A - g_B)$ where $t_A \neq t_B$)
- **2 Points**: Correct tendency only ($\text{sign}(t_A - t_B) = \text{sign}(g_A - g_B)$)
- **0 Points**: Otherwise

Let $P(g_A, g_B)$ be the joint probability of score $g_A:g_B$, where $0 \le g_A, g_B \le N$ ($N = \text{max\_goals}$).
For a given tip $t = (t_A, t_B)$ with difference $d = t_A - t_B$:

### 3.1 Draw Tip Case ($t_A = t_B \implies d = 0$)
Under the Kicktipp rules, a different draw (e.g. tipping 1-1 when it ends 2-2) only yields **2 points** (tendency), not 3 points (difference). Therefore:
- Exact draw ($g_A = t_A, g_B = t_A$) yields $4$ points.
- Any other draw ($g_A = g_B \neq t_A$) yields $2$ points.
- Non-draw outcomes ($g_A \neq g_B$) yield $0$ points.

Thus, the expected value is:
$$E(t_A, t_A) = 4 P(t_A, t_A) + 2 \sum_{g \neq t_A} P(g, g) = 2 P(\text{Draw}) + 2 P(t_A, t_A)$$
where $P(\text{Draw}) = \sum_{g=0}^{N} P(g, g)$.

### 3.2 Home Win Tip Case ($t_A > t_B \implies d > 0$)
- Exact score $(t_A, t_B)$ yields $4$ points.
- Correct goal difference $d$ but not exact (i.e. $g_A - g_B = d$ and $g_A \neq t_A$) yields $3$ points.
- Correct tendency (home win) but incorrect goal difference yields $2$ points.
- Draw or away win yields $0$ points.

Let $P(\text{Home}) = \sum_{g_A > g_B} P(g_A, g_B)$ and $P(\text{Diff} = d) = \sum_{g_A - g_B = d} P(g_A, g_B)$.
The expected value is:
$$E(t_A, t_B) = 4 P(t_A, t_B) + 3 [P(\text{Diff} = d) - P(t_A, t_B)] + 2 [P(\text{Home}) - P(\text{Diff} = d)]$$
$$E(t_A, t_B) = P(t_A, t_B) + P(\text{Diff} = d) + 2 P(\text{Home})$$

### 3.3 Away Win Tip Case ($t_A < t_B \implies d < 0$)
By symmetry, let $P(\text{Away}) = \sum_{g_A < g_B} P(g_A, g_B)$ and $P(\text{Diff} = d) = \sum_{g_A - g_B = d} P(g_A, g_B)$.
The expected value is:
$$E(t_A, t_B) = P(t_A, t_B) + P(\text{Diff} = d) + 2 P(\text{Away})$$

---

## 4. Algorithms Comparison

We propose two computational approaches for the solver:

### Algorithm 1: Naive Grid Iteration
Iterates over all tips and all actual outcomes directly.

```python
# Complexity: O(T^2 * N^2)
expected_points = {}
for t_a in range(max_tip + 1):
    for t_b in range(max_tip + 1):
        ev = 0.0
        for g_a in range(max_goals + 1):
            for g_b in range(max_goals + 1):
                pts = get_points(t_a, t_b, g_a, g_b)
                ev += pts * grid.get(g_a, {}).get(g_b, 0.0)
        expected_points[(t_a, t_b)] = ev
```

### Algorithm 2: Optimized Aggregate Search
Precomputes cumulative/marginal probabilities and calculates EV in $O(1)$ per tip.

```python
# Complexity: O(N^2 + T^2)
# 1. Precompute aggregate outcome probabilities
p_home = 0.0
p_away = 0.0
p_draw = 0.0
p_diff = {} # maps diff to probability

for g_a in range(max_goals + 1):
    for g_b in range(max_goals + 1):
        prob = grid.get(g_a, {}).get(g_b, 0.0)
        diff = g_a - g_b
        p_diff[diff] = p_diff.get(diff, 0.0) + prob
        if diff > 0:
            p_home += prob
        elif diff < 0:
            p_away += prob
        else:
            p_draw += prob

# 2. Evaluate tips in constant time
expected_points = {}
for t_a in range(max_tip + 1):
    for t_b in range(max_tip + 1):
        diff = t_a - t_b
        # Retrieve exact score probability (treat as 0 if out-of-grid bounds)
        p_exact = grid.get(t_a, {}).get(t_b, 0.0)
        p_d = p_diff.get(diff, 0.0)
        
        if diff > 0:
            ev = p_exact + p_d + 2.0 * p_home
        elif diff < 0:
            ev = p_exact + p_d + 2.0 * p_away
        else:
            ev = 2.0 * p_exact + 2.0 * p_draw
        expected_points[(t_a, t_b)] = ev
```

### Comparison Matrix

| Criteria | Algorithm 1: Naive Grid Search | Algorithm 2: Optimized Search |
|---|---|---|
| **Time Complexity** | $O(T^2 \cdot N^2)$ | $O(N^2 + T^2)$ |
| **Standard Cost ($T=6, N=12$)** | 8,281 loop iterations | $169 + 49 = 218$ loop iterations |
| **Large Grid Cost ($T=10, N=100$)** | $121 \times 10,201 = 1,234,321$ iterations | $10,201 + 121 = 10,322$ iterations |
| **Implementation Simplicity** | Very high | Moderate |
| **Extensibility / Flexibility** | Easy to adapt if scoring rules change. | Requires re-deriving algebraic simplification. |
| **Robustness to Bounds** | Naturally handles $T > N$. | Needs manual clamping for $p\_exact$ index. |

---

## 5. Proposed Implementation Plan for `solver.py`

We recommend writing `solver.py` to support **both** algorithms. During execution, it should run the optimized search by default but compare the output with the naive search under a debug/verification flag to guarantee mathematical correctness.

### Recommended `solver.py` structure:
```python
import math
from typing import Dict, Tuple, List

def sign(val: float) -> int:
    return 1 if val > 0 else (-1 if val < 0 else 0)

def get_points(t_a: int, t_b: int, g_a: int, g_b: int) -> int:
    if t_a == g_a and t_b == g_b:
        return 4
    
    diff_actual = g_a - g_b
    diff_tip = t_a - t_b
    
    if diff_actual == diff_tip:
        if diff_actual == 0:
            return 2
        return 3
    elif sign(diff_actual) == sign(diff_tip):
        return 2
    return 0

def solve_optimal_tip_from_grid(
    grid: Dict[int, Dict[int, float]],
    max_goals: int,
    max_tip: int,
    use_optimized: bool = True
) -> Tuple[List[Tuple[Tuple[int, int], float]], List[Tuple[Tuple[int, int], float]], Tuple[float, float, float]]:
    """
    Computes optimal Kicktipp tips from a joint score probability distribution grid.
    """
    # Clamping & bounds checks
    max_goals_clamped = max(0, min(100, int(max_goals)))
    max_tip_clamped = max(0, min(100, int(max_tip)))
    
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    
    if use_optimized:
        p_diff = {}
        for g_a in range(max_goals_clamped + 1):
            for g_b in range(max_goals_clamped + 1):
                prob = grid.get(g_a, {}).get(g_b, 0.0)
                diff = g_a - g_b
                p_diff[diff] = p_diff.get(diff, 0.0) + prob
                if diff > 0:
                    p_home += prob
                elif diff < 0:
                    p_away += prob
                else:
                    p_draw += prob
                    
        expected_points = {}
        for t_a in range(max_tip_clamped + 1):
            for t_b in range(max_tip_clamped + 1):
                diff = t_a - t_b
                p_exact = grid.get(t_a, {}).get(t_b, 0.0)
                p_d = p_diff.get(diff, 0.0)
                
                if diff > 0:
                    ev = p_exact + p_d + 2.0 * p_home
                elif diff < 0:
                    ev = p_exact + p_d + 2.0 * p_away
                else:
                    ev = 2.0 * p_exact + 2.0 * p_draw
                expected_points[(t_a, t_b)] = ev
    else:
        # Naive implementation
        expected_points = {}
        for t_a in range(max_tip_clamped + 1):
            for t_b in range(max_tip_clamped + 1):
                ev = 0.0
                for g_a in range(max_goals_clamped + 1):
                    for g_b in range(max_goals_clamped + 1):
                        pts = get_points(t_a, t_b, g_a, g_b)
                        ev += pts * grid.get(g_a, {}).get(g_b, 0.0)
                expected_points[(t_a, t_b)] = ev
                
        # Calculate outcome probabilities anyway
        for g_a in range(max_goals_clamped + 1):
            for g_b in range(max_goals_clamped + 1):
                prob = grid.get(g_a, {}).get(g_b, 0.0)
                if g_a > g_b:
                    p_home += prob
                elif g_a < g_b:
                    p_away += prob
                else:
                    p_draw += prob

    sorted_tips = sorted(expected_points.items(), key=lambda x: x[1], reverse=True)
    
    # Sort exact scores by probability
    flat_probs = []
    for g_a in range(max_goals_clamped + 1):
        for g_b in range(max_goals_clamped + 1):
            flat_probs.append(((g_a, g_b), grid.get(g_a, {}).get(g_b, 0.0)))
    sorted_scores = sorted(flat_probs, key=lambda x: x[1], reverse=True)
    
    return sorted_tips, sorted_scores, (p_home, p_draw, p_away)
```

---

## 6. Verification Method & Testing Recommendations

To verify this implementation once written:
1. **Verification Command**:
   `pytest tests/test_tier1_feature_coverage.py` should run successfully and ensure the interface behaves correctly.
2. **Cross-Algorithm Invariance**:
   Write a unit test that runs both `use_optimized=True` and `use_optimized=False` on multiple randomized probability grids (under Poisson, Negative Binomial, and extreme parameters) and asserts that the sorted tips and EVs are identical down to floating-point precision ($10^{-9}$).
3. **Boundary Check**:
   Test behavior when `max_tip > max_goals` to ensure no `KeyError` or index bounds problems occur during optimized search.
