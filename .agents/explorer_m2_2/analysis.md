# Mathematical Correction Model for Altitude and Climatic Factors in WM 2026 Predictor

This report proposes a mathematically rigorous and physiologically grounded design to adjust baseline expected goals ($\lambda_A, \lambda_B$) for matches in the FIFA World Cup 2026, accounting for **altitude acclimation** and **climatic conditions (heat and humidity)**.

---

## 1. Executive Summary
We model the impact of altitude and heat on player endurance as fractional performance capacity factors ($f_{\text{alt}}, f_{\text{thermal}} \in (0, 1]$). These factors are combined multiplicatively and applied as power-law adjustments to baseline expected goals ($\lambda^0$), capturing how physical fatigue reduces offensive creation and amplifies defensive lapses.

---

## 2. Analysis of the Current Implementation
The current implementation in `predictor.py` calculates expected scoreline probabilities using a Poisson distribution with a Dixon-Coles adjustment for low scores:
* **Function**: `solve_optimal_tip(lam_A, lam_B, rho=0.0, max_goals=12, max_tip=6)`
* **Inputs**: Raw `lambdaA` and `lambdaB` values are passed directly from command-line arguments without adjustment.
* **Integration Point**: The proposed corrections should act as a pre-processing layer that intercepts raw expected goals ($\lambda_A^0, \lambda_B^0$) and scales them using the match's environmental metadata (elevation, temperature, humidity, and acclimation days) before passing them to the Poisson solver.

---

## 3. Altitude Acclimation Model

### 3.1 Physiological Foundation
As altitude increases, atmospheric pressure drops, reducing the partial pressure of oxygen. This leads to a decline in VO2 max (aerobic capacity) starting around $1000\text{ m}$ elevation, dropping by approximately $6\%\text{ to }10\%$ per $1000\text{ m}$ above that threshold for unacclimated athletes.
Acclimation (hyperventilation, pH balancing, and plasma volume adjustments) occurs exponentially over time, with significant recovery within the first 1-2 weeks.

### 3.2 Mathematical Formulation
Let $E$ be the stadium elevation in meters and $d_{\text{alt}}$ be the number of acclimation days at/near that elevation prior to the match.

1. **Unacclimated Aerobic Loss ($L_{\text{alt}}$)**:
   We model the baseline loss above an elevation threshold $E_{\text{threshold}} = 1000\text{ m}$ using a linear-quadratic form to represent accelerating degradation at extreme altitudes:
   $$L_{\text{alt}}(E) = \max\left(0, \alpha \cdot \frac{E - E_{\text{threshold}}}{1000} + \beta \cdot \left(\frac{E - E_{\text{threshold}}}{1000}\right)^2\right)$$
   Where:
   * $\alpha = 0.08$ (linear coefficient: $8\%$ loss per $1000\text{ m}$)
   * $\beta = 0.015$ (quadratic coefficient: accounts for compounding hypoxemia)

2. **Acclimated Altitude Performance Factor ($f_{\text{alt}}$)**:
   Acclimation is modeled as an exponential decay of the aerobic loss over time:
   $$f_{\text{alt}}(E, d_{\text{alt}}) = 1 - L_{\text{alt}}(E) \cdot e^{-d_{\text{alt}} / \tau_{\text{alt}}}$$
   Where:
   * $\tau_{\text{alt}} = 7.0$ days (physiological half-life for initial red-blood-cell and ventilatory adaptations)
   * $f_{\text{alt}} \in (0.5, 1.0]$ is clamped to ensure a minimum viability floor of $50\%$ physical output.

### 3.3 Altitude Edge Cases & Calibration
* **Sea Level & Low Altitude ($E \le 1000\text{ m}$)**:
  $L_{\text{alt}}(E) = 0 \implies f_{\text{alt}} = 1.0$ (no penalty).
* **Guadalajara (Estadio Akron: $1560\text{ m}$)**:
  * Unacclimated ($d_{\text{alt}} = 0$): $L_{\text{alt}} = 0.08(0.56) + 0.015(0.56)^2 = 0.0495 \implies f_{\text{alt}} \approx 0.950$ ($5.0\%$ loss)
  * Acclimated ($d_{\text{alt}} = 7$): $f_{\text{alt}} = 1 - 0.0495 \cdot e^{-1} \approx 0.982$ ($1.8\%$ loss)
