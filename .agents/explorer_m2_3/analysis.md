# Design and Mathematical Models for Contextual Adjustments in WM 2026 Predictor

This report proposes a mathematically rigorous and biologically grounded framework for incorporating contextual tournament factors into the World Cup 2026 prediction engine. These factors adjust base team expected goals ($\lambda$) using a log-additive formulation, which is standard in bivariate Poisson and football analytics modeling.

---

## 1. Analysis of Current Implementation in `predictor.py`

The current version of `predictor.py` uses a classic independent Poisson goal distribution with a Dixon-Coles adjustment for low-scoring matches (resolving draw bias):

1. **Probability Matrix Construction**:
   - `poisson_prob(k, lam)` computes individual goal probabilities.
   - `solve_optimal_tip(lam_A, lam_B, rho, ...)` builds a 2D probability matrix $P[g_A][g_B]$ as the product of independent Poisson distributions:
     $$P(G_A = g_A, G_B = g_B) = \text{Poisson}(g_A; \lambda_A) \times \text{Poisson}(g_B; \lambda_B)$$
   - Dixon-Coles adjustment is applied directly to low scores:
     - $(0,0) \to 1.0 - \rho \lambda_A \lambda_B$
     - $(1,0) \to 1.0 + \rho \lambda_B$
     - $(0,1) \to 1.0 + \rho \lambda_A$
     - $(1,1) \to 1.0 - \rho$
   - Finally, the probability matrix is normalized.

2. **EV Maximizer**:
   - `get_points(t_A, t_B, g_A, g_B)` computes Kicktipp points (4 for exact, 3 for difference/tendency, 2 for tendency, 0 otherwise).
   - `solve_optimal_tip` iterates over all tipping options (up to `max_tip`) and returns the tip with the highest expected value (EV).

### Limitations of Current Model
- **No Contextual Modifiers**: Base $\lambda_A$ and $\lambda_B$ are assumed static. Factors like travel fatigue, short rest days, time zones crossed, home-field advantage, and fan support distribution are ignored.
- **Symmetric Home-Field Assumption**: There is currently no home-field bias modeled natively in the Poisson grid constructor (though home-field could theoretically be baked into the input $\lambda$, a programmatic approach is preferred).

---

## 2. Proposed Mathematical Models

We introduce a unified log-linear formulation where the adjusted expected goals ($\lambda_A, \lambda_B$) are computed as:

$$\lambda_A = \lambda_{\text{base, A}} \cdot \exp\left( \Delta_{\text{att}, A} + \Delta_{\text{def}, B} \right)$$
$$\lambda_B = \lambda_{\text{base, B}} \cdot \exp\left( \Delta_{\text{att}, B} + \Delta_{\text{def}, A} \right)$$

where:
- $\Delta_{\text{att}, i}$ is the net attacking adjustment for Team $i$.
- $\Delta_{\text{def}, i}$ is the net defensive adjustment (vulnerability) for Team $i$.

This formulation ensures that:
- Multipliers are strictly positive ($\exp(x) > 0$).
- Attacking improvements scale expected goals upward, while defensive improvements (negative $\Delta_{\text{def}}$) scale opponent expected goals downward.
- All penalties and bonuses compose naturally and additively in log-space.

---

### Model A: Travel and Rest Days Penalty Model

Travel stress and physical fatigue affect both a team's attacking precision ($\Delta_{\text{att}}$) and defensive coordination/mental sharpness ($\Delta_{\text{def}}$). We model this using three sub-penalties that combine into a Total Travel Penalty $P_{\text{total}, i}$.

#### 1. Rest Deficit Penalty ($P_{\text{rest}}$)
Short recovery periods severely impact performance, whereas rest beyond a certain threshold has diminishing returns.
$$P_{\text{rest}}(r) = C_{\text{rest}} \cdot \max(0, R_{\text{target}} - r)^p$$
- **Parameters**:
  - $R_{\text{target}} = 5$: Baseline recovery days at which rest penalty is zero.
  - $C_{\text{rest}} = 0.03$: Scaling factor.
  - $p = 1.5$: Convexity parameter (penalizes consecutive short-rest games exponentially).
