# Analysis & Design Report: E2E Testing Infrastructure

This document contains the detailed design, testing philosophy, and the complete test suite of 49 cases for the FIFA World Cup 2026 Prediction Engine. It also provides the exact content proposed for `TEST_INFRA.md` and the modifications to `PROJECT.md`.

---

## 1. Codebase Analysis & Integration Design

### Current State:
1. `predictor.py`: Implements a basic Bivariate Poisson model with Dixon-Coles adjustments for low scores (0-0, 1-0, 0-1, 1-1). It supports standard argument parsing via command-line arguments: `--teamA`, `--teamB`, `--lambdaA`, `--lambdaB`, `--rho`, `--max_tip`. It calculates Kicktipp points for a tip vs actual outcome and computes expected points for all tips inside the tip grid.
2. `PROJECT.md` & `ORIGINAL_REQUEST.md`: Specify four core features:
   - **F1: Advanced Probability Engine** (Poisson, Bivariate Poisson/Dixon-Coles, Negative Binomial).
   - **F2: Contextual Factors** (Altitude, Climate, Travel/Rest, Fan/Host Support).
   - **F3: Kicktipp Solver** (4/3/2 EV Maximization).
   - **F4: Backtesting and Validation** (historical evaluation & baseline comparison on WC 2022 data).

### Integration Interface Contracts (Proposed for implementation agents):
To run automated E2E tests, the executables must support CLI arguments. We define the contract as follows:

#### `predictor.py` CLI Options:
* `--model`: Distribution model to use: `poisson` (default) or `negbin`.
* `--lambdaA`, `--lambdaB`: Base expected goals (float).
* `--dispersionA`, `--dispersionB`: Overdispersion parameters for Negative Binomial (float, default: `1.0`).
* `--rho`: Dixon-Coles draw correlation parameter (float, default: `-0.05`).
* `--elevation`: Stadium elevation in meters (integer, default: `0`).
* `--acclA`, `--acclB`: Acclimation days for Team A and Team B (integer, default: `0`).
* `--temp`: Stadium temperature in °C (float, default: `20.0`).
* `--humidity`: Stadium relative humidity percentage (float, default: `50.0`).
* `--distA`, `--distB`: Travel distance in miles (integer, default: `0`).
* `--tzA`, `--tzB`: Timezones crossed (integer, default: `0`).
* `--restA`, `--restB`: Rest days (integer, default: `4`).
* `--host`: Designation of home team or host status: `A` (Team A is host/home), `B` (Team B is host/home), `none` (neutral ground, default).
* `--fanA`, `--fanB`: Percentage of fan support in stadium (integer, e.g., `50` / `50`, default).
* `--max_tip`: Max goals to tip (integer, default: `5`).
* `--json`: Flag to output results as a standardized JSON structure for automated test validation.

#### `backtest.py` CLI Options:
* `--dataset`: Path to CSV file containing historical matches (e.g. `data/wc2022.csv`).
* `--baseline`: Model to use as baseline (e.g. `poisson_only`).
* `--optimized`: Model to use as optimized (e.g. `dixon_coles_context`).
* `--json`: Output summary report in JSON format for the test runner.

---

## 2. Proposed Content for `TEST_INFRA.md`

Below is the complete text designed for `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/TEST_INFRA.md`.

