# Adversarial Challenge Report

## Challenge Summary

**Overall risk assessment**: LOW

## Challenges

### Low Challenge 1: Numerical Stability of Underflowing Grid Probabilities
- **Assumption challenged**: That probability grid cells sum to exactly 1.0 under extreme inputs.
- **Attack scenario**: Setting very large target lambdas ($\lambda \ge 800$) can result in underflowing marginal probabilities for all $k \le \text{max\_goals}$, making the sum of the grid equal to 0.0.
- **Blast radius**: If the grid sum becomes 0.0, dividing each cell by 0.0 would crash the engine with a `ZeroDivisionError`.
- **Mitigation**: The implementers have already added a robust check in `predictor.py`:
  ```python
  total_prob = sum(sum(grid[x].values()) for x in grid)
  if total_prob > 0.0:
      ...
  else:
      # fallback when total_prob is 0.0
      grid[max_goals][max_goals] = 1.0
  ```
  This mitigates the division-by-zero risk, defaulting the probability to the top corner outcome.

### Low Challenge 2: Dixon-Coles Parameter Bounds
- **Assumption challenged**: That user-supplied or calculated Dixon-Coles parameters will not cause probabilities to go negative.
- **Attack scenario**: A very high positive or negative $\rho$ value could cause the term $(1 - \rho \cdot a_A \cdot a_B)$ or $(1 - \rho)$ to become negative.
- **Blast radius**: Negative cells in the probability grid would skew the EV optimization and produce invalid probabilities.
- **Mitigation**: The code in `predictor.py` contains:
  ```python
  return max(0.0, factor)
  ```
  This ensures the adjustment factor is non-negative.

---

## Stress Test Results

- **Extreme temperature (-237.3°C, -237.3000000000001°C)** → expected to gracefully handle potential division-by-zero when computing Wet Bulb Globe Temperature (WBGT) → **PASS** (handled via denominator checks in `calculate_wbgt`)
- **Negative travel distance and rest days** → expected to handle negative inputs without causing negative travel penalties or domain errors → **PASS** (handled via `max(0.0, ...)` limits in `calculate_travel_penalty`)
- **Zero lambda value** → expected to yield $0:0$ as the certain outcome (probability 1.0) and not trigger division by zero in Dixon-Coles or Poisson functions → **PASS**

---

## Unchallenged Areas

- **Backtester performance with real World Cup 2022 dataset** — reason not challenged: Data and backtesting code were not implemented yet (Milestone 4 scope).