* **Mexico City (Estadio Azteca: $2240\text{ m}$)**:
  * Unacclimated ($d_{\text{alt}} = 0$): $L_{\text{alt}} = 0.08(1.24) + 0.015(1.24)^2 = 0.1223 \implies f_{\text{alt}} \approx 0.878$ ($12.2\%$ loss)
  * Acclimated ($d_{\text{alt}} = 7$): $f_{\text{alt}} = 1 - 0.1223 \cdot e^{-1} \approx 0.955$ ($4.5\%$ loss)
  * Fully Acclimated ($d_{\text{alt}} = 14$): $f_{\text{alt}} = 1 - 0.1223 \cdot e^{-2} \approx 0.983$ ($1.7\%$ loss)

---

## 4. Climatic Conditions Model (Heat and Humidity)

### 4.1 Physiological Foundation
High ambient temperature and high relative humidity impair the body's primary thermoregulation mechanism (sweat evaporation). This increases cardiovascular strain and accelerates core temperature rise, drastically reducing high-intensity running capacity.
We use the **Wet-Bulb Globe Temperature (WBGT)** to represent this combined thermal stress.

### 4.2 Wet-Bulb Globe Temperature (WBGT) Estimation
To estimate WBGT from dry-bulb temperature ($T$ in °C) and relative humidity ($RH$ in %), we use the Australian Bureau of Meteorology (BOM) simplified formula:
$$e = \frac{RH}{100} \cdot 6.1078 \cdot \exp\left(\frac{17.27 \cdot T}{T + 237.3}\right)$$
$$WBGT = 0.567 \cdot T + 0.393 \cdot e + 3.94$$
Where:
* $e$ is the water vapor pressure in hectopascals (hPa) calculated using the Tetens equation.
* $T$ is the temperature in °C.
* $RH$ is the relative humidity percentage ($0 \text{ to } 100$).

### 4.3 Thermal Performance Factor ($f_{\text{thermal}}$)
Let $d_{\text{heat}}$ be the number of days spent training in similar hot conditions before the match.

1. **Unacclimated Thermal Loss ($L_{\text{thermal}}$)**:
   Thermal stress degrades physical capability linearly above a comfortable threshold of $WBGT_{\text{threshold}} = 20.0^\circ\text{C}$:
   $$L_{\text{thermal}}(WBGT) = c_{\text{thermal}} \cdot \max(0, WBGT - WBGT_{\text{threshold}})$$
   Where:
   * $c_{\text{thermal}} = 0.015$ (representing a $1.5\%$ capacity drop per degree WBGT above $20.0^\circ\text{C}$)

2. **Acclimated Thermal Performance Factor ($f_{\text{thermal}}$)**:
   Heat acclimation (plasma volume expansion) occurs faster than altitude acclimation:
   $$f_{\text{thermal}}(WBGT, d_{\text{heat}}) = 1 - L_{\text{thermal}}(WBGT) \cdot e^{-d_{\text{heat}} / \tau_{\text{heat}}}$$
   Where:
   * $\tau_{\text{heat}} = 5.0$ days (representing typical rapid thermal adaptation)
   * $f_{\text{thermal}} \in (0.5, 1.0]$ is clamped to a lower boundary of $0.5$.

### 4.4 Climatic Edge Cases & Calibration
* **Mild Conditions ($T = 20^\circ\text{C}, RH = 50\%$ )**:
  $e = 11.69\text{ hPa} \implies WBGT = 19.87^\circ\text{C} \implies L_{\text{thermal}} = 0 \implies f_{\text{thermal}} = 1.0$ (no penalty).
* **Hot & Humid (Houston/Miami: $T = 32^\circ\text{C}, RH = 70\%$ )**:
  * $e = 33.29\text{ hPa} \implies WBGT = 35.16^\circ\text{C}$ (extreme thermal stress)
  * Unacclimated ($d_{\text{heat}} = 0$): $L_{\text{thermal}} = 0.015(35.16 - 20) = 0.2274 \implies f_{\text{thermal}} \approx 0.773$ ($22.7\%$ loss)
  * Acclimated ($d_{\text{heat}} = 5$): $f_{\text{thermal}} = 1 - 0.2274 \cdot e^{-1} \approx 0.916$ ($8.4\%$ loss)

---

## 5. Integrated xG/Lambda Adjustment Model

### 5.1 Combined Physical Performance Factor ($F_i$)
For each team $i \in \{A, B\}$, we compute the combined physical performance factor as the product of the two independent environmental stressors:
$$F_i = f_{\text{alt}, i} \cdot f_{\text{thermal}, i}$$
Since both factors are in $(0, 1]$, $F_i \in (0.25, 1.0]$ represents the team's combined physical capacity.

