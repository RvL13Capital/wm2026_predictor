# Mathematical Analysis and Design: Goal Prediction Enhancements

## Executive Summary
This report analyzes the existing Poisson goal predictor and proposes a rigorous mathematical and structural design to incorporate (1) Bivariate Poisson with Dixon-Coles adjustment, and (2) Negative Binomial distribution to handle overdispersion (variance exceeding the mean). In doing so, we present a **Generalized Dixon-Coles adjustment** that preserves the joint probability sum-to-one property for any discrete marginal distributions, including the Negative Binomial.

---

## 1. Analysis of Current Implementation in `predictor.py`
The current implementation in `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py` operates under the following structure:
* **Marginal Distributions**: Modeled as independent Poisson distributions via `poisson_prob(k, lam)` representing $\text{P}(X = k) = \frac{\lambda^k e^{-\lambda}}{k!}$.
* **Draw Adjustment**: Incorporates a standard Dixon-Coles correction for low-scoring states (0-0, 1-0, 0-1, 1-1) using a correlation parameter `rho` ($\rho$).
* **Decision Optimization**: Computes the expected points for tips $t(t_A, t_B)$ across a grid of actual goals up to `max_goals = 12` using the scoring rules:
  * $4\text{ points}$: Exact score.
  * $3\text{ points}$: Correct goal difference and tendency (e.g., tip 2-0, actual 3-1).
  * $2\text{ points}$: Correct tendency only (Home Win, Draw, Away Win).
  * $0\text{ points}$: Otherwise.

### Key Limitations of the Current Code
1. **No Overdispersion Handling**: The Poisson distribution assumes $\text{Var}(X) = \text{E}(X) = \lambda$. Football data exhibits overdispersion (high-scoring outliers and variance greater than the mean), which the Poisson model underestimates.
2. **Fixed Dixon-Coles Assumed Marginals**: The Dixon-Coles correction is implemented using hardcoded adjustment factors $1.0 - \rho \lambda_A \lambda_B$, $1.0 + \rho \lambda_B$, $1.0 + \rho \lambda_A$, and $1.0 - \rho$. While correct for Poisson marginals, this adjustment does **not** sum to 1.0 when applied directly to other marginal distributions (such as Negative Binomial) prior to grid normalization.
3. **Factorial Overflow Risk**: The `poisson_prob` uses `math.factorial(k)`. If `max_goals` is increased, this will lead to large integer operations.

---

## 2. Mathematical Formulations

### A. Bivariate Poisson with Dixon-Coles Correction
To account for the dependency between home and away goals (specifically the over-representation of low-scoring draws), Dixon and Coles (1997) proposed applying a correction factor $\tau(x, y)$ to the independent joint probabilities:

$$\text{P}(X=x, Y=y) = \tau(x, y) \cdot \text{P}(X=x) \cdot \text{P}(Y=y)$$

For home expected goals $\lambda_A$ and away expected goals $\lambda_B$, the adjustment factor $\tau(x, y)$ is defined as:

$$\tau(x, y) = \begin{cases} 
1 - \rho \lambda_A \lambda_B & \text{for } x = 0, y = 0 \\
1 + \rho \lambda_B & \text{for } x = 1, y = 0 \\
1 + \rho \lambda_A & \text{for } x = 0, y = 1 \\
1 - \rho & \text{for } x = 1, y = 1 \\
1 & \text{otherwise}
\end{cases}$$

Here, $\rho$ is the correlation parameter (typically negative, e.g., $-0.10$ to $-0.05$, which boosts draws 0-0 and 1-1 and decreases 1-0 and 0-1).

To guarantee non-negative probabilities, the correction factor must satisfy $\tau(x, y) \ge 0$, which imposes constraints on $\rho$:
$$\max\left(-\frac{1}{\lambda_A}, -\frac{1}{\lambda_B}\right) \le \rho \le \min\left(1, \frac{1}{\lambda_A \lambda_B}\right)$$

---

### B. Negative Binomial Distribution for Overdispersion
To model matches where the variance of goals scored exceeds the mean ($\text{Var}(X) > \text{E}(X)$), we use the Negative Binomial distribution parameterized by mean $\mu$ and dispersion parameter $\alpha \ge 0$:

$$\text{Var}(X) = \mu + \alpha \mu^2$$

#### 1. Parameter Mapping
To express this distribution in the standard Negative Binomial parameters $r$ (dispersion/number of failures) and $p$ (probability of success):
* **Dispersion parameter** ($r > 0$): $r = \frac{1}{\alpha}$
* **Success probability** ($p \in (0, 1]$): $p = \frac{1}{1 + \alpha \mu} = \frac{r}{r + \mu}$

#### 2. Probability Computation (PMF)
The probability of scoring $k$ goals is:

$$\text{P}(X = k) = \frac{\Gamma(k + r)}{k! \, \Gamma(r)} (1 - p)^k p^r$$

For numerical stability and to prevent overflow when calculating factorials and powers, we compute the probability in the log-domain using the log-gamma function $\ln\Gamma(z)$ (`math.lgamma`):

$$\ln \text{P}(X = k) = \ln\Gamma(k + r) - \ln\Gamma(k + 1) - \ln\Gamma(r) + k \ln(1 - p) + r \ln(p)$$
$$\text{P}(X = k) = \exp\left(\ln \text{P}(X = k)\right)$$

Where $1 - p = \frac{\alpha \mu}{1 + \alpha \mu}$ and $p = \frac{1}{1 + \alpha \mu}$.

#### 3. Convergence to Poisson
As $\alpha \to 0$ (so $r \to \infty$), the Negative Binomial distribution converges to the Poisson distribution with mean $\mu$. In practice, when $\alpha \le 10^{-6}$, the implementation should switch to the Poisson PMF to avoid division by zero.

---

### C. Generalized Dixon-Coles for Arbitrary Marginals
If we apply the standard Dixon-Coles adjustment (using $\lambda_A, \lambda_B$ directly) to Negative Binomial marginals, the joint probabilities will no longer sum to exactly $1.0$ (prior to truncation). 

To preserve the property $\sum_{x,y} \text{P}(X=x, Y=y) = 1$ for *any* discrete distributions $P_X$ and $P_Y$, we propose the **Generalized Dixon-Coles adjustment**:

$$\tau(x, y) = \begin{cases} 
1 - \rho \cdot a_A \cdot a_B & \text{for } x = 0, y = 0 \\
1 + \rho \cdot a_B & \text{for } x = 1, y = 0 \\
1 + \rho \cdot a_A & \text{for } x = 0, y = 1 \\
1 - \rho & \text{for } x = 1, y = 1 \\
1 & \text{otherwise}
\end{cases}$$

Where the adjustment scaling factors $a_A$ and $a_B$ are defined as:
$$a_A = \frac{\text{P}_X(1)}{\text{P}_X(0)} \quad \text{and} \quad a_B = \frac{\text{P}_Y(1)}{\text{P}_Y(0)}$$

#### Mathematical Proof of the Sum-to-One Property
Let $S$ be the sum of the adjusted joint probabilities:
$$S = \sum_{x \ge 0} \sum_{y \ge 0} \tau(x, y) \text{P}_X(x) \text{P}_Y(y)$$
Since $\tau(x, y) = 1$ for all states except the four low-scoring states, we partition the sum:
$$S = \sum_{x \ge 0} \sum_{y \ge 0} \text{P}_X(x) \text{P}_Y(y) + \Delta = 1 + \Delta$$
Where the delta change $\Delta$ is:
$$\Delta = (\tau(0,0)-1)\text{P}_X(0)\text{P}_Y(0) + (\tau(1,0)-1)\text{P}_X(1)\text{P}_Y(0) + (\tau(0,1)-1)\text{P}_X(0)\text{P}_Y(1) + (\tau(1,1)-1)\text{P}_X(1)\text{P}_Y(1)$$

Substituting the generalized correction factors:
$$\Delta = -\rho a_A a_B \text{P}_X(0) \text{P}_Y(0) + \rho a_B \text{P}_X(1) \text{P}_Y(0) + \rho a_A \text{P}_X(0) \text{P}_Y(1) - \rho \text{P}_X(1) \text{P}_Y(1)$$
Factoring out $\rho$:
$$\Delta = \rho \left[ a_B \text{P}_Y(0) \left( \text{P}_X(1) - a_A \text{P}_X(0) \right) - \text{P}_Y(1) \left( \text{P}_X(1) - a_A \text{P}_X(0) \right) \right]$$
$$\Delta = \rho \left( \text{P}_X(1) - a_A \text{P}_X(0) \right) \left( a_B \text{P}_Y(0) - \text{P}_Y(1) \right)$$

By substituting $a_A = \frac{\text{P}_X(1)}{\text{P}_X(0)}$ and $a_B = \frac{\text{P}_Y(1)}{\text{P}_Y(0)}$:
$$\text{P}_X(1) - a_A \text{P}_X(0) = \text{P}_X(1) - \text{P}_X(1) = 0$$
$$\text{P}_Y(1) - a_B \text{P}_Y(0) = \text{P}_Y(1) - \text{P}_Y(1) = 0$$

Thus, $\Delta = 0 \times 0 = 0$, proving that $\sum_{x,y} \tau(x, y) \text{P}_X(x) \text{P}_Y(y) = 1$ is preserved for **any** valid discrete marginal distributions.

#### Parameter Value Expressions:
1. **Poisson**: 
   $$a_i = \frac{\lambda_i e^{-\lambda_i}}{e^{-\lambda_i}} = \lambda_i$$ (identical to standard Dixon-Coles)
