#!/usr/bin/env python3
"""Local T-45 prematch-alert runner — replaces the (disabled) GitHub Actions cron.

Polls `scripts/prematch_alert.py --auto` every POLL_SECONDS. The alert script
itself decides which fixtures are inside the T-45 window and dedups via
data/prematch_state.json, so this runner is a dumb 5-minute heartbeat.

CallMeBot creds (CALLMEBOT_RECIPIENTS / _PHONE / _APIKEY) must be in the
environment — launch with `source ~/.zshrc` first, e.g.:

    source ~/.zshrc
    nohup python3 scripts/prematch_local_runner.py >> data/logs/prematch_local.log 2>&1 &

Stop with:  pkill -f prematch_local_runner
Logs:       data/logs/prematch_local.log
"""
import os
import sys
import time
import datetime
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
POLL_SECONDS = 300

if __name__ == "__main__":
    while True:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        print(f"== tick {ts} ==", flush=True)
        try:
            subprocess.run([sys.executable, "scripts/prematch_alert.py", "--auto"],
                           check=False)
        except Exception as e:  # never let one bad tick kill the heartbeat
            print(f"runner error (alert): {e}", flush=True)
        # Post-alert sweep: auto-record finished results into live_state +
        # flag injuries/news for in-session review (scripts/results_sweep.py).
        try:
            subprocess.run([sys.executable, "scripts/results_sweep.py"], check=False)
        except Exception as e:
            print(f"runner error (sweep): {e}", flush=True)
        time.sleep(POLL_SECONDS)
