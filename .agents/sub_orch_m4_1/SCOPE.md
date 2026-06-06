# Scope: Milestone 4 Sub-Orchestration

## Architecture
- `backtest.py` at project root. It will read historical World Cup 2022 matches, run predictions for both `baseline` and `optimized` models, simulate tips maximizing expected value using the Kicktipp solver, compute points, and generate a comparative report.
- `data/wc2022.csv` at project root (or embedded within `backtest.py`) containing WC 2022 matches with team names, actual goals, and environmental/travel contexts.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Set In Progress | Update `PROJECT.md` milestone 4 status to `IN_PROGRESS` | None | PLANNED |
| 2 | Exploration | Explore files, code structure, WC 2022 data requirements | None | PLANNED |
| 3 | Implementation | Implement `backtest.py` and fallback/CSV data | M2 | PLANNED |
| 4 | Verification & E2E | Run E2E tests and verify all pass | M3 | PLANNED |
| 5 | Forensic Audit | Perform integrity forensic audit to ensure CLEAN verdict | M4 | PLANNED |
| 6 | Project Done | Update `PROJECT.md` status to `DONE` and report handoff | M5 | PLANNED |

## Interface Contracts
### `backtest.py` functions:
- `load_match_data(csv_path: str) -> List[dict]`: reads CSV, parses columns (`team_a`, `team_b`, `goals_a`, `goals_b`, `elevation`, `temp`, `humidity`, etc.). Raises `ValueError` on empty CSVs, missing columns, or malformed data. If a match context value (e.g. elevation, temp, humidity) is missing, it should default appropriately or omit them so `get_adjusted_lambdas` defaults them.
- `run_backtest(model_type: str, data: List[dict]) -> dict`: runs backtest for `baseline` (simple Poisson, no contextual adjustments, using solver) or `optimized` (Bivariate Poisson/Negative Binomial + contextual factors + solver). Returns dictionary with `"total_points"` and `"predictions"` (a list of dictionaries, each with a `"points"` key).
- `generate_summary_report(results_base: dict, results_opt: dict) -> dict`: compiles a summary dictionary containing `"baseline_total_points"`, `"optimized_total_points"`, `"baseline_avg_points"`, `"optimized_avg_points"`, and `"delta_total_points"`.
- CLI runner: compares models on World Cup 2022 matches, prints report, and asserts that the optimized model achieves higher points than the baseline.