```markdown
# E2E Testing Infrastructure: FIFA World Cup 2026 Prediction Engine

This document outlines the testing philosophy, feature inventory, test runner architecture, and the complete catalog of 49 end-to-end (E2E) test cases.

---

## 1. Testing Philosophy
The E2E testing framework is designed as an **opaque-box testing framework**. It evaluates the prediction engine by executing its public command-line interfaces (`predictor.py` and `backtest.py`) rather than asserting internal code states. 

Key principles:
1. **Reproducibility**: All tests must use deterministic configurations or mock values where external randomness exists.
2. **Contract-Based Assertions**: Tests assert on boundary ranges, exact outcomes, or expected physical adjustments (e.g. travel distance must always penalize/reduce performance or keep it constant, never boost it).
3. **Graceful Degradation**: Invalid inputs must result in clean CLI error codes (non-zero exits) and explanatory stderr logs.
4. **Validation of Mathematical Correctness**: Asserts that probability distributions sum to 1.0, and Kicktipp EV maximization correctly identifies the tip with highest expected points.

---

## 2. Feature Inventory
* **F1: Advanced Probability Engine**
  - Standard Independent Poisson distribution.
  - Bivariate Poisson distribution with Dixon-Coles adjustments (low scores correction).
  - Negative Binomial distribution to model overdispersion (high-scoring outliers).
* **F2: Contextual WM-Specific Factors**
  - Altitude acclimation curves (meters and acclimation days).
  - Climatic conditions (temperature and relative humidity).
  - Travel and rest days (mileage, timezone transitions, and rest days).
  - Fan support and host advantage (neutral vs. home ground, fan percentage).
* **F3: Kicktipp Solver (EV Maximization)**
  - 4/3/2 scoring point rule evaluation.
  - Expectation calculation over the grid.
  - Sorting and identification of the optimal tip.
* **F4: Backtesting and Validation**
  - Batch simulation on historical WC 2022 match data.
  - Points tally comparison between baseline and optimized models.

---

## 3. Test Architecture & Runner Design
The testing files are located in the `tests/` directory:
- `tests/run_e2e.py`: Main test runner script.
- `tests/test_cases.json`: Declarative test suite definition.

### Opaque-Box Execution Model
The runner executes CLI commands via subprocesses and validates outputs:
1. Parse `tests/test_cases.json` containing test definitions.
2. Formulate the CLI command (e.g., `python3 predictor.py --lambdaA X --lambdaB Y ... --json`).
3. Execute the process, capture stdout and stderr, and verify the exit code.
4. If `--json` flag is utilized, parse stdout as JSON and assert on specific fields (e.g., `optimal_tip`, `outcomes.home`, `expected_points`). Otherwise, use regex pattern matching on text.

### Test Result Reporting
The runner prints a structured report to stdout:
```text
[PASS] TC-T1-F1-01: Standard Independent Poisson baseline prediction
[PASS] TC-T1-F2-01: Altitude Acclimation adjustment
...
E2E Test Results: 49/49 Passed (100.0% Success Rate)
```
If any test fails, it prints details of the failed assertions, command run, and returns exit code `1`.

---

## 4. Complete Test Suite Catalog (49 Test Cases)

### Tier 1: Feature Coverage (>=5 cases per feature)

#### Feature 1: Advanced Probability Engine (F1)
* **TC-T1-F1-01: Poisson Baseline Verification**
  - **Inputs**: `--lambdaA 1.5 --lambdaB 1.0 --rho 0.0 --model poisson`
  - **Expected Outcome**: Home win probability ~44.9%, Draw ~23.1%, Away win ~32.0%. Probability matrix sum = 1.0.
  - **Rationale**: Asserts that standard independent Poisson behaves identically to baseline mathematical calculations.
* **TC-T1-F1-02: Bivariate Dixon-Coles Positive Correlation**
  - **Inputs**: `--lambdaA 1.5 --lambdaB 1.0 --rho 0.1 --model poisson`
  - **Expected Outcome**: Probability of 0-0, 1-1 increased compared to TC-T1-F1-01. Probability of 1-0, 0-1 decreased.
  - **Rationale**: Validates Dixon-Coles correlation parameter adjusts low scores properly.
* **TC-T1-F1-03: Bivariate Dixon-Coles Negative Correlation**
  - **Inputs**: `--lambdaA 1.5 --lambdaB 1.0 --rho -0.1 --model poisson`
  - **Expected Outcome**: Probability of 0-0, 1-1 decreased compared to TC-T1-F1-01. Probability of 1-0, 0-1 increased.
  - **Rationale**: Validates negative correlation adjustments decrease draw probabilities.
* **TC-T1-F1-04: Negative Binomial Overdispersion Model**
  - **Inputs**: `--lambdaA 2.5 --lambdaB 2.5 --dispersionA 2.0 --dispersionB 2.0 --model negbin`
  - **Expected Outcome**: Elevated probability of extreme high goal counts (>= 4 goals per team) compared to standard Poisson.
  - **Rationale**: Confirms Negative Binomial handles overdispersion and tail probabilities.
* **TC-T1-F1-05: Probability Grid Normalization**
  - **Inputs**: `--lambdaA 4.2 --lambdaB 3.8 --rho 0.05 --model poisson --max_tip 8`
  - **Expected Outcome**: Sum of all probabilities in the internal $12 \times 12$ grid equals 1.0 (tolerance $\pm 1e-6$).
  - **Rationale**: Ensures the probability engine normalizes the grid after adjustments.

#### Feature 2: Contextual WM-Specific Factors (F2)
* **TC-T1-F2-01: Altitude Acclimation Penalty**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --elevation 2500 --acclA 2 --acclB 14`
  - **Expected Outcome**: Adjusted lambda for Team A (2 days acclimation) is strictly less than Team B (14 days acclimation).
  - **Rationale**: Verifies that low acclimation at high altitudes penalizes team rating.
