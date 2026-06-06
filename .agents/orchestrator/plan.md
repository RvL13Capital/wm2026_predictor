# Plan — World Cup 2026 Prediction Engine

## Objective
Build an optimized FIFA World Cup 2026 prediction engine with advanced probability models (Bivariate Poisson / Dixon-Coles), contextual factors (elevation, climate, travel, host support), a Kicktipp solver (4/3/2 points), and a backtesting suite.

## Architecture & Code Layout
- `predictor.py`: Refactored to support advanced models and contextual factors.
- `solver.py` / `kicktipp.py`: The expected value maximization solver.
- `backtest.py`: The backtesting suite using World Cup 2022 data.
- `tests/`: Directory containing unit tests and E2E test cases.
- `data/`: Directory containing stadium metadata and WC 2022 match results.

## Milestones & Decomposition

### Milestone 1: E2E Testing Track Setup
- **Objective**: Design and build the E2E test infrastructure, defining requirements, test runner, and Tiers 1-4 test cases.
- **Deliverables**: `TEST_INFRA.md`, test runner, `TEST_READY.md`.
- **Assigned to**: E2E Testing Track Orchestrator.

### Milestone 2: Advanced Probability Engine & Contextual Factors
- **Objective**: Implement the Bivariate Poisson model with Dixon-Coles adjustments or Negative Binomial model. Add elevation, climate, travel, and host advantage math curves.
- **Deliverables**: Refactored math engine, verified via unit tests.
- **Assigned to**: Implementation Sub-orchestrator (M2).

### Milestone 3: Kicktipp Solver (4/3/2 Scoring)
- **Objective**: Implement a solver to maximize expected points under the 4/3/2 scoring system, properly handling draw rules (wrong draws get tendency points, not difference points).
- **Deliverables**: Kicktipp solver modules and tests.
- **Assigned to**: Implementation Sub-orchestrator (M3).

### Milestone 4: Backtesting Suite
- **Objective**: Implement the historical backtesting framework comparing the optimized model against the baseline Poisson model on World Cup 2022 data.
- **Deliverables**: Backtesting scripts and verification report showing improvement.
- **Assigned to**: Implementation Sub-orchestrator (M4).

### Milestone 5: E2E Integration and Verification
- **Objective**: Run E2E tests across all tiers, fix integration bugs, and run Phase 2 (Adversarial Hardening / Tier 5 coverage).
- **Deliverables**: Full test success, gap report, and clean audit verdict.
- **Assigned to**: Implementation Sub-orchestrator (M5).

## Verification Strategy
- **E2E Testing Track**: Verification of test coverage targets.
- **Implementation Track**: Unit test coverage for math formulas, solver logic, and backtester.
- **Forensic Audit**: Run `teamwork_preview_auditor` to check for hardcoding, facade patterns, or circumventing implementations.