- **Behavior**:
  - $r \ge 5$ days: $P_{\text{rest}} = 0$
  - $r = 4$ days: $P_{\text{rest}} = 0.03 \cdot 1^{1.5} = 0.03$ (3% penalty)
  - $r = 3$ days (standard): $P_{\text{rest}} = 0.03 \cdot 2^{1.5} \approx 0.085$ (8.5% penalty)
  - $r = 2$ days (severe): $P_{\text{rest}} = 0.03 \cdot 3^{1.5} \approx 0.156$ (15.6% penalty)

#### 2. Physical Travel Distance Penalty ($P_{\text{dist}}$)
Fatigue from flight distance is sub-linear (modeled via exponential saturation) and is mitigated by the number of rest days $r$ before the match.
$$P_{\text{dist}}(d, r) = C_{\text{dist}} \cdot \left(1 - e^{-\lambda_d \cdot d}\right) \cdot e^{-\lambda_{rd} \cdot r}$$
- **Parameters**:
  - $d$: Great-circle distance traveled in miles.
  - $r$: Rest days since travel.
  - $C_{\text{dist}} = 0.05$: Maximum possible physical distance penalty (5%).
  - $\lambda_d = 0.001$: Saturation scale (a 1000-mile flight yields $63\%$ of max penalty; 3000 miles yields $95\%$).
  - $\lambda_{rd} = 0.30$: Recovery rate per rest day (each rest day decreases the remaining distance penalty by $\approx 26\%$).

#### 3. Circadian Disruption (Jet Lag) Penalty ($P_{\text{tz}}$)
Crossing time zones disrupts circadian rhythms. Adaptation takes approximately 1 day per timezone, and phase advance (Eastward travel) is harder than phase delay (Westward travel).
- **Circadian Disruption Score ($CD$)**:
  $$CD(\Delta z, \text{dir}) = \Delta z \cdot w_{\text{dir}}$$
  where:
  - $w_{\text{dir}} = 1.5$ if Eastbound ($\text{dir} = \text{"East"}$)
  - $w_{\text{dir}} = 1.0$ if Westbound ($\text{dir} = \text{"West"}$)
  - $w_{\text{dir}} = 0.0$ if no time zones crossed ($\Delta z = 0$)
- **Jet Lag Penalty**:
  $$P_{\text{tz}}(\Delta z, \text{dir}, r) = C_{\text{tz}} \cdot \max(0, CD(\Delta z, \text{dir}) - r)$$
- **Parameters**:
  - $\Delta z$: Absolute number of time zones crossed.
  - $r$: Rest days since arrival.
  - $C_{\text{tz}} = 0.02$: Penalty coefficient (2% penalty per day of unadjusted timezone deficit).

#### Total Fatigue Penalty ($P_{\text{total}}$)
The total penalty is the sum of the three factors, capped at a maximum performance degradation:
$$P_{\text{total}, i} = \min\left(P_{\text{max}}, P_{\text{rest}}(r_i) + P_{\text{dist}}(d_i, r_i) + P_{\text{tz}}(\Delta z_i, \text{dir}_i, r_i)\right)$$
- **Parameters**:
  - $P_{\text{max}} = 0.30$: Capped at 30% total performance penalty.

#### Log-Scale Adjustments
The fatigue penalty degrades a team's own attacking potency and increases their defensive vulnerability (conceding more goals):
$$\Delta_{\text{att, travel}, i} = -c_{\text{att, travel}} \cdot P_{\text{total}, i}$$
$$\Delta_{\text{def, travel}, i} = c_{\text{def, travel}} \cdot P_{\text{total}, i}$$
- **Parameters**:
  - $c_{\text{att, travel}} = 0.70$: Attacking degradation sensitivity.
  - $c_{\text{def, travel}} = 0.30$: Defensive degradation sensitivity (mistakes, coordination failure).

---

### Model B: Host Advantage and Fan Support Model

Host advantage and fan support skew team efficiency. We separate these into a structural country-host effect and a dynamic stadium crowd effect.