* **TC-T1-F2-02: Climatic Heat and Humidity Penalty**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --temp 36.0 --humidity 85.0`
  - **Expected Outcome**: Both teams' adjusted lambdas are lower than base ratings of 2.0.
  - **Rationale**: Tests extreme climate performance decay factor.
* **TC-T1-F2-03: Travel and Rest Days Penalty**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --distA 5000 --tzA 8 --restA 3 --distB 200 --tzB 0 --restB 6`
  - **Expected Outcome**: Team A (long travel, low rest) lambda is penalised more than Team B (short travel, high rest).
  - **Rationale**: Verifies travel mileage, timezone transitions, and low rest days apply penalties correctly.
* **TC-T1-F2-04: Host Support Multiplier**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --host A --fanA 80 --fanB 20`
  - **Expected Outcome**: Team A's adjusted lambda is strictly greater than 2.0; Team B's lambda remains at 2.0 or is penalized.
  - **Rationale**: Tests host country and fan distribution advantage.
* **TC-T1-F2-05: Contextual Combinatorial Bounds**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --elevation 3000 --acclA 1 --temp 35 --humidity 80 --distA 4000 --tzA 6 --restA 3`
  - **Expected Outcome**: Combined penalty scales down lambdaA, but adjusted lambdaA remains strictly greater than or equal to 0.1 (non-negative clamping).
  - **Rationale**: Ensures compounding penalties do not lead to zero or negative lambdas.

#### Feature 3: Kicktipp Solver (F3)
* **TC-T1-F3-01: EV Grid Search Completeness**
  - **Inputs**: `--lambdaA 1.6 --lambdaB 1.2 --max_tip 5`
  - **Expected Outcome**: The runner outputs expected values for exactly 36 tip combinations ($0 \times 0$ to $5 \times 5$).
  - **Rationale**: Confirms the solver does a complete grid search.
* **TC-T1-F3-02: Deterministic 4-Point Exact Score Assert**
  - **Inputs**: `--lambdaA 0.001 --lambdaB 0.001`
  - **Expected Outcome**: The optimal tip is 0:0 with an expected value (EV) close to 4.0 points.
  - **Rationale**: If a 0-0 score is practically certain, the solver must tip 0-0 to maximize EV to 4 points.
* **TC-T1-F3-03: Correct Difference 3-Point Assert**
  - **Inputs**: `--lambdaA 3.0 --lambdaB 1.0 --max_tip 5` (symmetric distribution centered around +2 goals difference)
  - **Expected Outcome**: The optimal tip has a goal difference of +2 (e.g. 2:0 or 3:1) rather than a draw or away tip.
  - **Rationale**: Validates the solver captures expected differences in its calculations.
