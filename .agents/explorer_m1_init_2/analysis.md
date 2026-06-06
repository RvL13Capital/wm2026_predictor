# Analysis Report: E2E Testing Infrastructure Design

## Executive Summary
This report presents the design and specification of the End-to-End (E2E) testing infrastructure for the FIFA World Cup 2026 Prediction Engine. In compliance with the project layout and the read-only exploration constraints, this document outlines the testing philosophy, feature inventory (F1–F4), test architecture, and a comprehensive suite of 49 test cases spanning four distinct test tiers. It also provides the exact proposed content for `TEST_INFRA.md` (to be created at the project root) and the proposed updates to `PROJECT.md`.

---

## 1. Codebase Analysis
The current workspace contains the following core files:
- **`ORIGINAL_REQUEST.md`**: Outlines the requirements for the advanced probability engine (R1), contextual factors (R2), Kicktipp solver (R3), and backtesting/validation (R4).
- **`PROJECT.md`**: Defines the project architecture, milestones, requirement mapping, interface contracts, and layout.
- **`predictor.py`**: A partial implementation of the prediction engine. It currently supports:
  - Base Poisson probability calculation.
  - Dixon-Coles adjustment for low-scoring matches (0-0, 1-0, 0-1, 1-1) using a correlation parameter `rho`.
  - A basic Kicktipp solver computing the optimal tip up to a specified `max_tip` (default 5).
  - Main CLI interface accepting `--lambdaA`, `--lambdaB`, `--rho`, and `--max_tip`.
  - Outcome tendencies (Home win, Draw, Away win) and exact score probabilities.

### Observations on Existing Code:
1. **Dixon-Coles Adjustment**: The logic in `solve_optimal_tip` correctly implements the adjustment factor matrix:
   - `(0, 0): 1.0 - rho * lam_A * lam_B`
   - `(1, 0): 1.0 + rho * lam_B`
   - `(0, 1): 1.0 + rho * lam_A`
   - `(1, 1): 1.0 - rho`
   This requires `lam_A > 0` and `lam_B > 0` to prevent division or domain errors, and the product adjustment is clipped at `0.0`.
2. **Missing Features (to be implemented in later milestones)**:
   - **Negative Binomial Model**: Not yet present in `predictor.py`. Needs to handle overdispersion with a dispersion parameter `alpha`.
   - **Contextual Factors (R2)**: Altitude acclimation curves, climatic conditions, travel and rest penalties, and host advantage calculations are not yet integrated into the CLI or core predictor function.
   - **Kicktipp Draw Rule Correction**: The current `get_points` function awards 3 points to wrong draws (e.g. Tip 2-2, Actual 1-1) because `diff_actual == diff_tip` (0 == 0). According to the plan in `PROJECT.md`, draw rule corrections must be applied such that wrong draws only receive tendency points (2 points), not difference points (3 points).
   - **Backtesting Suite**: No `backtest.py` or historical data files exist yet.

---

## 2. E2E Testing Philosophy & Architecture

### Testing Philosophy
- **Opaque-Box E2E Testing**: Tests must execute the software from its public entry points (primarily CLI commands and high-level interface contracts) rather than mocking inner helper methods.
- **Physical & Mathematical Realism**: Test cases must cover physically realistic values (e.g. altitudes, climates, rest intervals) and mathematically consistent probabilities (grid normalization, overdispersion behavior).
- **Integrity First**: No facade testing, hardcoded expectations, or shortcut implementations. The test runner must execute genuine computations.
- **Self-Containment**: The testing infrastructure should run without external network dependencies, using only the local filesystem and Python 3 standard library.

