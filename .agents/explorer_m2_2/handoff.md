# Handoff Report - Explorer M2_2

This report presents the findings, logic, and designs for the mathematical correction curves for altitude acclimation and climatic conditions in the World Cup 2026 Predictor.

---

## 1. Observation
We analyzed the contents of the following files:
1. `predictor.py` at `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`:
   Lines 100-112:
   ```python
   def main():
       parser = argparse.ArgumentParser(description="WM 2026 Tippspiel-Optimierer (Poisson-Modell)")
       parser.add_argument("--teamA", type=str, default="Team A", help="Name von Heimteam")
       parser.add_argument("--teamB", type=str, default="Team B", help="Name von Auswärtsteam")
       parser.add_argument("--lambdaA", type=float, required=True, help="Torerwartung lambda für Team A (xG)")
       parser.add_argument("--lambdaB", type=float, required=True, help="Torerwartung lambda für Team B (xG)")
       parser.add_argument("--rho", type=float, default=-0.05, help="Dixon-Coles Korrekturfaktor für Unentschieden/Tiefstände")
       parser.add_argument("--max_tip", type=int, default=5, help="Maximaler Tore-Tipp")
       
       args = parser.parse_args()
   
       tips, scores, outcomes = solve_optimal_tip(args.lambdaA, args.lambdaB, args.rho, max_tip=args.max_tip)
   ```
2. `PROJECT.md` at `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/PROJECT.md`:
   Line 25-28:
   ```markdown
   - **Altitude Acclimation Curves**: Stadium elevations impact player endurance and ball physics, modeled using acclimation curves.
   - **Climatic Conditions**: Adjusts team performance based on heat and humidity index (wet-bulb temperature equivalents).
   ```

---

## 2. Logic Chain
1. Based on `predictor.py` (Observation 1), the prediction engine currently accepts raw `lambdaA` and `lambdaB` values directly from CLI arguments and passes them unmodified to the solver.
2. Based on `PROJECT.md` (Observation 2), the system needs to adjust team performance based on stadium elevations (altitude acclimation) and heat/humidity.
3. Physically, altitude and heat/humidity both reduce aerobic capacity (VO2 max) and increase thermal/cardiovascular stress. In soccer, physical fatigue affects team performance by decreasing own offensive efficiency (sharpness, speed) and increasing opponent's offensive efficiency (defensive lapses, recovery errors).
4. By introducing a pre-processing function that intercepts raw expected goals ($\lambda_A^0, \lambda_B^0$), calculates combined physical capacity factors ($F_A, F_B$), and scales the expected goals using asymmetric power-law exponents ($\gamma_{\text{off}}$ and $\gamma_{\text{def}}$), we can model these complex dynamics while keeping the core solver decoupled from environmental logic.
5. The mathematical formulas developed and recorded in `analysis.md` accurately model these dynamics:
   * **Altitude**: $f_{\text{alt}} = 1 - L_{\text{alt}}(E) \cdot e^{-d_{\text{alt}} / \tau_{\text{alt}}}$ (where $L_{\text{alt}}$ is linear-quadratic with altitude above $1000\text{ m}$, and acclimation decay is exponential).
   * **Heat**: $f_{\text{thermal}} = 1 - L_{\text{thermal}}(WBGT) \cdot e^{-d_{\text{heat}} / \tau_{\text{heat}}}$ (where $WBGT$ is calculated using the Australian BOM vapor pressure approximation, and thermal stress is linear above $20.0^\circ\text{C}$).
   * **Integration**: Combined factors $F_i = f_{\text{alt}, i} \cdot f_{\text{thermal}, i}$ scale expected goals via:
     $$\lambda_A = \lambda_A^0 \cdot F_A^{\gamma_{\text{off}}} \cdot F_B^{-\gamma_{\text{def}}}$$
     $$\lambda_B = \lambda_B^0 \cdot F_B^{\gamma_{\text{off}}} \cdot F_A^{-\gamma_{\text{def}}}$$

---

## 3. Caveats
* The physiological calibration constants ($\alpha=0.08, \beta=0.015, c_{\text{thermal}}=0.015, \tau_{\text{alt}}=7.0, \tau_{\text{heat}}=5.0$) and sensitivity exponents ($\gamma_{\text{off}}=0.5, \gamma_{\text{def}}=0.8$) are selected based on literature values for athletic performance and soccer match dynamics. They have not yet been fine-tuned or backtested against actual historical World Cup match data.
* Ball physics (e.g. lower air density causing less drag and different ball curves at high altitudes) is not included in this model as it primarily impacts set-piece trajectory rather than team-level aerobic expected goals.

---

## 4. Conclusion
We have completed a detailed design and mathematical correction curve model for both altitude acclimation and climatic conditions. The complete proposal, including formulas, edge case behavior, and proposed Python function signatures is saved to `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/explorer_m2_2/analysis.md`.

---

## 5. Verification Method
1. Inspect `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/explorer_m2_2/analysis.md` to confirm the presence of clear function signatures, formulas, and integration CLI parameters.
2. Confirm mathematical correctness of calculations by checking extreme values:
   * Sea Level ($E \le 1000\text{ m}$) or mild temperature ($WBGT \le 20.0^\circ\text{C}$) must result in factors of $1.0$.
   * An unacclimated team at Estadio Azteca ($2240\text{ m}$) must experience a $\approx 12.2\%$ loss ($f_{\text{alt}} \approx 0.878$).
   * 14 days of acclimation at Azteca must restore the capacity factor to $\approx 98.3\%$.