### 5.2 Power-Law Lambda Scaling
We model the impact of fatigue on expected goals ($\lambda$) using two distinct channels:
1. **Offensive Penalty ($\gamma_{\text{off}}$)**: Fatigue reduces offensive sharpness, passing accuracy, and high-speed runs, decreasing own xG.
2. **Defensive Concession Penalty ($\gamma_{\text{def}}$)**: Fatigue impairs defensive organization, reaction times, and tracking back, increasing opponent xG.

The adjusted expected goals ($\lambda_A, \lambda_B$) are defined as:
$$\lambda_A = \lambda_A^0 \cdot F_A^{\gamma_{\text{off}}} \cdot F_B^{-\gamma_{\text{def}}}$$
$$\lambda_B = \lambda_B^0 \cdot F_B^{\gamma_{\text{off}}} \cdot F_A^{-\gamma_{\text{def}}}$$

Where:
* $\gamma_{\text{off}} = 0.5$ (offensive sensitivity)
* $\gamma_{\text{def}} = 0.8$ (defensive sensitivity, representing the empirical reality that defensive breakdowns are highly sensitive to physical exhaustion)

### 5.3 Asymmetric Fatigue Scenarios
* **Symmetric Fatigue (Both teams at $F_A = F_B = 0.80$)**:
  $$\lambda_A = \lambda_A^0 \cdot 0.80^{0.5} \cdot 0.80^{-0.8} = \lambda_A^0 \cdot 0.80^{-0.3} \approx 1.07 \cdot \lambda_A^0$$
  When both teams are equally fatigued, the game becomes more open and defensive lapses occur on both sides, leading to a net increase in expected goals (more chaotic, higher scoring game).
* **Asymmetric Fatigue (Team A acclimated $F_A = 1.0$, Team B unacclimated $F_B = 0.80$)**:
  $$\lambda_A = \lambda_A^0 \cdot 1.0^{0.5} \cdot 0.80^{-0.8} \approx 1.20 \cdot \lambda_A^0 \quad (\text{xG increases by } 20.0\%)$$
  $$\lambda_B = \lambda_B^0 \cdot 0.80^{0.5} \cdot 1.0^{-0.8} \approx 0.89 \cdot \lambda_B^0 \quad (\text{xG decreases by } 10.6\%)$$
  This perfectly models the competitive advantage gained by physical preparation and acclimation.

---

## 6. Proposed Python Implementation

Here is the proposed modular implementation to be integrated into `predictor.py`.