### Test Architecture
- **Location**: All test scripts, configuration files, and test runner reside under `tests/`.
- **Test Runner (`tests/run_e2e.py`)**: A centralized Python script that imports and executes all 49 test cases across the four tiers. It outputs a structured, colorized terminal summary, tracks execution time, and returns exit code `0` on total success and a non-zero exit code on any failure.
- **Tiers of Coverage**:
  - **Tier 1 (Feature Coverage)**: Verifies correctness of each individual feature (F1-F4) under standard operating conditions. (>=5 cases per feature; 20 total)
  - **Tier 2 (Boundary & Corner Cases)**: Pushes each feature to its mathematical or physical limits to ensure stability and graceful degradation. (>=5 cases per feature; 20 total)
  - **Tier 3 (Cross-Feature Combinations)**: Evaluates the integration and interaction between multiple features (e.g. how travel fatigue impacts the solver's decisions or how host advantage scales under high-altitude conditions). (>=4 cases; 4 total)
  - **Tier 4 (Real-World Application Scenarios)**: Simulates actual matches from the FIFA World Cup 2026 schedule, checking that the end-to-end flow produces realistic and optimal tipping recommendations. (>=5 cases; 5 total)
  - **Total Cases**: 49 test cases.

---

## 3. Complete Test Case Inventory (49 Cases)

### Tier 1: Feature Coverage (20 Cases)

#### F1: Advanced Probability Engine
- **T1_F1_1: Dixon-Coles Correlation Boost**
  - *Description*: Verify that setting $\rho > 0$ increases the probability of draws (0-0, 1-1) and decreases the probability of low-scoring non-draws (1-0, 0-1) compared to the independent Poisson product.
  - *Inputs*: $\lambda_A = 1.0, \lambda_B = 1.0, \rho = 0.15$.
  - *Expected*: $P(0,0)$ and $P(1,1)$ are larger than the baseline Poisson product, and $P(1,0)$ and $P(0,1)$ are smaller.
- **T1_F1_2: Negative Binomial Overdispersion Fatter Tails**
  - *Description*: Verify that the Negative Binomial model handles overdispersion by producing higher probabilities for high-scoring outcomes (e.g. $\ge 4$ goals) compared to the Poisson model for the same mean.
  - *Inputs*: Mean $\lambda_A = 2.0, \lambda_B = 2.0$, dispersion parameter $\alpha = 0.5$.
  - *Expected*: Probability of score $k \ge 4$ is higher under Negative Binomial than Poisson.
- **T1_F1_3: Probability Grid Normalization**
  - *Description*: Verify that the probability distribution grid sums to exactly $1.000$ (within floating-point tolerance $10^{-6}$) after applying Dixon-Coles adjustments.
  - *Inputs*: $\lambda_A = 1.8, \lambda_B = 1.2, \rho = -0.1$.
  - *Expected*: Sum of all $P(g_A, g_B)$ for $0 \le g_A, g_B \le 12$ is $1.0 \pm 10^{-6}$.
- **T1_F1_4: Outcome Probability Consistency**
  - *Description*: Verify that the sum of Home Win, Draw, and Away Win probabilities matches the sum of the corresponding cells in the normalized grid.
  - *Inputs*: $\lambda_A = 1.5, \lambda_B = 1.5, \rho = 0.0$.
  - *Expected*: $P(\text{Home}) + P(\text{Draw}) + P(\text{Away}) = 1.000$.
- **T1_F1_5: Zero Goal Rate Baseline**
  - *Description*: Verify that when both goal rates are zero, the probability of a 0-0 draw is exactly $1.0$.
  - *Inputs*: $\lambda_A = 0.0, \lambda_B = 0.0, \rho = 0.0$.
  - *Expected*: $P(0,0) = 1.0$, all other $P(g_A, g_B) = 0.0$.

#### F2: Contextual WM-Specific Factors
- **T1_F2_1: Altitude Acclimation Curve Penalty**
  - *Description*: Verify that a high-altitude stadium (e.g., Estadio Azteca at 2,240m) reduces the base scoring expectations (lambda) of a non-acclimated team.
  - *Inputs*: Base $\lambda = 1.5$, Altitude = 2240m, Acclimation Days = 2.
  - *Expected*: Adjusted $\lambda' < 1.5$.
- **T1_F2_2: Climate Heat-Humidity Index (Wet-Bulb Temperature) Penalty**
  - *Description*: Verify that high wet-bulb temperature equivalent conditions apply a fatigue penalty to team expectations.
  - *Inputs*: Base $\lambda = 1.8$, Temperature = 35°C, Humidity = 75%.
  - *Expected*: Adjusted $\lambda' < 1.8$ due to the heat fatigue curve.
- **T1_F2_3: Rest Days and Timezone Transition Travel Penalty**
  - *Description*: Verify that a team with significant travel distance and fewer rest days receives a strength penalty.
  - *Inputs*: Base $\lambda = 1.6$, Travel Distance = 4500 km, Timezones Crossed = 3, Rest Days = 3.
  - *Expected*: Adjusted $\lambda' < 1.6$.
- **T1_F2_4: Host Country Fan Support Advantage**
  - *Description*: Verify that a host country (USA, Mexico, Canada) receives a strength boost.
  - *Inputs*: Base $\lambda = 1.2$, Host Status = True.
  - *Expected*: Adjusted $\lambda' > 1.2$.
- **T1_F2_5: Neutral Field Baseline**
  - *Description*: Verify that when a match is played under baseline conditions (sea level, moderate climate, zero travel, equal rest, neutral field), no contextual corrections are applied.
  - *Inputs*: Altitude = 0m, Temp = 20°C, Humidity = 50%, Travel = 0km, Rest Days = 7, Host Status = False.
  - *Expected*: Adjusted $\lambda' = \lambda$.

#### F3: Kicktipp Solver (EV Maximization)
- **T1_F3_1: Kicktipp Exact Match (4 Points) Reward**
  - *Description*: Verify that the expected points calculation correctly applies 4 points to exact match cells and contributes to the expected value of a tip.
  - *Inputs*: Expected value calculation for tip (1,0) when actual score is (1,0).
  - *Expected*: Point contribution of 4 points weighted by $P(1,0)$.
- **T1_F3_2: Kicktipp Goal Difference Match (3 Points) Reward**
  - *Description*: Verify that the expected points calculation correctly applies 3 points for correct difference and tendency (e.g., tip is 2-1 and actual is 1-0).
  - *Inputs*: Expected value calculation for tip (2,1) against actual (1,0).
  - *Expected*: Point contribution of 3 points weighted by $P(1,0)$.
- **T1_F3_3: Kicktipp Tendency-Only (2 Points) Reward**
  - *Description*: Verify that a tip of a home win (e.g., 2-0) gets 2 points when the actual is a different home win (e.g., 1-0) and the goal difference is different.
  - *Inputs*: Expected value calculation for tip (2,0) against actual (1,0).
  - *Expected*: Point contribution of 2 points weighted by $P(1,0)$.
- **T1_F3_4: Kicktipp Incorrect Match (0 Points)**
  - *Description*: Verify that a tip of a home win (e.g., 2-0) gets 0 points when the actual is a draw (e.g., 1-1) or an away win (e.g., 0-1).
  - *Inputs*: Expected value calculation for tip (2,0) against actual (1,1).
  - *Expected*: Point contribution of 0 points.
- **T1_F3_5: Solver EV Maximization Decision**
  - *Description*: Verify that the solver iterates through all tips up to `max_tip` and selects the tip that mathematically maximizes the expected value.
  - *Inputs*: Probability grid where $P(2,0) = 0.3$, $P(1,0) = 0.2$, $P(0,0) = 0.2$.
  - *Expected*: Solver selects the tip that yields the highest $E(t) = 4P(\text{Exact}) + 3P(\text{Diff}) + 2P(\text{Tendenz})$.

#### F4: Backtesting and Validation
- **T1_F4_1: Historical Match Data Ingestion**
  - *Description*: Verify that the backtester correctly reads and parses historical match results (e.g., CSV format containing Team A, Team B, Goals A, Goals B, and date).
  - *Inputs*: Backtest data file path with valid entries.
  - *Expected*: The backtester loads all records without parsing errors.
- **T1_F4_2: Simulation Loop Execution**
  - *Description*: Verify that the backtester runs the prediction engine and solver for every match in the historical dataset.
  - *Inputs*: Small dataset of 5 historical matches.
  - *Expected*: The backtester generates a tip for each of the 5 matches.
- **T1_F4_3: Backtesting Points Accumulator**
  - *Description*: Verify that the backtester correctly calculates the total Kicktipp points accumulated by the optimized model across the historical matches.
  - *Inputs*: 3 matches with known simulated tips and actual scores (e.g., Match 1: Tip 2-1, Actual 2-1 [4pts]; Match 2: Tip 2-0, Actual 3-1 [3pts]; Match 3: Tip 1-0, Actual 0-1 [0pts]).
  - *Expected*: Accumulated points = 7.
- **T1_F4_4: Comparative Performance Evaluation**
  - *Description*: Verify that the backtest output includes a comparative report showing total points, exact tips, difference tips, tendency tips, and total points for both the baseline model and the optimized model.
  - *Inputs*: Execution of backtest on WC 2022 dataset.
  - *Expected*: Report printed with clear comparative statistics for both models.
- **T1_F4_5: Validation Constraint Check**
  - *Description*: Verify that the backtester returns success only when the optimized model outperforms or equals the baseline model in total points.
  - *Inputs*: Backtesting run comparing optimized model vs baseline model.
  - *Expected*: Output report proves optimized model score $\ge$ baseline model score.

---

### Tier 2: Boundary & Corner Cases (20 Cases)

#### F1: Advanced Probability Engine
- **T2_F1_1: Extreme Goals Output (`max_goals` upper bound)**
  - *Description*: Verify that the engine behaves correctly when `max_goals` is configured to very large values (e.g., 20) and doesn't run out of memory.
  - *Inputs*: $\lambda_A = 4.0, \lambda_B = 4.0, \text{max\_goals} = 20$.
  - *Expected*: Probability grid of size 21x21 is computed, normalized, and sums to 1.0.
- **T2_F1_2: Extreme Goal Rates ($\lambda \to 0$ or high value)**
  - *Description*: Verify engine stability when $\lambda_A$ is extremely high (e.g., 10.0, representing a massive mismatch) or close to 0 (e.g., 0.001).
  - *Inputs*: $\lambda_A = 10.0, \lambda_B = 0.01$.
  - *Expected*: Calculations do not overflow or division-by-zero, and probability peaks at extreme values.
- **T2_F1_3: Dixon-Coles Correlation Parameter ($\rho$) Out of Bounds**
  - *Description*: Verify that the engine safely caps or raises an error when $\rho$ is set beyond physical limits (where adjustments would result in negative probabilities).
  - *Inputs*: $\lambda_A = 1.0, \lambda_B = 1.0$, extreme $\rho = 2.0$ or $\rho = -2.0$.
  - *Expected*: Probabilities are clipped to $\ge 0.0$ and renormalized, or a validation error is thrown.
- **T2_F1_4: Negative Binomial dispersion ($\alpha \to 0$)**
  - *Description*: Verify that when the dispersion parameter $\alpha$ in Negative Binomial approaches 0, the distribution converges to the Poisson distribution with the same mean.
  - *Inputs*: $\lambda = 2.0$, $\alpha = 10^{-6}$.
  - *Expected*: Negative Binomial probabilities match Poisson probabilities within $10^{-4}$ tolerance.
- **T2_F1_5: Floating Point Underflow Protection**
  - *Description*: Verify that very low probability cells (e.g. $P(12, 12)$ when $\lambda = 0.1$) do not cause underflow crashes or division by zero during normalization.
  - *Inputs*: $\lambda_A = 0.1, \lambda_B = 0.1, \text{max\_goals} = 12$.
  - *Expected*: Engine completes successfully; underflow values are handled as $0.0$ without causing errors.

#### F2: Contextual WM-Specific Factors
- **T2_F2_1: Extreme Altitude (Above acclimation limits)**
  - *Description*: Verify that an extreme altitude input (e.g., La Paz at 4,000m) is handled gracefully without dividing by zero or producing negative lambda.
  - *Inputs*: Base $\lambda = 1.5$, Altitude = 4000m, Acclimation = 0 days.
  - *Expected*: Adjusted $\lambda' \ge 0.1$ (lambda is capped at a positive minimum value).
- **T2_F2_2: Severe Weather (Extreme heat and humidity)**
  - *Description*: Verify that extreme wet-bulb temperatures (e.g. 45°C wet-bulb) apply the maximum fatigue penalty but do not reduce lambda to zero or negative.
  - *Inputs*: Base $\lambda = 2.0$, Temp = 48°C, Humidity = 90%.
  - *Expected*: $\lambda'$ is adjusted downwards but capped at a minimum baseline (e.g., 0.1).
- **T2_F2_3: Back-to-Back Match Travel Fatigue (Minimum rest, maximum travel)**
  - *Description*: Verify that playing a match with minimum rest (2 days) after crossing multiple timezones and maximum travel distance (5,000 km) applies the maximum travel penalty correctly.
  - *Inputs*: Base $\lambda = 1.8$, Rest Days = 2, Travel = 5000 km, Timezones Crossed = 4.
  - *Expected*: Penalty reaches its mathematical cap; lambda is reduced significantly but remains positive.
- **T2_F2_4: Double Host Match (Both host teams)**
  - *Description*: Verify how host advantage behaves when two host nations play each other (e.g., USA vs Mexico in the knockout stage).
  - *Inputs*: Team A = USA (Host), Team B = Mexico (Host).
  - *Expected*: Either both receive a host boost (neutralizing the relative advantage), or host advantage is set to neutral/zero.
- **T2_F2_5: Invalid/Negative Context Inputs**
  - *Description*: Verify that the system validates and handles invalid inputs like negative altitude, negative travel distance, or negative rest days.
  - *Inputs*: Altitude = -100m, Rest Days = -1.
  - *Expected*: System rejects input with ValueError or caps inputs to logical minimums.

#### F3: Kicktipp Solver
- **T2_F3_1: Extreme `max_tip` setting (Upper bound)**
  - *Description*: Verify that if `max_tip` is set to a large value (e.g. 10), the search space (121 combinations) does not cause execution timeouts or performance degradation.
  - *Inputs*: $\lambda_A = 2.5, \lambda_B = 2.5, \text{max\_tip} = 10$.
  - *Expected*: Optimal tip is resolved in < 0.1 seconds.
- **T2_F3_2: Zero-Goal Expectation Optimal Tip**
  - *Description*: Verify that when probabilities overwhelmingly favor a 0-0 draw, the solver outputs 0-0 as the optimal tip.
  - *Inputs*: $\lambda_A = 0.05, \lambda_B = 0.05, \rho = 0.1$.
  - *Expected*: Optimal tip is 0-0.
- **T2_F3_3: High scoring expectation tip capping**
  - *Description*: Verify that if expectations are very high (e.g., $\lambda_A = 7.0, \lambda_B = 7.0$), the solver's optimal tip is capped at `max_tip` and does not throw index errors.
  - *Inputs*: $\lambda_A = 7.0, \lambda_B = 7.0, \text{max\_tip} = 5$.
  - *Expected*: Optimal tip is capped within 5-5 range.
- **T2_F3_4: Flat Probability Distribution Ties**
  - *Description*: Verify solver behavior when there is a tie in expected value between two tips (e.g. 1-0 and 2-1 having identical expected values).
  - *Inputs*: Uniform probability grid or symmetric grid.
  - *Expected*: Solver resolves the tie deterministically (e.g., lower goal difference, or lexicographical order).
- **T2_F3_5: Kicktipp Draw Rule Correction (Milestone 3 draw rule)**
  - *Description*: Verify that a wrong draw tip (e.g., tipping 2-2 when the match ends 1-1) receives only tendency points (2 pts) and NOT goal difference points (3 pts), as required by the special draw rule logic.
  - *Inputs*: Tip = 2-2, Actual score = 1-1.
  - *Expected*: Point output from scoring function is 2 points, not 3 points.

#### F4: Backtesting and Validation
- **T2_F4_1: Empty historical dataset**
  - *Description*: Verify that running the backtesting suite with an empty match dataset raises an appropriate error or warning rather than crashing.
  - *Inputs*: Empty CSV file or list.
  - *Expected*: File is parsed, and a warning/error is raised indicating no matches found to backtest.
- **T2_F4_2: Missing columns in historical data**
  - *Description*: Verify that the backtester handles malformed CSV files (missing score columns or team name columns) by skipping or raising validation errors.
  - *Inputs*: CSV file missing the "Goals A" column.
  - *Expected*: Backtester catches the missing field and raises a descriptive `KeyError`.
- **T2_F4_3: Single Match Backtest**
  - *Description*: Verify that the backtest suite runs correctly and prints statistics for a dataset containing exactly one match.
  - *Inputs*: CSV with a single match (e.g. Qatar vs Ecuador).
  - *Expected*: Total points equal the points of that single match tip.
- **T2_F4_4: All Draw actual outcomes**
  - *Description*: Verify backtester performance when all actual matches in the historical dataset are draws.
  - *Inputs*: Dataset where every match ended 1-1.
  - *Expected*: Backtester correctly computes points, verifying how draw bias adjustments (Dixon-Coles) affect points compared to baseline.
- **T2_F4_5: Zero point baseline performance**
  - *Description*: Verify backtesting evaluation when the baseline model scores 0 points (e.g., every match is predicted 0-0 but actual scores are high-scoring wins).
  - *Inputs*: Dataset with matches like 5-0, 4-1 where baseline tips are off.
  - *Expected*: Comparative report shows baseline points = 0 and optimized model points > 0.

---

### Tier 3: Cross-Feature Combinations (4 Cases)

- **T3_F1_F2: Dixon-Coles Interaction with Host Advantage**
  - *Description*: Test the interaction between the Dixon-Coles adjustment ($\rho$) and the host advantage contextual factor. Host advantage boosts a team's base $\lambda$, which in turn changes the low-score probabilities adjusted by $\rho$.
  - *Inputs*: Base $\lambda_A = 1.0, \lambda_B = 1.0$. Team A is Host (host advantage = 1.15x $\lambda$). $\rho = -0.1$.
  - *Expected*: The host advantage boosts $\lambda_A$ to $1.15$. The Dixon-Coles adjustment then uses $\lambda_A' = 1.15$ in the adjustment term: $(0,0): 1.0 - \rho \lambda_A' \lambda_B$. Verify that the resulting grid correctly integrates both factors.
- **T3_F2_F3: Extreme Altitude Contextual Factor and Solver Capping**
  - *Description*: Test how extreme altitude adjustments (which heavily reduce $\lambda$) interact with the solver's optimal tip decision. Highly reduced $\lambda$ values should shift the solver's optimal tip to a very low-scoring option (like 0-0 or 1-0).
  - *Inputs*: Base $\lambda_A = 1.6, \lambda_B = 1.4$. Match played at 3000m (heavy penalty). Solver evaluates optimal tip.
  - *Expected*: The altitude penalty reduces adjusted $\lambda_A'$ and $\lambda_B'$ to near 0.5. The solver's optimal tip shifts from 2-1 (typical for 1.6 vs 1.4) to 1-0 or 0-0.
- **T3_F1_F3: Negative Binomial Overdispersion and Solver Decision**
  - *Description*: Test how switching from Poisson to Negative Binomial distribution affects the solver's expected points calculation. Negative Binomial with high dispersion increases the variance of goals, which should make draw tips or low-score tips less attractive because of higher likelihood of outlier scores (like 3-3 or 4-2).
  - *Inputs*: $\lambda_A = 2.0, \lambda_B = 2.0$. Case A: Poisson model. Case B: Negative Binomial with dispersion $\alpha = 0.5$. Solver runs on both.
  - *Expected*: Case A (Poisson) optimal tip might be 2-2 or 1-1, whereas Case B (Negative Binomial) shifts optimal tip to 2-1 or 1-2 because the increased probability of high scores makes exact draw tips riskier.
- **T3_F2_F4: Travel Fatigue and Backtest Validation**
  - *Description*: Test how travel fatigue and rest days are applied across a sequence of historical matches in the backtester. Ensure that the backtester correctly tracks rest days and travel distance from match history data and applies the corresponding penalty to the prediction engine.
  - *Inputs*: Backtester reads a sequence of 3 matches for Germany: Match 1 (day 1, home), Match 2 (day 4, 3000km travel, 3 days rest), Match 3 (day 7, 0km travel, 3 days rest).
  - *Expected*: The backtester correctly applies the travel penalty to Germany in Match 2, but applies a smaller or zero penalty in Match 3 (since travel is 0). The simulated tips change accordingly.

---

### Tier 4: Real-World Application Scenarios (5 Cases)

- **T4_S1: Opening Match at Estadio Azteca (Mexico vs. Lower Ranked Team)**
  - *Description*: Mexico plays their opening match at Estadio Azteca (Mexico City, altitude 2,240m). Mexico is accustomed to the altitude (no acclimation penalty), while the opponent arrives 2 days before the match (heavy acclimation penalty). Mexico also has host advantage.
  - *Inputs*: Mexico base $\lambda = 1.8$ (Host = True, Altitude acclimated = True). Opponent base $\lambda = 1.0$ (Host = False, Altitude acclimated = False, 2 days acclimation, Altitude = 2240m).
  - *Expected*: Mexico's adjusted $\lambda_A' = 2.1$. Opponent's adjusted $\lambda_B' = 0.7$. Optimal tip is calculated as 2-0 or 3-0 in favor of Mexico.
- **T4_S2: Mid-Summer Heat in Houston (USA vs. European Giant)**
  - *Description*: USA plays a European giant in NRG Stadium, Houston in July. Heat and humidity are high. USA has home advantage and is better acclimated to the summer climate. The European team suffers a large climate penalty.
  - *Inputs*: USA base $\lambda = 1.3$ (Host = True, Climate penalty = Low). Europe base $\lambda = 1.9$ (Host = False, Climate penalty = High due to 35°C temperature and 80% humidity).
  - *Expected*: USA's adjusted $\lambda_A' = 1.4$. Europe's adjusted $\lambda_B' = 1.4$. The solver shifts the optimal tip from a strong away win (e.g. 1-2) to a tight draw (e.g. 1-1) or close home win.
- **T4_S3: Coast-to-Coast Travel Strain (Canada Knockout Match)**
  - *Description*: Canada plays a Round of 32 match in Miami after playing their last group stage match in Vancouver. They travel 4,400 km, cross 3 time zones, and have only 4 days of rest. Their opponent played their group match in Orlando (close to Miami) and has 6 days of rest.
  - *Inputs*: Canada base $\lambda = 1.5$ (Host = True, Travel = 4400km, Timezones = 3, Rest = 4). Opponent base $\lambda = 1.5$ (Host = False, Travel = 350km, Timezones = 0, Rest = 6).
  - *Expected*: Canada's adjusted $\lambda_A'$ is penalized to 1.1 despite host status. Opponent's adjusted $\lambda_B' = 1.5$. Optimal tip shifts from home win or draw to away win (e.g. 1-2).
- **T4_S4: High-Scoring Knockout Mismatch (Argentina vs. Qualifier)**
  - *Description*: Argentina plays a lower-ranked qualifier team in a high-scoring stadium (sea level, climate-controlled, e.g., AT&T Stadium). We expect a high variance in goals, so we use the Negative Binomial model to capture the risk of high scores.
  - *Inputs*: Argentina base $\lambda = 3.2$, Qualifier base $\lambda = 0.5$. Dispersion $\alpha = 0.4$.
  - *Expected*: The Negative Binomial distribution assigns a significant probability to scores like 4-0, 4-1, 5-0. The Kicktipp solver evaluates these probabilities and returns a tip like 3-0 or 4-0.
- **T4_S5: Group Stage Decider (Low-Scoring Tactical Draw)**
  - *Description*: Two defensive teams play their final group stage match where a draw guarantees both teams progress. A highly correlated Dixon-Coles draw adjustment ($\rho = 0.15$) is applied, reflecting tactical match setup.
  - *Inputs*: Team A base $\lambda = 0.9$, Team B base $\lambda = 0.8$, $\rho = 0.15$ (high draw correlation).
  - *Expected*: The Dixon-Coles correlation significantly boosts the probability of 0-0 and 1-1. The Kicktipp solver outputs 1-1 as the optimal tip, showing the effect of modeling draw correlation.

---

## 4. Proposed `TEST_INFRA.md` Content
Below is the full design content to be written to `TEST_INFRA.md` at the project root by the implementation subagent:

```markdown
# End-to-End Testing Infrastructure Design Specification

## 1. Testing Philosophy
The FIFA World Cup 2026 Prediction Engine's testing infrastructure enforces an **opaque-box E2E testing methodology**.
- **Public APIs and CLI Entry Points**: Tests exercise the prediction pipeline via command-line arguments and standard Python interfaces, validating the behavior of the engine exactly as a user or backtesting system would.
- **Physical and Mathematical Realism**: The test cases are grounded in realistic inputs (e.g., stadium elevation, climate records, timezone deltas) and evaluate that the mathematical calculations (Dixon-Coles adjustments, Negative Binomial dispersion, and Kicktipp EV maximization) produce theoretically sound outputs.
- **Strict Anti-Facade Constraints**: Dummy implementations, hardcoded outputs, or mocked calculations are strictly forbidden. The engine must perform genuine mathematical calculations, and tests must verify the results using derived mathematical expected boundaries.

## 2. Feature Inventory
The test suite validates four primary feature domains:
- **F1: Advanced Probability Engine**: Bivariate Poisson distribution, Dixon-Coles low-score adjustments, Negative Binomial overdispersion calculations, probability grid normalization, and output consistency.
- **F2: Contextual WM-Specific Factors**: Impact of elevation (altitude acclimation curves), climate (wet-bulb equivalent heat/humidity penalties), travel fatigue (mileage and timezone cross deltas), and host country advantage boosts.
- **F3: Kicktipp Solver (EV Maximization)**: Implementation of the 4/3/2 scoring system solver. Correct calculation of EV over the `max_tip` space, and proper handling of the draw rule correction (wrong draws awarded 2 points instead of 3).
- **F4: Backtesting and Validation**: Ingestion of historical data, E2E simulation execution, accumulation of total simulated points, comparison against baseline Poisson models, and validating that the optimized engine outperforms the baseline on historical match sets.

## 3. Test Architecture
- **Location**: All test scripts are placed in the `tests/` directory at the project root.
- **Test Runner (`tests/run_e2e.py`)**:
  - Automatically discovers and runs all tests.
  - Groups tests by Tier and Feature.
  - Validates outputs against mathematical invariants (e.g., sum of probabilities equals 1.0, optimal tips lie within configured limits).
  - Tracks total execution time.
  - Returns exit code `0` on successful completion of all tests, and non-zero on any failures.

## 4. Test Tiers and Case Directory
The testing suite contains **49 test cases** divided into four tiers:

### Tier 1: Feature Coverage (20 cases)
Provides base coverage for F1-F4 under standard, nominal conditions:
- **T1_F1_1** to **T1_F1_5**: Cover Bivariate Poisson, Negative Binomial, Dixon-Coles draw correlation, grid normalization, and zero-rate baseline.
- **T1_F2_1** to **T1_F2_5**: Cover altitude acclimation, climate/heat penalties, travel fatigue penalties, host country advantage, and neutral field baseline.
- **T1_F3_1** to **T1_F3_5**: Cover exact score reward (4 pts), difference reward (3 pts), tendency reward (2 pts), incorrect match (0 pts), and solver EV maximization decision.
- **T1_F4_1** to **T1_F4_5**: Cover backtest data ingestion, simulation loop execution, points accumulator, comparative reporting, and validation constraint check.

### Tier 2: Boundary and Corner Cases (20 cases)
Validates extreme, unusual, or boundary conditions to ensure robustness:
- **T2_F1_1** to **T2_F1_5**: Extreme `max_goals` bounds (e.g., 20), extreme lambda values, out-of-bounds Dixon-Coles parameters ($\rho = \pm 2.0$), Negative Binomial convergence to Poisson ($\alpha \to 0$), and floating point underflow protection.
- **T2_F2_1** to **T2_F2_5**: Extreme altitude (above acclimation limit), severe climate (extreme wet-bulb temperature), minimum rest with maximum travel, double-host neutralizations, and invalid negative inputs.
- **T2_F3_1** to **T2_F3_5**: Extreme `max_tip` setting (e.g., 10), zero-goal expectation optimal tip, high scoring expectation capping, flat probability ties, and Kicktipp draw rule correction (2 points vs 3 points for wrong draws).
- **T2_F4_1** to **T2_F4_5**: Empty historical dataset, missing columns in data, single match backtest, all-draw historical outcomes, and zero-point baseline performance.

### Tier 3: Cross-Feature Combinations (4 cases)
Tests the interaction of multiple subsystems:
- **T3_F1_F2 (Dixon-Coles & Host Advantage)**: Validates that host-boosted lambdas are correctly integrated into the Dixon-Coles adjustment terms.
- **T3_F2_F3 (Altitude & Solver Capping)**: Validates that high-altitude penalties shift the optimal tip choice to low-scoring profiles.
- **T3_F1_F3 (Negative Binomial & Solver)**: Tests how overdispersion under Negative Binomial alters EV calculations compared to standard Poisson, shifting optimal tips away from high-risk draws.
- **T3_F2_F4 (Travel Fatigue & Backtester)**: Validates that the backtester correctly updates and carries over rest days and travel penalties for a team across consecutive match fixtures.

### Tier 4: Real-World Application Scenarios (5 cases)
End-to-end simulations of actual 2026 tournament conditions:
- **T4_S1 (Azteca Altitude)**: Mexico vs. Non-Acclimated Opponent at Estadio Azteca.
- **T4_S2 (Houston Heat)**: USA vs. European Giant in high heat/humidity.
- **T4_S3 (Travel Strain)**: Canada playing in Miami after a long flight from Vancouver with short rest.
- **T4_S4 (High-Scoring Mismatch)**: Argentina vs. lower-ranked Qualifier under Negative Binomial.
- **T4_S5 (Group Stage Decider)**: Tactical draw simulation between two defensive teams using Dixon-Coles correlation.

## 5. Execution Guide
To run the E2E test suite:
```bash
python3 tests/run_e2e.py
```
This command runs all 49 tests and prints detailed reports. It returns `0` only if all tests pass.
```
```

---

## 5. Proposed `PROJECT.md` Changes

The following diff shows the proposed updates to `PROJECT.md` to set Milestone 1 to `IN_PROGRESS` and associate it with the caller conversation ID:

```markdown
<<<<
| 1 | E2E Testing Track | Design and build the E2E test suite (Tiers 1-4) | None | PLANNED |
====
| 1 | E2E Testing Track | Design and build the E2E test suite (Tiers 1-4) | None | IN_PROGRESS (Conv: 4606a3e4-1e6e-445b-8297-9307c4ee54d6) |
>>>>
```
This change documents that the E2E testing track is active and coordinates progress under the specified conversation thread.