#### 1. Host Status Advantage ($\Delta_{\text{host}}$)
Represents the structural benefits of playing in a familiar climate/timezone, using familiar training facilities, avoiding long-distance travel, and favorable referee bias.
For World Cup 2026 (co-hosted by USA, Canada, and Mexico):
- **Status Categories**:
  - **True Home**: Team is playing in their home country (e.g., USA playing in a USA stadium).
  - **Co-Host**: Team is one of the three co-hosts but playing in another host's country (e.g., Mexico playing in a US stadium).
  - **Neutral**: Neither of the above.
- **Log-scale constants**:
  - $\theta_{\text{att, host}}(\text{True Home}) = 0.08$ (equivalent to $+8.3\%$ goals scored)
  - $\theta_{\text{def, host}}(\text{True Home}) = -0.06$ (equivalent to $-5.8\%$ goals conceded)
  - $\theta_{\text{att, host}}(\text{Co-Host}) = 0.03$ (equivalent to $+3.0\%$ goals scored)
  - $\theta_{\text{def, host}}(\text{Co-Host}) = -0.02$ (equivalent to $-2.0\%$ goals conceded)
  - $\theta_{\text{att, host}}(\text{Neutral}) = 0.0$
  - $\theta_{\text{def, host}}(\text{Neutral}) = 0.0$

#### 2. Fan Support Advantage ($\Delta_{\text{fan}}$)
Stadia in neutral countries can still have massive fan imbalance (e.g. Mexico vs Poland in USA).
Let $S_i \in [0.0, 1.0]$ and $S_j \in [0.0, 1.0]$ be the proportions of fan support for Team $i$ and Team $j$ in the stadium.
The fan advantage is driven by the net support margin $\Delta S = S_i - S_j$:
$$\Delta_{\text{att, fan}, i} = C_{\text{att, fan}} \cdot (S_i - S_j)$$
$$\Delta_{\text{def, fan}, i} = -C_{\text{def, fan}} \cdot (S_i - S_j)$$
- **Parameters**:
  - $C_{\text{att, fan}} = 0.05$: Max attack scaling (up to $\approx +5.1\%$ goals scored with a 100% vs 0% crowd).
  - $C_{\text{def, fan}} = 0.04$: Max defense scaling (up to $\approx -3.9\%$ goals conceded).

#### Combined Host and Fan Net Adjustments
For any team $i$ playing opponent $j$:
$$\Delta_{\text{att}, i} = \Delta_{\text{att, travel}, i} + \theta_{\text{att, host}}(Status_i) + C_{\text{att, fan}} \cdot (S_i - S_j)$$
$$\Delta_{\text{def}, i} = \Delta_{\text{def, travel}, i} + \theta_{\text{def, host}}(Status_i) - C_{\text{def, fan}} \cdot (S_i - S_j)$$

---

## 3. Function Signatures and Python Implementations

These function signatures are designed for integration into `predictor.py`.

