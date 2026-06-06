# Milestone 2 Design Specification: Advanced Probability Engine & Contextual Factors

This document provides the complete mathematical and architectural specification for Milestone 2 of the World Cup 2026 Prediction Engine.

---

## 1. Probability Engine Architecture

The probability engine supports two distinct probability distributions for match goals, adjustable via a new `MatchModelConfig` configuration.

### A. Probability Distributions
1. **Poisson Distribution**:
   $$P(X = k) = \frac{\lambda^k e^{-\lambda}}{k!}$$
2. **Negative Binomial Distribution** (to handle overdispersion where $\text{Var}(X) > \text{E}(X)$):
   $$P(X = k) = \frac{\Gamma(k + r)}{k! \, \Gamma(r)} (1 - p)^k p^r$$
   where:
   - Dispersion parameter: $r = \frac{1}{\alpha}$ (with $\alpha > 0$)
   - Success probability: $p = \frac{1}{1 + \alpha \mu}$
   - Falls back to Poisson if $\alpha \le 10^{-6}$ to avoid division by zero.
   - Computed in the log-domain using `math.lgamma` to prevent numerical overflow.

### B. Generalized Dixon-Coles Adjustment
To model draw correlation, joint probabilities are adjusted:
$$P(X=x, Y=y) = \tau(x, y) \cdot P(X=x) \cdot P(Y=y)$$
where the generalized correction factor $\tau(x, y)$ is:
$$\tau(x, y) = \begin{cases} 
1 - \rho \cdot a_A \cdot a_B & \text{for } x = 0, y = 0 \\
1 + \rho \cdot a_B & \text{for } x = 1, y = 0 \\
1 + \rho \cdot a_A & \text{for } x = 0, y = 1 \\
1 - \rho & \text{for } x = 1, y = 1 \\
1 & \text{otherwise}
\end{cases}$$
and the scaling parameters are:
$$a_i = \frac{P_i(1)}{P_i(0)}$$
- For Poisson: $a_i = \mu_i$ (standard Dixon-Coles).
- For Negative Binomial: $a_i = \frac{\mu_i}{1 + \alpha_i \mu_i}$.
This generalized formulation guarantees that the joint probability matrix sums to exactly $1.0$ (before truncation) for any discrete marginal distributions.

---

## 2. Contextual Correction Curves

Raw expected goals ($\lambda^0_A, \lambda^0_B$) are adjusted using a unified log-linear formulation:
$$\lambda_A = \lambda^0_A \cdot \exp\left( \Delta_{\text{att}, A} + \Delta_{\text{def}, B} \right)$$
$$\lambda_B = \lambda^0_B \cdot \exp\left( \Delta_{\text{att}, B} + \Delta_{\text{def}, A} \right)$$

### A. Environmental Stressors (Altitude and Heat/Humidity)
Individual capacity factors $f_{\text{alt}}, f_{\text{thermal}} \in [0.5, 1.0]$ are calculated, yielding a combined physical factor $F_i = f_{\text{alt}, i} \cdot f_{\text{thermal}, i}$.
1. **Altitude Acclimation**:
   $$L_{\text{alt}}(E) = \max\left(0, 0.08 \cdot H + 0.015 \cdot H^2\right) \quad \text{where } H = \frac{E - 1000}{1000}$$
   $$f_{\text{alt}}(E, d_{\text{alt}}) = 1 - L_{\text{alt}}(E) \cdot e^{-d_{\text{alt}} / 7.0}$$
2. **Thermal Stress (WBGT)**:
   $$e = \frac{RH}{100} \cdot 6.1078 \cdot \exp\left(\frac{17.27 \cdot T}{T + 237.3}\right)$$
   $$WBGT = 0.567 \cdot T + 0.393 \cdot e + 3.94$$
   $$L_{\text{thermal}}(WBGT) = 0.015 \cdot \max(0, WBGT - 20.0)$$
   $$f_{\text{thermal}}(WBGT, d_{\text{heat}}) = 1 - L_{\text{thermal}}(WBGT) \cdot e^{-d_{\text{heat}} / 5.0}$$