* **TC-T1-F3-04: Correct Tendency 2-Point Assert**
  - **Inputs**: `--lambdaA 1.8 --lambdaB 1.7 --max_tip 5`
  - **Expected Outcome**: The optimal tip is 2:1 or 1:1, securing the high probability tendency.
  - **Rationale**: High uncertainty games should tip draw or narrow home wins to secure the 2 points tendency rule.
* **TC-T1-F3-05: Tip Output Sorting**
  - **Inputs**: `--lambdaA 1.5 --lambdaB 1.2 --max_tip 5`
  - **Expected Outcome**: The top 5 printed tips are strictly in descending order of Expected Value.
  - **Rationale**: Confirms the solver displays optimal choices sorted correctly.

#### Feature 4: Backtesting and Validation (F4)
* **TC-T1-F4-01: Backtest Suite Execution**
  - **Inputs**: `python3 backtest.py --dataset data/wc2022_test.csv`
  - **Expected Outcome**: Script exits with code 0.
  - **Rationale**: Basic execution test of backtest.py.
* **TC-T1-F4-02: Side-by-Side Model Comparison Output**
  - **Inputs**: `python3 backtest.py --dataset data/wc2022_test.csv`
  - **Expected Outcome**: Output logs print comparative columns for baseline vs optimized model.
  - **Rationale**: Ensures the report prints comparative metrics.
* **TC-T1-F4-03: Points Accumulation Calculation**
  - **Inputs**: `python3 backtest.py --dataset data/wc2022_test.csv`
  - **Expected Outcome**: Cumulative score is correct based on the individual match tipping points.
  - **Rationale**: Validates backtest.py uses the exact 4/3/2 scoring logic to tally total points.
* **TC-T1-F4-04: Match-by-Match Breakdown Format**
  - **Inputs**: `python3 backtest.py --dataset data/wc2022_test.csv --verbose`
  - **Expected Outcome**: Match details (Teams, Actual score, Model Tip, Points earned) are outputted.
  - **Rationale**: Verifies granular logging output structure.
* **TC-T1-F4-05: Baseline vs. Optimized Performance Comparison**
  - **Inputs**: `python3 backtest.py --dataset data/wc2022_test.csv`
  - **Expected Outcome**: Total points for the optimized model is verified to be greater than or equal to the baseline model.
  - **Rationale**: Confirms accuracy acceptance criteria on historical test sets.

---

### Tier 2: Boundary & Corner Cases (>=5 cases per feature)

#### Feature 1: Advanced Probability Engine (F1 - Boundary/Corner)
* **TC-T2-F1-01: Zero Lambda Boundary**
  - **Inputs**: `--lambdaA 0.0 --lambdaB 0.0 --rho 0.0`
  - **Expected Outcome**: P(0:0) = 1.0, all other score probabilities = 0.0.
  - **Rationale**: Asserts that 0 lambda results in a deterministic 0-0 match without crash.
* **TC-T2-F1-02: Extreme Positive Dixon-Coles Correlation**
  - **Inputs**: `--lambdaA 1.0 --lambdaB 1.0 --rho 2.5`
  - **Expected Outcome**: The correlation adjustment clamps negative adjustment factors to 0, preventing negative probabilities.
  - **Rationale**: Tests bounds handling when rho is mathematically too large.
* **TC-T2-F1-03: Negative Lambda Error Handling**
  - **Inputs**: `--lambdaA -1.0 --lambdaB 1.5`
  - **Expected Outcome**: Non-zero exit code, stderr contains validation message: "lambda must be non-negative".
  - **Rationale**: Tests engine's boundary validation on invalid inputs.
