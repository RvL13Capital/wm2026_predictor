# Scope: E2E Testing Track

## Architecture
- Opaque-box testing framework under `tests/`.
- Test runner script `tests/run_e2e.py` executing all tiers.
- Configuration and test definitions derived from features F1-F4.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Initialize Track | Update PROJECT.md (Milestone 1 IN_PROGRESS), create TEST_INFRA.md with design | None | PLANNED |
| 2 | Tier 1 & 2 Tests | Implement Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner) test cases | M1 | PLANNED |
| 3 | Tier 3 & 4 Tests | Implement Tier 3 (Cross-Feature) and Tier 4 (Real-World) test cases | M2 | PLANNED |
| 4 | Test Runner & Verification | Implement `tests/run_e2e.py` and verify all tests pass | M3 | PLANNED |
| 5 | Validation & Handoff | Forensic Audit, TEST_READY.md, and update PROJECT.md to DONE | M4 | PLANNED |
