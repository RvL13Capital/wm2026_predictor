# Original User Request

## 2026-06-03T18:06:26Z

You are the M4 Implementation Orchestrator (sub-orchestrator).
Your working directory is `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/sub_orch_m4_1`.
Your parent conversation ID is `e5c19f75-f9be-4875-b90b-029f101863fe`.

Mission:
1. Update `PROJECT.md` at project root: Set Milestone 4 Status to `IN_PROGRESS` and record your conversation ID.
2. Implement Milestone 4: Backtesting Suite (`backtest.py`).
3. Requirements:
   - Create `backtest.py` at the project root.
   - Implement the following functions in `backtest.py`:
     - `load_match_data(csv_path: str) -> List[dict]`: reads historical match data from a CSV file. It must parse columns such as `team_a`, `team_b`, `goals_a`, `goals_b`, `elevation`, `temp`, `humidity`, and potentially others. It must raise `ValueError` on empty CSVs, missing columns, or malformed data.
     - `run_backtest(model_type: str, data: List[dict]) -> dict`: runs the backtest for the specified model: `baseline` (simple Poisson, no contextual adjustments, using solver) or `optimized` (Bivariate Poisson/Negative Binomial + contextual factors + solver). It must return a dictionary with `"total_points"` and `"predictions"` (a list of dictionaries, each with a `"points"` key).
     - `generate_summary_report(results_base: dict, results_opt: dict) -> dict`: compiles a summary dictionary containing `"baseline_total_points"`, `"optimized_total_points"`, `"baseline_avg_points"`, `"optimized_avg_points"`.
   - Provide a main CLI runner in `backtest.py` that:
     - Runs the comparison on a representative set of historical World Cup 2022 matches (e.g. Group stage and Knockouts).
     - Prints a formatted comparative report to stdout.
     - Asserts that the optimized model achieves higher simulated Kicktipp points than the baseline model.
   - Provide a default World Cup 2022 dataset. You can write this data to a file like `data/wc2022.csv` (using the worker) or embed it as a default fallback within `backtest.py`.
4. Enable and execute the E2E test cases under Feature 4 (which were previously skipped). Run `python3 tests/run_e2e.py` and verify that all 49 test cases pass successfully.
5. Update `PROJECT.md` at project root: Set Milestone 4 Status to `DONE`.
6. Write a handoff report in your working directory and notify the parent via send_message.

Orchestration Rules:
- You are a sub-orchestrator. You MUST delegate all implementation and verification steps to subagents (Explorer -> Worker -> Reviewer -> Challenger -> Auditor). Do NOT write code or run commands yourself.
- Ensure the Worker uses genuine implementations (no hardcoding, no facades).
- Run the Forensic Auditor on the final deliverables and ensure a CLEAN verdict.
- Heartbeat cron: start a heartbeat cron and update progress.md.

MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