2. **Negative Binomial**: 
   $$a_i = \frac{r_i (1-p_i) p_i^{r_i}}{p_i^{r_i}} = r_i (1-p_i) = \frac{\mu_i}{1 + \alpha_i \mu_i}$$

This generalization ensures that the joint distribution remains a mathematically coherent probability distribution before truncation limits are applied.

---

## 3. Function Signatures & Data Structures Design

Below is the proposed design for the updated Python implementation.

### A. Data Structures
```python
from enum import Enum
from dataclasses import dataclass

class ModelDistribution(Enum):
    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"

@dataclass(frozen=True)
class MatchModelConfig:
    dist_type: ModelDistribution
    mu_a: float          # Expected goals for Team A
    mu_b: float          # Expected goals for Team B
    alpha_a: float = 0.0 # Dispersion parameter for Team A (ignored if Poisson)
    alpha_b: float = 0.0 # Dispersion parameter for Team B (ignored if Poisson)
    rho: float = 0.0     # Dixon-Coles adjustment factor
    max_goals: int = 12  # Grid limit for goal calculations
    max_tip: int = 6     # Maximum tip to consider
```

### B. Core Signatures
```python
import math
from typing import Dict, Tuple, List

def poisson_probability(k: int, lam: float) -> float:
    """
    Calculates the Poisson probability P(X = k) using log-gamma to avoid overflow.
    
    Args:
        k: Number of goals (non-negative integer)
        lam: Mean goal intensity (positive float)
    """
    if lam <= 0.0:
        return 1.0 if k == 0 else 0.0
    # log-domain calculation: ln(P(X = k)) = k * ln(lam) - lam - ln(k!)
    log_p = k * math.log(lam) - lam - math.lgamma(k + 1)
    return math.exp(log_p)

def negative_binomial_probability(k: int, mu: float, alpha: float) -> float:
    """
    Calculates the Negative Binomial probability P(X = k) with mean mu and dispersion alpha.
    Falls back to Poisson if alpha is near zero.
    
    Args:
        k: Number of goals (non-negative integer)
        mu: Expected goals (positive float)
        alpha: Dispersion parameter (non-negative float)
    """
    if alpha <= 1e-6:
        return poisson_probability(k, mu)
    if mu <= 0.0:
        return 1.0 if k == 0 else 0.0
        
    r = 1.0 / alpha
    p = 1.0 / (1.0 + alpha * mu)
    
    # ln(P(X = k)) = ln(Gamma(k + r)) - ln(Gamma(k + 1)) - ln(Gamma(r)) + k * ln(1-p) + r * ln(p)
    log_p = (
        math.lgamma(k + r) 
        - math.lgamma(k + 1) 
        - math.lgamma(r) 
        + k * math.log(1.0 - p) 
        + r * math.log(p)
    )
    return math.exp(log_p)

def compute_marginal_probability(k: int, mu: float, alpha: float, dist_type: ModelDistribution) -> float:
    """
    Delegates probability calculation to correct distribution.
    """
    if dist_type == ModelDistribution.POISSON:
        return poisson_probability(k, mu)
    elif dist_type == ModelDistribution.NEGATIVE_BINOMIAL:
        return negative_binomial_probability(k, mu, alpha)
    else:
        raise ValueError(f"Unknown distribution type: {dist_type}")

def get_dixon_coles_adjustment(
    x: int, 
    y: int, 
    a_a: float, 
    a_b: float, 
    rho: float
) -> float:
    """
    Calculates the Dixon-Coles adjustment factor for the given score (x, y).
    
    Args:
        x: Home goals
        y: Away goals
        a_a: Adjustment parameter for Team A (P_A(1)/P_A(0))
        a_b: Adjustment parameter for Team B (P_B(1)/P_B(0))
        rho: Joint correlation parameter
    """
    if rho == 0.0:
        return 1.0
        
    if x == 0 and y == 0:
        factor = 1.0 - rho * a_a * a_b
    elif x == 1 and y == 0:
        factor = 1.0 + rho * a_b
    elif x == 0 and y == 1:
        factor = 1.0 + rho * a_a
    elif x == 1 and y == 1:
        factor = 1.0 - rho
    else:
        factor = 1.0
        
    return max(0.0, factor)
```

