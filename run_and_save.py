import subprocess
import os

project_dir = "/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor"
os.chdir(project_dir)

e2e_res = subprocess.run(["python3", "tests/run_e2e.py"], capture_output=True, text=True)
with open("e2e_out.txt", "w") as f:
    f.write(e2e_res.stdout + e2e_res.stderr)

bt_res = subprocess.run(["python3", "backtest.py"], capture_output=True, text=True)
with open("backtest_out.txt", "w") as f:
    f.write(bt_res.stdout + bt_res.stderr)