```python
def calculate_travel_penalty(
    rest_days: float,
    travel_miles: float,
    tz_crossed: int,
    direction: str = "None",
    r_target: float = 5.0,
    c_rest: float = 0.03,
    p: float = 1.5,
    c_dist: float = 0.05,
    lambda_d: float = 0.001,
    lambda_rd: float = 0.30,
    c_tz: float = 0.02,
    p_max: float = 0.30
) -> float:
    """
    Calculates the total travel and fatigue penalty P_total.
    
    Args:
        rest_days: Days of rest since the last match.
        travel_miles: Great-circle distance traveled in miles.
        tz_crossed: Absolute number of time zones crossed.
        direction: Direction of travel ("East", "West", or "None").
        r_target: Target rest days for zero rest penalty.
        c_rest: Rest penalty scale.
        p: Convex exponent for rest deficit.
        c_dist: Max distance penalty coefficient.
        lambda_d: Distance decay constant.
        lambda_rd: Rest days mitigation decay constant for travel.
        c_tz: Timezone penalty coefficient.
        p_max: Maximum capped penalty.
        
    Returns:
        float: Combined penalty score P_total in [0.0, p_max].
    """
    # 1. Rest Deficit Penalty
    p_rest = c_rest * max(0.0, r_target - rest_days) ** p
    
    # 2. Distance Penalty
    p_dist = c_dist * (1.0 - math.exp(-lambda_d * travel_miles)) * math.exp(-lambda_rd * rest_days)
    
    # 3. Circadian Disruption Penalty
    w_dir = 1.5 if direction.strip().lower() == "east" else (1.0 if direction.strip().lower() == "west" else 0.0)
    cd_score = tz_crossed * w_dir
    p_tz = c_tz * max(0.0, cd_score - rest_days)
    
    # Combined & capped
    return min(p_max, p_rest + p_dist + p_tz)


def calculate_context_adjustments(
    status: str,
    opponent_status: str,
    fan_support_pct: float,
    opponent_fan_support_pct: float,
    travel_penalty: float,
    opponent_travel_penalty: float,
    c_att_travel: float = 0.70,
    c_def_travel: float = 0.30,
    c_att_fan: float = 0.05,
    c_def_fan: float = 0.04
) -> tuple[float, float]:
    """
    Computes log-scale attack and defense adjustments for a single team.
    
    Args:
        status: Host status of the team ("True Home", "Co-Host", "Neutral").
        opponent_status: Host status of the opponent.
        fan_support_pct: Fan support percentage in stadium [0.0, 1.0].
        opponent_fan_support_pct: Opponent's fan support percentage [0.0, 1.0].
        travel_penalty: Computed P_total for the team.
        opponent_travel_penalty: Computed P_total for the opponent.
        c_att_travel: Attack travel penalty weight.
        c_def_travel: Defense travel penalty weight.
        c_att_fan: Attack fan support weight.
        c_def_fan: Defense fan support weight.
        
    Returns:
        tuple[float, float]: (delta_att, delta_def) log-scale adjustments.
    """
    # 1. Travel Adjustment
    delta_att_travel = -c_att_travel * travel_penalty
    delta_def_travel = c_def_travel * travel_penalty
    
    # 2. Host Status Coefficients
    host_att_map = {"True Home": 0.08, "Co-Host": 0.03, "Neutral": 0.00}
    host_def_map = {"True Home": -0.06, "Co-Host": -0.02, "Neutral": 0.00}
    
    delta_att_host = host_att_map.get(status, 0.0)
    delta_def_host = host_def_map.get(status, 0.0)
    
    # 3. Fan Support
    net_fan_margin = fan_support_pct - opponent_fan_support_pct
    delta_att_fan = c_att_fan * net_fan_margin
    delta_def_fan = -c_def_fan * net_fan_margin
    
    # Total Additive log adjustment
    delta_att = delta_att_travel + delta_att_host + delta_att_fan
    delta_def = delta_def_travel + delta_def_host + delta_def_fan
    
    return delta_att, delta_def


def adjust_lambdas(
    lambda_A_base: float,
    lambda_B_base: float,
    teamA_context: dict,
    teamB_context: dict
) -> tuple[float, float]:
    """
    Calculates adjusted lambdas for team A and team B by evaluating both team contexts.
    
    Args:
        lambda_A_base: Base expected goals (xG) for Team A.
        lambda_B_base: Base expected goals (xG) for Team B.
        teamA_context: Dict containing:
            - "rest_days": float
            - "travel_miles": float
            - "tz_crossed": int
            - "direction": str
            - "status": str
            - "fan_support_pct": float
        teamB_context: Dict containing same keys for Team B.
        
    Returns:
        tuple[float, float]: (adjusted_lambda_A, adjusted_lambda_B)
    """
    # Calculate travel penalties
    p_travel_A = calculate_travel_penalty(
        teamA_context["rest_days"],
        teamA_context["travel_miles"],
        teamA_context["tz_crossed"],
        teamA_context["direction"]
    )
    p_travel_B = calculate_travel_penalty(
        teamB_context["rest_days"],
        teamB_context["travel_miles"],
        teamB_context["tz_crossed"],
        teamB_context["direction"]
    )
    
    # Calculate log adjustments
    delta_att_A, delta_def_A = calculate_context_adjustments(
        teamA_context["status"],
        teamB_context["status"],
        teamA_context["fan_support_pct"],
        teamB_context["fan_support_pct"],
        p_travel_A,
        p_travel_B
    )
    delta_att_B, delta_def_B = calculate_context_adjustments(
        teamB_context["status"],
        teamA_context["status"],
        teamB_context["fan_support_pct"],
        teamA_context["fan_support_pct"],
        p_travel_B,
        p_travel_A
    )
    
    # Apply adjustments using exp formulation
    lambda_A_adj = lambda_A_base * math.exp(delta_att_A + delta_def_B)
    lambda_B_adj = lambda_B_base * math.exp(delta_att_B + delta_def_A)
    
    return lambda_A_adj, lambda_B_adj
```

