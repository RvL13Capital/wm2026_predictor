## Challenge Summary

**Overall risk assessment**: LOW

## Challenges

### Low Challenge 1: Extreme alpha in Negative Binomial
- **Assumption challenged**: That the Negative Binomial distribution remains stable for arbitrarily large values of dispersion parameter `alpha`.
- **Attack scenario**: A user calls `negative_binomial_probability` with `alpha = 1e300`. This causes `1 + alpha * mu` to be extremely large, making the parameter `p = 1 / (1 + alpha * mu)` underflow to `0.0`.
- **Blast radius**: If `p` is `0.0`, then `math.log(p)` raises a `ValueError` (domain error: log of zero).
- **Mitigation**: The code successfully mitigates this by having explicit limits: `if alpha > 1e15 or alpha * mu > 1e15: return poisson_probability(k, mu)` (lines 64, 70), falling back safely before the division or underflow occurs.

### Low Challenge 2: Extremely large grid max_goals
- **Assumption challenged**: That grid calculations can scale to arbitrary sizes.
- **Attack scenario**: A user configures `max_goals = 10000`. The nested grid loops will run $10000 \times 10000 = 10^8$ times, causing high latency/CPU utilization.
- **Blast radius**: Severe latency regression.
- **Mitigation**: The code successfully mitigates this by clamping `max_goals` at `100` (`max_goals = max(0, min(100, raw_max_goals))` at line 434 and line 486).

## Stress Test Results

- **Extreme Climate Stress**: Temp=-237.3°C -> clamped to -50.0°C -> WBGT=-24.398°C -> PASS
- **Extreme Travel Stress**: Travel miles = -1e6, rest days = -1e6 -> clamped -> penalty = 0.3 -> PASS
- **Extreme Dixon-Coles Stress**: rho = -10.0, mu_a = 1.5, mu_b = 1.2 -> grid sum normalized to 1.0 -> PASS
- **Extreme Dispersion Stress**: alpha = 1e300 -> fallback to Poisson -> P(2) = 0.2707 -> PASS

## Unchallenged Areas

- Future planned components (`solver.py`, `backtest.py`) are out of scope as they have not been developed yet.