* **TC-T2-F1-04: Negative Binomial High Overdispersion Boundary**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --dispersionA 0.01 --dispersionB 0.01 --model negbin`
  - **Expected Outcome**: Normal calculation completion. Does not crash due to zero or negative denominator.
  - **Rationale**: Prevents numerical stability errors when dispersion parameter is near zero.
* **TC-T2-F1-05: Grid Truncation Boundary**
  - **Inputs**: `--lambdaA 10.0 --lambdaB 10.0 --max_goals 12`
  - **Expected Outcome**: Grid sum is normalized back to 1.0 even if a significant part of the distribution lies outside the grid.
  - **Rationale**: Verifies model normalization prevents probability loss under high ratings.

#### Feature 2: Contextual WM-Specific Factors (F2 - Boundary/Corner)
* **TC-T2-F2-01: Extreme Altitude (La Paz, 3600m)**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --elevation 3600 --acclA 0 --acclB 14`
  - **Expected Outcome**: Team A's lambda is clamped to a minimum performance floor (e.g. 0.2) rather than decreasing to 0 or negative.
  - **Rationale**: Asserts elevation penalty decay curves clamp to a minimum baseline rating.
* **TC-T2-F2-02: Back-to-Back Rest Days (0 Rest Days)**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --restA 0 --restB 4`
  - **Expected Outcome**: Severe travel penalty applies to Team A, but rating does not fall below 0.
  - **Rationale**: Tests extreme fatigue modeling boundary.
* **TC-T2-F2-03: Climate Extreme Temperature (50°C)**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --temp 50.0 --humidity 90.0`
  - **Expected Outcome**: Both teams' ratings are severely reduced but remain positive.
  - **Rationale**: Tests extreme desert climate bounds.
* **TC-T2-F2-04: Absolute Fan Monopolization (100% vs 0%)**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --host A --fanA 100 --fanB 0`
  - **Expected Outcome**: Performance boost for Team A matches theoretical maximum. No division by zero.
  - **Rationale**: Validates bounds of the fan support formula.
* **TC-T2-F2-05: Long-term Acclimation Saturation**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --elevation 2000 --acclA 300`
  - **Expected Outcome**: Team A's adjusted lambda is equal to base rating (2.0), showing no excess boost above base rating.
  - **Rationale**: Tests that acclimation only removes altitude penalty, and does not serve as an infinite positive multiplier.

#### Feature 3: Kicktipp Solver (F3 - Boundary/Corner)
* **TC-T2-F3-01: Zero Max Tip Boundary**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --max_tip 0`
  - **Expected Outcome**: Solver returns exactly 1 tip option: `(0, 0)` with its expected points.
  - **Rationale**: Ensures max tip restriction limits the solver grid correctly.
* **TC-T2-F3-02: Uniform Grid Probabilities**
  - **Inputs**: Custom uniform probability distribution (via mocked model or flat grid test mode)
  - **Expected Outcome**: Solver identifies the tip maximizing mathematical scoring.
  - **Rationale**: Ensures the EV formula works correctly under uniform random distributions.
* **TC-T2-F3-03: Tied Expected Values Resolution**
  - **Inputs**: Symmetric lambdas: `--lambdaA 1.0 --lambdaB 1.0 --rho 0.0`
  - **Expected Outcome**: Ties are broken deterministically (e.g. 1:1 has higher EV than 0:0, or lower scores are selected).
  - **Rationale**: Asserts that solver returns a stable, reproducible single optimal tip even during symmetric ties.
* **TC-T2-F3-04: Extremely Small Grid Size (`max_goals = 1`)**
  - **Inputs**: `--lambdaA 1.0 --lambdaB 1.0 --max_goals 1` (internal probability grid only $2 \times 2$)
  - **Expected Outcome**: Solver correctly calculates EV over this tiny grid without IndexError.
  - **Rationale**: Tests internal array size bounds in solver.
* **TC-T2-F3-05: Large Tip Grid Bounds (`max_tip = 15`)**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --max_tip 15`
  - **Expected Outcome**: Execution completes within 100ms.
  - **Rationale**: Validates performance scaling and constraints on solver tip grid iterations.

#### Feature 4: Backtesting and Validation (F4 - Boundary/Corner)
* **TC-T2-F4-01: Empty Dataset Handling**
  - **Inputs**: `python3 backtest.py --dataset data/empty.csv`
  - **Expected Outcome**: Non-zero exit code, error message: "Dataset is empty".
  - **Rationale**: Prevents crashes and division-by-zero errors when data is missing.