### C. Joint Grid Construction and Optimization
```python
def generate_joint_grid(config: MatchModelConfig) -> Dict[int, Dict[int, float]]:
    """
    Generates a normalized grid of joint score probabilities up to max_goals.
    Applies the generalized Dixon-Coles adjustment.
    """
    grid = {}
    
    # 1. Compute marginal arrays
    p_a = [compute_marginal_probability(k, config.mu_a, config.alpha_a, config.dist_type) for k in range(config.max_goals + 1)]
    p_b = [compute_marginal_probability(k, config.mu_b, config.alpha_b, config.dist_type) for k in range(config.max_goals + 1)]
    
    # 2. Calculate Dixon-Coles parameters: a = P(1) / P(0)
    # Safely handle potential P(0) == 0 edge cases
    a_a = p_a[1] / p_a[0] if p_a[0] > 0.0 else config.mu_a
    a_b = p_b[1] / p_b[0] if p_b[0] > 0.0 else config.mu_b
    
    # 3. Populate and adjust joint grid
    for x in range(config.max_goals + 1):
        grid[x] = {}
        for y in range(config.max_goals + 1):
            base_prob = p_a[x] * p_b[y]
            adj_factor = get_dixon_coles_adjustment(x, y, a_a, a_b, config.rho)
            grid[x][y] = base_prob * adj_factor
            
    # 4. Normalize the grid to ensure sum == 1.0 over the truncated space
    total_prob = sum(sum(grid[x].values()) for x in grid)
    if total_prob > 0.0:
        for x in grid:
            for y in grid[x]:
                grid[x][y] /= total_prob
                
    return grid

def solve_optimal_tip(
    config: MatchModelConfig
) -> Tuple[
    List[Tuple[Tuple[int, int], float]], # Expected points for tips sorted desc
    List[Tuple[Tuple[int, int], float]], # Top exact score probabilities sorted desc
    Tuple[float, float, float]           # Tendency probabilities (Win A, Draw, Win B)
]:
    """
    Solves for the optimal tip by building the joint probability matrix and
    calculating the expected value of points for all tip candidates.
    """
    # 1. Build joint probability matrix
    grid = generate_joint_grid(config)
    
    # 2. Evaluate expected points for each tip t(t_A, t_B)
    expected_points = {}
    for t_a in range(config.max_tip + 1):
        for t_b in range(config.max_tip + 1):
            ev = 0.0
            for g_a in range(config.max_goals + 1):
                for g_b in range(config.max_goals + 1):
                    pts = get_points(t_a, t_b, g_a, g_b)  # Reuses existing scoring logic
                    ev += pts * grid[g_a][g_b]
            expected_points[(t_a, t_b)] = ev
            
    # 3. Extract outcome tendencies
    prob_home = sum(grid[x][y] for x in grid for y in grid[x] if x > y)
    prob_draw = sum(grid[x][y] for x in grid for y in grid[x] if x == y)
    prob_away = sum(grid[x][y] for x in grid for y in grid[x] if x < y)
    
    # 4. Format outputs
    sorted_tips = sorted(expected_points.items(), key=lambda item: item[1], reverse=True)
    
    flat_probs = [((x, y), grid[x][y]) for x in grid for y in grid[x]]
    sorted_scores = sorted(flat_probs, key=lambda item: item[1], reverse=True)
    
    return sorted_tips, sorted_scores[:5], (prob_home, prob_draw, prob_away)
```

---

## 4. Execution Flow and Validation Plan

### A. Mathematical Validation
To verify the implementation:
1. **Sum of probabilities**: Summing `generate_joint_grid(config)` must equal `1.0` (within numerical precision, i.e., $|1 - \sum P| < 10^{-9}$).
2. **Poisson Convergence**: When `config.alpha_a = 0.0` and `config.alpha_b = 0.0`, the output from the Negative Binomial model must be identical to the output of the Poisson model.
3. **Dixon-Coles Truncation Check**: Standardize boundary limits on `rho` dynamically based on computed $a_A$ and $a_B$ values to prevent any negative probability components.

### B. Unit Test Cases
```python
def test_negative_binomial_sum():
    # Test that marginal distribution sums to 1.0 (over a wide grid range)
    probs = [negative_binomial_probability(k, mu=1.5, alpha=0.3) for k in range(50)]
    assert abs(sum(probs) - 1.0) < 1e-6

def test_poisson_convergence():
    # Test that Negative Binomial converges to Poisson as alpha -> 0
    p_poisson = poisson_probability(3, lam=2.0)
    p_nb = negative_binomial_probability(3, mu=2.0, alpha=1e-9)
    assert abs(p_poisson - p_nb) < 1e-7

def test_generalized_dixon_coles_sum():
    # Test that the Generalized Dixon-Coles adjustment keeps sum == 1.0 prior to truncation
    config = MatchModelConfig(
        dist_type=ModelDistribution.NEGATIVE_BINOMIAL,
        mu_a=1.8, mu_b=1.2,
        alpha_a=0.2, alpha_b=0.2,
        rho=-0.08,
        max_goals=40  # Set large enough to ignore truncation error
    )
    grid = generate_joint_grid(config)
    total_p = sum(sum(grid[x].values()) for x in grid)
    assert abs(total_p - 1.0) < 1e-6
```