The environmental log-scale contributions are:
$$\Delta_{\text{att, env}, i} = 0.5 \cdot \ln(F_i)$$
$$\Delta_{\text{def, env}, i} = -0.8 \cdot \ln(F_i)$$

### B. Travel Fatigue
Modeled as total fatigue penalty $P_{\text{total}} \in [0.0, 0.30]$:
$$P_{\text{rest}}(r) = 0.03 \cdot \max(0, 5 - r)^{1.5}$$
$$P_{\text{dist}}(d, r) = 0.05 \cdot \left(1 - e^{-0.001 \cdot d}\right) \cdot e^{-0.30 \cdot r}$$
$$P_{\text{tz}}(\Delta z, \text{dir}, r) = 0.02 \cdot \max(0, CD(\Delta z, \text{dir}) - r) \quad \text{with } CD = \Delta z \cdot w_{\text{dir}}$$
$$P_{\text{total}, i} = \min\left(0.30, P_{\text{rest}} + P_{\text{dist}} + P_{\text{tz}}\right)$$

The travel log-scale contributions are:
$$\Delta_{\text{att, travel}, i} = -0.70 \cdot P_{\text{total}, i}$$
$$\Delta_{\text{def, travel}, i} = 0.30 \cdot P_{\text{total}, i}$$

### C. Host Advantage and Fan Support
1. **Host Status**:
   - `True Home`: $\theta_{\text{att}} = 0.08, \theta_{\text{def}} = -0.06$
   - `Co-Host`: $\theta_{\text{att}} = 0.03, \theta_{\text{def}} = -0.02$
   - `Neutral`: $\theta_{\text{att}} = 0.00, \theta_{\text{def}} = 0.00$
2. **Fan Support**:
   $$\Delta_{\text{att, fan}, i} = 0.05 \cdot (S_i - S_j)$$
   $$\Delta_{\text{def, fan}, i} = -0.04 \cdot (S_i - S_j)$$

---

## 3. Python API Design & Integration

### A. New CLI Arguments
```python
# Distributions
--distribution {poisson, negative_binomial}
--alphaA (dispersion parameter for Team A)
--alphaB (dispersion parameter for Team B)

# Environmental Factors
--elevation (stadium elevation in meters)
--temp (ambient temperature in Celsius)
--humidity (relative humidity percentage)
--accl_days_A / --accl_days_B (altitude acclimation days)
--heat_accl_days_A / --heat_accl_days_B (heat acclimation days)

# Travel & Fatigue
--rest_days_A / --rest_days_B (days of rest)
--travel_miles_A / --travel_miles_B (miles traveled)
--tz_crossed_A / --tz_crossed_B (time zones crossed)
--travel_dir_A / --travel_dir_B (travel direction: East, West, None)

# Host & Fans
--status_A / --status_B (True Home, Co-Host, Neutral)
--fan_pct_A / --fan_pct_B (fan support percentage: 0.0 to 1.0)
```

### B. Core Functions
The implementation in `predictor.py` will expose:
- `calculate_altitude_factor(elevation, acclimation_days) -> float`
- `calculate_wbgt(temp, humidity) -> float`
- `calculate_thermal_factor(temp, humidity, heat_accl_days) -> float`
- `calculate_travel_penalty(rest_days, travel_miles, tz_crossed, direction) -> float`
- `get_adjusted_lambdas(lambda_A_base, lambda_B_base, teamA_context, teamB_context) -> tuple[float, float]`
- `poisson_probability(k, lam) -> float`
- `negative_binomial_probability(k, mu, alpha) -> float`
- `generate_joint_grid(config) -> dict`
- `solve_optimal_tip(config) -> tuple`