* **TC-T2-F4-02: Single-Match Dataset Validation**
  - **Inputs**: `python3 backtest.py --dataset data/single_match.csv`
  - **Expected Outcome**: Correct output and points calculation for the single match.
  - **Rationale**: Tests dataset lower limit execution.
* **TC-T2-F4-03: Malformed CSV Columns**
  - **Inputs**: `python3 backtest.py --dataset data/malformed.csv` (missing ratings or match outcomes)
  - **Expected Outcome**: Program exits cleanly with error: "Missing required column: [column_name]".
  - **Rationale**: Validates parser resilience and error handling.
* **TC-T2-F4-04: Identical Model Configuration**
  - **Inputs**: `python3 backtest.py --baseline poisson --optimized poisson --dataset data/wc2022_test.csv`
  - **Expected Outcome**: Report shows identical points for both baseline and optimized models.
  - **Rationale**: Ensures the comparison logic is exact.
* **TC-T2-F4-05: All-Draws Historical Data Evaluation**
  - **Inputs**: `python3 backtest.py --dataset data/all_draws.csv`
  - **Expected Outcome**: Handles data correctly. Models that adjust draw probability higher (e.g. Dixon-Coles) outperform standard Poisson.
  - **Rationale**: Verifies model performance comparison sensitivity under specific scenario distributions.

---

### Tier 3: Cross-Feature Combinations (4 cases)

* **TC-T3-01: Dixon-Coles Bivariate Poisson + Severe Climatic and Host Advantage**
  - **Inputs**: `--lambdaA 2.0 --lambdaB 2.0 --model poisson --rho 0.1 --temp 35.0 --humidity 80.0 --host A --fanA 80 --fanB 20`
  - **Expected Outcome**: Team A's adjusted lambda is boosted by host advantage but reduced by climate penalty. Dixon-Coles correlation is applied to the final calculated lambdas. Grid normalizes to 1.0.
  - **Rationale**: Tests combination of F1 (Dixon-Coles adjustment) and F2 (host status and climatic factors) combined.
* **TC-T3-02: Negative Binomial Model + Extreme Travel Fatigue + Kicktipp Solver**
  - **Inputs**: `--lambdaA 2.5 --lambdaB 2.5 --model negbin --dispersionA 1.5 --dispersionB 1.5 --distA 5000 --tzA 8 --restA 3`
  - **Expected Outcome**: Team A's rating is penalized. The engine computes Negative Binomial probabilities using the penalized rating and dispersion. The Kicktipp solver evaluates this overdispersed grid and outputs optimal tip.
  - **Rationale**: Verifies interaction of F1 (NB distribution), F2 (travel fatigue), and F3 (solver).
* **TC-T3-03: Complete Prediction Engine to Solver E2E Pipeline**
  - **Inputs**: `--lambdaA 1.8 --lambdaB 1.5 --model poisson --rho -0.05 --elevation 2240 --acclA 14 --temp 28 --humidity 60 --distB 3000 --tzB 4 --restB 4 --host A --fanA 70 --fanB 30`
  - **Expected Outcome**: Full configuration completes. Home team gets host advantage and altitude acclimation (no penalty), visiting team gets travel penalty. Dixon-Coles is applied. Solver returns correct sorted tips list.
  - **Rationale**: Tests complete integration of all prediction modifiers and solver calculations.
* **TC-T3-04: Backtesting Suite with Complex Contextual Dataset**
  - **Inputs**: `python3 backtest.py --dataset data/wc2022_context.csv --optimized complex_context`
  - **Expected Outcome**: Backtester parses match-specific contextual columns (elevation, rest days, travel, fan support) for each row, computes context-adjusted predictions, executes the solver, and returns summary stats.
  - **Rationale**: Ensures backtester can interface with the full multi-parameter predictor model.

---

### Tier 4: Real-World Application Scenarios (5 scenarios)

