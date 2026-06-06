# Original User Request

## Initial Request — 2026-06-03T17:05:57Z

Build an optimized FIFA World Cup 2026 prediction engine that identifies and resolves flaws in the current score generation process (e.g., standard Poisson limitations) to find the absolute mathematically optimal tipping strategy.

Working directory: /Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor
Integrity mode: development

## Requirements

### R1. Advanced Probability Engine
Replace the simplistic independent Poisson model. Implement a Bivariate Poisson model with Dixon-Coles correlation adjustments to properly model draws, or a Negative Binomial distribution to handle overdispersion (high-scoring outliers).

### R2. Contextual WM-Specific Factors
Incorporate mathematical correction factors for:
- Altitude acclimation curves (using stadium elevations).
- Climatic conditions (heat and humidity index).
- Travel and rest days (mileage and timezone transitions).
- Fan support / Host advantages.

### R3. Kicktipp Solver (Expected Value Maximization)
Strictly implement the 4/3/2 scoring system solver. For any pair of team strength inputs, the engine must iterate over possible score tips and output the exact tip that maximizes expected points:
$$E(t) = 4P(\text{Exact}) + 3P(\text{Diff}) + 2P(\text{Tendenz})$$

### R4. Backtesting and Validation
Implement a backtesting suite that evaluates the model using historical data (e.g., World Cup 2022 match results) and compares its Kicktipp points performance against the baseline Poisson model.

## Acceptance Criteria

### Functionality
- [ ] Core prediction engine runs without errors and accepts team strength/context parameters.
- [ ] Kicktipp solver successfully outputs the mathematically optimal tip with its expected value.
- [ ] Backtesting script executes successfully, printing a comparative report (baseline vs. optimized model).

### Performance & Accuracy
- [ ] The optimized model achieves higher total simulated points than the baseline independent Poisson model on historical match data.
