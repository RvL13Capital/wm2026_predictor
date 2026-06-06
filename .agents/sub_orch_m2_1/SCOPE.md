# Scope: Milestone 2 — Advanced Probability Engine & Contextual Factors

## Architecture
- `predictor.py` will contain:
  - Bivariate Poisson with Dixon-Coles correlation adjustments.
  - Negative Binomial distribution to handle overdispersion.
  - Contextual factors correction curves for:
    - Altitude acclimation curves (using stadium elevations).
    - Climatic conditions (heat and humidity index).
    - Travel and rest days (mileage and timezone transitions).
    - Fan support / Host advantages.
- The entry points and interfaces must remain backwards-compatible or extend standard models correctly.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Setup & Update | Update PROJECT.md, start heartbeat, and verify current predictor.py | None | DONE |
| 2 | Design & Exploration | Explore Dixon-Coles details, Negative Binomial, and mathematical correction formulas | None | DONE |
| 3 | Core Implementation | Implement probability distributions and contextual curves in predictor.py | M2.2 | IN_PROGRESS |
| 4 | Verification & Test | Write unit tests for all distributions and correction curves, ensuring 100% correctness | M2.3 | PLANNED |
| 5 | Forensic Audit | Perform integrity check using Forensic Auditor | M2.4 | PLANNED |

## Interface Contracts
- `predictor.py` provides probability modeling (Poisson, Dixon-Coles, Negative Binomial, and contextual factors).
- Expected inputs:
  - Base team ratings (or base lambda values).
  - Contextual parameters: team A/B travel, team A/B elevation, temperature/humidity, rest days, etc.
- Expected outputs:
  - Probability grid for outcomes (score matrix).
  - Outcome probabilities (Home win, Draw, Away win).