```python
import math

def calculate_altitude_factor(
    elevation: float, 
    acclimation_days: float, 
    threshold: float = 1000.0, 
    alpha: float = 0.08, 
    beta: float = 0.015, 
    tau: float = 7.0
) -> float:
    """
    Calculates the team's performance capacity factor under altitude stress.
    
    Parameters:
    - elevation: Stadium elevation in meters.
    - acclimation_days: Days the team spent acclimating to the altitude.
    - threshold: Elevation in meters below which there is no performance penalty.
    - alpha: Linear coefficient of VO2 max loss per 1000m above threshold.
    - beta: Quadratic coefficient of VO2 max loss per 1000m above threshold.
    - tau: Acclimation time constant in days.
    
    Returns:
      A float in the range [0.5, 1.0] representing the altitude capacity factor.
    """
    if elevation <= threshold:
        return 1.0
        
    h = (elevation - threshold) / 1000.0
    base_loss = alpha * h + beta * (h ** 2)
    acclimation_effect = math.exp(-acclimation_days / tau)
    remaining_loss = base_loss * acclimation_effect
    
    factor = 1.0 - remaining_loss
    return max(0.5, min(1.0, factor))


def calculate_wbgt(temperature: float, humidity: float) -> float:
    """
    Estimates the Wet-Bulb Globe Temperature (WBGT) in shadow/indoor conditions.
    Uses the Australian Bureau of Meteorology (BOM) vapor pressure approximation.
    
    Parameters:
    - temperature: Ambient temperature in Celsius.
    - humidity: Relative humidity percentage (0.0 to 100.0).
    """
    # Water vapor pressure (e) in hPa via Tetens equation
    e = (humidity / 100.0) * 6.1078 * math.exp((17.27 * temperature) / (temperature + 237.3))
    
    # WBGT approximation
    wbgt = 0.567 * temperature + 0.393 * e + 3.94
    return wbgt


def calculate_thermal_factor(
    temperature: float, 
    humidity: float, 
    heat_acclimation_days: float, 
    threshold: float = 20.0, 
    c_thermal: float = 0.015, 
    tau_heat: float = 5.0
) -> float:
    """
    Calculates the team's performance capacity factor under heat/humidity stress.
    
    Parameters:
    - temperature: Temperature in Celsius.
    - humidity: Relative humidity percentage (0.0 to 100.0).
    - heat_acclimation_days: Days the team spent acclimating to the local heat conditions.
    - threshold: WBGT temperature in Celsius below which there is no heat stress.
    - c_thermal: Performance loss per degree WBGT above threshold.
    - tau_heat: Acclimation time constant in days.
    
    Returns:
      A float in the range [0.5, 1.0] representing the thermal capacity factor.
    """
    wbgt = calculate_wbgt(temperature, humidity)
    
    if wbgt <= threshold:
        return 1.0
        
    base_loss = c_thermal * (wbgt - threshold)
    acclimation_effect = math.exp(-heat_acclimation_days / tau_heat)
    remaining_loss = base_loss * acclimation_effect
    
    factor = 1.0 - remaining_loss
    return max(0.5, min(1.0, factor))


def get_adjusted_lambdas(
    lambda_A_base: float,
    lambda_B_base: float,
    elevation: float,
    acclimation_days_A: float,
    acclimation_days_B: float,
    temperature: float,
    humidity: float,
    heat_acclimation_days_A: float,
    heat_acclimation_days_B: float,
    gamma_off: float = 0.5,
    gamma_def: float = 0.8
) -> tuple[float, float]:
    """
    Applies altitude and thermal adjustments to baseline expected goals.
    """
    # 1. Compute individual capacity factors
    f_alt_A = calculate_altitude_factor(elevation, acclimation_days_A)
    f_alt_B = calculate_altitude_factor(elevation, acclimation_days_B)
    
    f_therm_A = calculate_thermal_factor(temperature, humidity, heat_acclimation_days_A)
    f_therm_B = calculate_thermal_factor(temperature, humidity, heat_acclimation_days_B)
    
    # 2. Combined physical factors
    F_A = f_alt_A * f_therm_A
    F_B = f_alt_B * f_therm_B
    
    # 3. Apply power-law adjustments
    lambda_A_adj = lambda_A_base * (F_A ** gamma_off) * (F_B ** -gamma_def)
    lambda_B_adj = lambda_B_base * (F_B ** gamma_off) * (F_A ** -gamma_def)
    
    return lambda_A_adj, lambda_B_adj
```

---

## 7. CLI Integration in `predictor.py`
To fully leverage these curves, the `main()` function in `predictor.py` should be expanded to accept the new environmental parameters as optional CLI flags:

```python
    # New CLI Arguments to add to parser:
    parser.add_argument("--elevation", type=float, default=0.0, help="Stadium elevation in meters")
    parser.add_argument("--temp", type=float, default=15.0, help="Ambient temperature in Celsius")
    parser.add_argument("--humidity", type=float, default=50.0, help="Relative humidity percentage")
    
    parser.add_argument("--accl_days_A", type=float, default=0.0, help="Altitude acclimation days for Team A")
    parser.add_argument("--accl_days_B", type=float, default=0.0, help="Altitude acclimation days for Team B")
    parser.add_argument("--heat_accl_days_A", type=float, default=0.0, help="Heat acclimation days for Team A")
    parser.add_argument("--heat_accl_days_B", type=float, default=0.0, help="Heat acclimation days for Team B")
```

The adjusted lambdas are then resolved prior to executing the Tip Solver:
```python
    # Inside main():
    lambda_A, lambda_B = get_adjusted_lambdas(
        args.lambdaA, args.lambdaB,
        elevation=args.elevation,
        acclimation_days_A=args.accl_days_A,
        acclimation_days_B=args.accl_days_B,
        temperature=args.temp,
        humidity=args.humidity,
        heat_acclimation_days_A=args.heat_accl_days_A,
        heat_acclimation_days_B=args.heat_accl_days_B
    )
    
    tips, scores, outcomes = solve_optimal_tip(lambda_A, lambda_B, args.rho, max_tip=args.max_tip)
```
This cleanly maps the physical realities of the 2026 venues to our tipping optimization engine.
