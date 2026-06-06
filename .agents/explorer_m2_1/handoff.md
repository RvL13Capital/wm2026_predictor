# Handoff Report — explorer_m2_1

## 1. Observation
- File location: `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`
- Current implementation contains a Poisson-based bivariate model with Dixon-Coles adjustments.
  - In `predictor.py` (lines 56–64):
    ```python
    if rho != 0.0 and lam_A > 0 and lam_B > 0:
        adjustment = {
            (0, 0): 1.0 - rho * lam_A * lam_B,
            (1, 0): 1.0 + rho * lam_B,
            (0, 1): 1.0 + rho * lam_A,
            (1, 1): 1.0 - rho
        }
        for (a, b), factor in adjustment.items():
            P[a][b] *= max(0.0, factor)
    ```
- Fact: Football match goal statistics exhibit overdispersion where the variance of goals scored is larger than the mean ($\text{Var}(X) > \text{E}(X)$), which cannot be modeled by a Poisson distribution since $\text{Var}(X) = \text{E}(X) = \lambda$.
- Mathematical formulation: Under the Negative Binomial distribution parameterized by mean $\mu$ and dispersion $\alpha$, the variance is $\text{Var}(X) = \mu + \alpha \mu^2$. The PMF is given by:
  $$\text{P}(X=k) = \frac{\Gamma(k + r)}{k!\Gamma(r)} (1-p)^k p^r$$
  where $r = 1/\alpha$ and $p = 1 / (1 + \alpha\mu)$.
- Analysis finding: Applying standard Dixon-Coles adjustment factors $1 - \rho \mu_A \mu_B$, $1 + \rho \mu_B$, etc., to Negative Binomial marginals does not preserve the sum-to-one joint probability distribution property prior to truncation/normalization because:
  $$\text{P}_X(1) \ne \mu_A \text{P}_X(0)$$
  for Negative Binomial marginals.
- Mathematical proof/derivation: We solved for a **Generalized Dixon-Coles adjustment** by introducing scaling factors $a_A = \text{P}_X(1)/\text{P}_X(0)$ and $a_B = \text{P}_Y(1)/\text{P}_Y(0)$. Under this generalization, the sum-to-one property holds exactly because:
  $$\Delta = \rho \left( \text{P}_X(1) - a_A \text{P}_X(0) \right) \left( a_B \text{P}_Y(0) - \text{P}_Y(1) \right) = \rho (0) (0) = 0$$
  This yields:
  - For Poisson: $a_i = \lambda_i$
  - For Negative Binomial: $a_i = \frac{\mu_i}{1 + \alpha_i \mu_i}$

## 2. Logic Chain
1. **Goal**: Model football match outcomes with draws and overdispersion.
2. **Current state**: Only Poisson is implemented; Dixon-Coles adjustment parameters are hardcoded specifically for Poisson marginals.
3. **Problem**: Negative Binomial is needed for overdispersion, but applying the existing Dixon-Coles adjustments directly breaks the sum-to-one property of the joint probability table before truncation.
4. **Resolution**: 
   - Propose log-domain calculation of Negative Binomial probabilities using `math.lgamma` to prevent numeric overflow.
   - Propose a Generalized Dixon-Coles adjustment using scaling parameters $a_i = \text{P}(1)/\text{P}(0)$, which reduces to standard Dixon-Coles for Poisson and provides a mathematically sound adjustment for Negative Binomial.
5. **Architectural design**: Define clear signatures (`negative_binomial_probability`, `get_dixon_coles_adjustment`, `generate_joint_grid`) to support both models cleanly using a dataclass `MatchModelConfig`.

## 3. Caveats
- Truncation of the joint grid at `max_goals` (default: 12) removes a negligible amount of probability mass, which is handled via post-normalization.
- If the dispersion parameter $\alpha$ is close to 0, dividing by $\alpha$ to obtain $r = 1/\alpha$ leads to division by zero. The design includes a fallback threshold of $\alpha \le 10^{-6}$ where it switches to Poisson.
- Extremely high values of $|\rho|$ might lead to negative adjustment factors. The design includes a safeguards boundary: $\max\left(-1/a_A, -1/a_B\right) \le \rho \le \min\left(1, 1/(a_A a_B)\right)$ and truncates factors at `0.0` (using `max(0.0, factor)`).

## 4. Conclusion
We have delivered a complete mathematical analysis and design report to `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/explorer_m2_1/analysis.md`. The design features a novel Generalized Dixon-Coles formulation that bridges both Poisson and Negative Binomial models, preventing distribution sums from diverging before grid truncation.

## 5. Verification Method
To verify the math and signatures:
1. Inspect the detailed report `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/explorer_m2_1/analysis.md`.
2. Review the unit test cases provided in Section 4.B of the analysis report:
   - Check that `negative_binomial_probability` sums to $1.0$.
   - Check that `negative_binomial_probability` matches `poisson_probability` when $\alpha \to 0$.
   - Check that `generate_joint_grid` has a sum of $1.0$ (before truncation/normalization) when using the generalized Dixon-Coles adjustment.
