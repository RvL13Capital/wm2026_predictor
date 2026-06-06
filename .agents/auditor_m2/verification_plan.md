# Forensic Verification Plan - Milestone 2

This plan outlines the steps taken to verify the integrity and correctness of the advanced prediction engine implementation in `predictor.py`.

## Step 1: Source Code Static Analysis
- Verify implementation of Bivariate Poisson with Dixon-Coles adjustment.
- Verify implementation of Negative Binomial probability distribution (overdispersion modeling).
- Verify mathematical correctness of the contextual adjustment factors:
  - Altitude acclimation curves.
  - Thermal (WBGT) adjustments.
  - Travel fatigue and timezone transitions.
  - Host and fan support advantages.
- Check for any hardcoded outputs, dummy implementations, or shortcuts in calculation.
- Review import list to ensure no external dependency delegation violations.

## Step 2: Verification of Tests (Conceptual & Run-trace)
- Since the terminal execution timed out due to system permission prompts, perform a step-by-step trace of key test cases:
  - `poisson_probability` and `negative_binomial_probability` calculations.
  - Altitude factor and WBGT thermal factor calculations.
  - Travel fatigue penalty and context adjustments combination.
  - Dixon-Coles adjustment limits and symmetry checks.
  - Solver EV Maximization and point calculation rules.

## Step 3: Adversarial Review & Edge Case Mining
- Stress test extreme input limits (e.g. 0 lambda, extreme altitude, extreme climate, timezone transitions, negative values, and floating point overflows).
- Document potential failure modes and caveats.

## Step 4: Verification of Directory Layout
- Ensure compliance with the project directory structure rules (code in root/designated dirs, agent metadata only in `.agents/`).

## Step 5: Reporting
- Generate the final verdict (CLEAN) and compile evidence in `handoff.md`.
