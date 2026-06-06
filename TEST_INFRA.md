# E2E Testing Infrastructure

This document outlines the end-to-end (E2E) testing framework for the FIFA World Cup 2026 Prediction Engine.

## Testing Philosophy
- **Opaque-Box Verification**: Test execution utilizes the public CLI interfaces and high-level module APIs.
- **Zero External Dependencies**: All tests run using Python's standard `unittest` library.
- **Strict Tiered Validation**:
  - **Tier 1**: Feature Coverage (20 test cases checking core logic).
  - **Tier 2**: Boundary & Corner Cases (20 test cases verifying limits, nulls, and extreme values).
  - **Tier 3**: Cross-Feature Combinations (4 test cases validating component interaction).
  - **Tier 4**: Real-World Scenarios (5 scenarios simulating specific matches).

## Directory Structure
```text
tests/
├── run_e2e.py                     # E2E Test Suite Orchestrator
├── test_tier1_feature_coverage.py  # Feature-specific tests
├── test_tier2_boundary_corner.py  # Extreme inputs, limit tests
├── test_tier3_cross_feature.py     # Component integrations
└── test_tier4_real_world.py        # Real-world simulations
```

## Running the E2E Test Suite
To run all tests across all tiers, run:
```bash
python3 tests/run_e2e.py
```

To run a specific test tier (e.g. Tier 1):
```bash
python3 -m unittest tests/test_tier1_feature_coverage.py
```