---

## 4. Calibration and Verification Scenarios

To verify the mathematical stability of the model, consider the following extreme and nominal scenarios.

### Scenario 1: Symmetrical Neutral Ground (Validation Baseline)
- **Inputs**:
  - $\lambda_{\text{base, A}} = 1.5$, $\lambda_{\text{base, B}} = 1.2$
  - Both teams: Neutral status, 50% fan support, 5 rest days, 0 travel miles, 0 time zones crossed.
- **Computation**:
  - $P_{\text{total, A}} = P_{\text{total, B}} = 0$
  - Net fan margin $\Delta S = 0$
  - $\Delta_{\text{att}, A} = \Delta_{\text{def}, B} = \Delta_{\text{att}, B} = \Delta_{\text{def}, A} = 0$
- **Result**:
  - $\lambda_{\text{adjusted, A}} = 1.5$, $\lambda_{\text{adjusted, B}} = 1.2$ (Symmetric recovery, no scaling).

### Scenario 2: High Travel/Rest Disadvantage for Away vs. Fresh Host (Extreme Fatigue)
- **Team A (Host)**: Playing at home (`True Home`), 80% crowd support, 5 rest days, 0 travel miles.
- **Team B (Away)**: playing in USA (`Neutral`), 10% crowd support, 3 rest days, traveled 3000 miles crossing 6 time zones Eastbound.
- **Base parameters**: $\lambda_{\text{base, A}} = 1.5$, $\lambda_{\text{base, B}} = 1.5$ (Equally strong base strength).
- **Computation steps**:
  1. **Travel Penalty for A**: $P_{\text{total, A}} = 0.0$
  2. **Travel Penalty for B**:
     - $P_{\text{rest}} = 0.03 \cdot (5 - 3)^{1.5} \approx 0.085$
     - $P_{\text{dist}} = 0.05 \cdot (1 - e^{-3.0}) \cdot e^{-0.9} \approx 0.05 \cdot 0.95 \cdot 0.407 \approx 0.019$
     - $P_{\text{tz}} = 0.02 \cdot \max(0, 6 \cdot 1.5 - 3) = 0.02 \cdot 6 = 0.12$
     - $P_{\text{total, B}} = 0.085 + 0.019 + 0.12 = 0.224$ (No capping needed as $0.224 < 0.30$)
  3. **Log adjustments**:
     - **Team A**:
       - $\Delta_{\text{att}, A} = -0.70(0.0) + 0.08 + 0.05(0.80 - 0.10) = 0.115$
       - $\Delta_{\text{def}, A} = 0.30(0.0) - 0.06 - 0.04(0.80 - 0.10) = -0.088$
     - **Team B**:
       - $\Delta_{\text{att}, B} = -0.70(0.224) + 0.0 + 0.05(0.10 - 0.80) = -0.1568 - 0.035 = -0.1918$
       - $\Delta_{\text{def}, B} = 0.30(0.224) + 0.0 - 0.04(0.10 - 0.80) = 0.0672 + 0.028 = 0.0952$
  4. **Adjusted Lambdas**:
     - $\lambda_{\text{adj, A}} = 1.5 \cdot \exp(0.115 + 0.0952) = 1.5 \cdot \exp(0.2102) \approx 1.5 \cdot 1.234 \approx 1.85$ (xG increases by $23.4\%$)
     - $\lambda_{\text{adj, B}} = 1.5 \cdot \exp(-0.1918 - 0.088) = 1.5 \cdot \exp(-0.2798) \approx 1.5 \cdot 0.756 \approx 1.13$ (xG decreases by $24.4\%$)
- **Result**:
  - The final lambdas are adjusted from $(1.5, 1.5)$ to $(1.85, 1.13)$. This beautifully models the crushing effect of transatlantic jet lag combined with short rest and hostile host stadium support.