* **TC-T4-01: Mexico City Altitude Match (Mexico vs. USA)**
  - **Scenario**: Match at Estadio Azteca, Mexico City (2240m elevation).
  - **Inputs**:
    - Team A (Mexico, Host): base lambda 1.6, elevation 2240, acclA 14, host A, fanA 85
    - Team B (USA, Visitor): base lambda 1.5, elevation 2240, acclB 3, distB 1500, tzB 1, restB 5
  - **Expected Outcome**: Mexico's lambda is boosted (~1.8-1.9) due to host status and acclimation. USA's lambda is penalized (~1.2-1.3) due to poor acclimation and travel fatigue. Solver tips a home win (e.g. 2:0 or 2:1).
  - **Rationale**: Simulates historical altitude advantage in Mexico City.
* **TC-T4-02: Miami Humid Heat Match (Ecuador vs. England)**
  - **Scenario**: Mid-day match in Miami (34°C, 85% humidity).
  - **Inputs**:
    - Team A (Ecuador): base lambda 1.3 (high heat tolerance, minimal travel/rest penalty)
    - Team B (England): base lambda 2.1, temp 34, humidity 85, distB 4500, tzB 5, restB 4
  - **Expected Outcome**: England suffers significant performance degradation, closing the gap. Solver outputs a narrow England win or draw (e.g. 1:1 or 2:1 England).
  - **Rationale**: Simulates impact of extreme heat on European teams playing in tropical climates.
* **TC-T4-03: Travel-Weary Favorite (Germany vs. Canada in Vancouver)**
  - **Scenario**: Germany travels across the Atlantic to face Canada in Vancouver.
  - **Inputs**:
    - Team A (Canada, Host): base lambda 1.1, host A, fanA 65, distA 0, restA 6
    - Team B (Germany): base lambda 2.2, distB 5200, tzB 9, restB 3
  - **Expected Outcome**: Germany's travel fatigue penalty scales down their offensive output. Canada gets host boost. Solver tips a close draw (e.g. 1:1).
  - **Rationale**: Recreates the classic timezone fatigue offset against host nation support.
* **TC-T4-04: High-Scoring Knockout (Brazil vs. France)**
  - **Scenario**: High-scoring teams face off in comfortable indoor climate (Dallas, 21°C).
  - **Inputs**:
    - Team A (Brazil): base lambda 2.4, dispersionA 1.6, model negbin
    - Team B (France): base lambda 2.2, dispersionB 1.5, model negbin
  - **Expected Outcome**: Solver identifies optimal tip as high-scoring (e.g. 2:2 or 3:2) due to overdispersion probability mass in the tail of the distribution.
  - **Rationale**: Tests model behavior when predicting matches between offensive powerhouses.
* **TC-T4-05: Defensively Tight Knockout (Argentina vs. Italy)**
  - **Scenario**: Neutral venue, low-scoring expectations.
  - **Inputs**:
    - Team A (Argentina): base lambda 1.3, model poisson, rho 0.18
    - Team B (Italy): base lambda 1.0, model poisson, rho 0.18
  - **Expected Outcome**: Increased probability of draw. Optimal tip is 1:1 draw.
  - **Rationale**: Simulates defensive strategies in knockout rounds modeled with positive Dixon-Coles correlation.

```
---

## 3. Required Changes to `PROJECT.md`

To record the start of Milestone 1 and align project management tracking, the following diff must be applied to `PROJECT.md`:

```diff
<<<<
| 1 | E2E Testing Track | Design and build the E2E test suite (Tiers 1-4) | None | PLANNED |
====
| 1 | E2E Testing Track | Design and build the E2E test suite (Tiers 1-4) | None | IN_PROGRESS (Conv: 4606a3e4-1e6e-445b-8297-9307c4ee54d6) |
>>>>
```

This updates the milestone status to `IN_PROGRESS` and links it to the conversation ID `4606a3e4-1e6e-445b-8297-9307c4ee54d6` as requested.
