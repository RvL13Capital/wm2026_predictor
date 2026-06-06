## 2026-06-03T18:10:13Z
You are a teamwork_preview_worker.
Your working directory is /Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/worker_m4_impl.

Your tasks are:
1. Create a `data` directory under project root `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor` and write the World Cup 2022 dataset to `data/wc2022.csv`.
Here is the CSV content to write:
team_a,team_b,goals_a,goals_b,elevation,temp,humidity,status_a,status_b,fan_pct_a,fan_pct_b,rest_days_a,rest_days_b,travel_miles_a,travel_miles_b,tz_crossed_a,tz_crossed_b,direction_a,direction_b,accl_days_a,accl_days_b,heat_accl_days_a,heat_accl_days_b,alpha_a,alpha_b,rho
Germany,Japan,1,2,0.0,22.0,50.0,Neutral,Neutral,0.5,0.5,3.0,6.0,4000.0,0.0,6,0,East,None,0.0,0.0,0.0,0.0,0.05,0.05,-0.05
Croatia,Morocco,0,0,0.0,22.0,50.0,Neutral,Neutral,0.2,0.8,5.0,5.0,0.0,0.0,0,0,None,None,0.0,0.0,0.0,0.0,0.05,0.05,-0.15
France,Australia,4,1,0.0,22.0,50.0,Neutral,Neutral,0.6,0.4,5.0,5.0,0.0,0.0,0,0,None,None,0.0,0.0,0.0,0.0,0.15,0.05,-0.05
Argentina,Croatia,3,0,0.0,22.0,50.0,Neutral,Neutral,0.8,0.2,4.0,2.5,0.0,0.0,0,0,None,None,0.0,0.0,0.0,0.0,0.05,0.05,-0.05
Morocco,Portugal,1,0,0.0,22.0,50.0,Neutral,Neutral,0.8,0.2,4.0,4.0,0.0,0.0,0,0,None,None,0.0,0.0,0.0,0.0,0.05,0.05,-0.05
England,USA,0,0,0.0,28.0,75.0,Neutral,Neutral,0.5,0.5,4.0,4.0,0.0,0.0,0,0,None,None,0.0,0.0,0.0,0.0,0.05,0.05,-0.10

2. Create `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/backtest.py`.
Implement the following:
- `load_match_data(csv_path: str) -> List[dict]`
- `run_backtest(model_type: str, data: List[dict]) -> dict`
- `generate_summary_report(results_base: dict, results_opt: dict) -> dict`
- Embedded/default fallback for TEAM_STATS containing:
  "Qatar": {"off": 0.8, "def": 1.4}, "Ecuador": {"off": 1.1, "def": 1.0}, "Senegal": {"off": 1.2, "def": 1.1}, "Netherlands": {"off": 1.5, "def": 0.8}, "England": {"off": 1.8, "def": 0.7}, "Iran": {"off": 0.9, "def": 1.2}, "USA": {"off": 1.1, "def": 0.9}, "Wales": {"off": 0.8, "def": 1.3}, "Argentina": {"off": 1.9, "def": 0.7}, "Saudi Arabia": {"off": 0.9, "def": 1.3}, "Mexico": {"off": 1.1, "def": 1.0}, "Poland": {"off": 1.0, "def": 1.1}, "France": {"off": 2.0, "def": 0.8}, "Australia": {"off": 1.0, "def": 1.1}, "Denmark": {"off": 1.2, "def": 0.9}, "Tunisia": {"off": 0.9, "def": 1.0}, "Spain": {"off": 1.7, "def": 0.8}, "Costa Rica": {"off": 0.7, "def": 1.5}, "Germany": {"off": 1.6, "def": 1.0}, "Japan": {"off": 1.3, "def": 1.0}, "Belgium": {"off": 1.3, "def": 1.0}, "Canada": {"off": 1.0, "def": 1.3}, "Morocco": {"off": 1.3, "def": 0.6}, "Croatia": {"off": 1.4, "def": 0.8}, "Brazil": {"off": 2.0, "def": 0.7}, "Serbia": {"off": 1.2, "def": 1.3}, "Switzerland": {"off": 1.2, "def": 1.0}, "Cameroon": {"off": 1.1, "def": 1.2}, "Portugal": {"off": 1.7, "def": 0.9}, "Ghana": {"off": 1.1, "def": 1.4}, "Uruguay": {"off": 1.1, "def": 0.9}, "South Korea": {"off": 1.1, "def": 1.1}
  And fall back to `{"off": 1.2, "def": 1.0}` for other teams.
- Embedded raw fallback matches list containing the 6 matches above, to use when load_match_data fails or no csv path is passed.
- A main CLI runner that runs the comparison on the representative matches, prints a report, and asserts that the optimized model achieves higher simulated Kicktipp points than the baseline model.
- Make sure that load_match_data raises ValueError on empty files, missing required headers ('team_a', 'team_b', 'goals_a', 'goals_b', 'elevation', 'temp', 'humidity'), and malformed values (goals or elevation/temp/humidity having incorrect formats, or team_a == team_b). If elevation, temp, or humidity cells in a row are empty, do not add them to the dictionary (so they get defaulted appropriately via .get()).

MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work.

3. Run the E2E test suite by executing:
   `python3 tests/run_e2e.py`
   Ensure that all 49 test cases pass successfully.

4. Write a handoff.md in your working directory documenting the files created, the test execution command, and the output showing that all 49 tests passed.
