#!/usr/bin/env python3
"""Post-alert results sweep — auto-record FINISHED matches into live_state.json.

Run by prematch_local_runner.py after each tick (so it lands right after every
WhatsApp alert). Pulls the FIFA calendar (api.fifa.com — same source the alert
uses), finds **First-Stage** matches at full-time whose pairing is not yet in
data/live_state.json, appends [home, away] final scores, validates, and commits
ONLY live_state.json. Idempotent: a silent no-op when nothing is new.

Deliberately conservative — "results auto, news flagged":
  • FIFA MatchStatus: 0 = full-time, 3 = live, 1 = scheduled. Only 0 is recorded.
  • Knockout finals are NOT auto-added (the pool's shootout_total convention,
    gate G1, needs manual care) — they are flagged for manual entry instead.
  • Injuries / news / suspensions are NEVER edited here. Each newly-recorded
    game emits a 🩹 FLAG line (data/logs/sweep.log) naming the teams to review
    in-session. Judgment stays with a human/agent, never the daemon.
"""
import os
import sys
import json
import datetime
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prematch_alert as pa  # reuse engine_name(), _http_json(), CALENDAR_URL, _atomic_write

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, "data", "live_state.json")
SWEEPLOG = os.path.join(ROOT, "data", "logs", "sweep.log")
STATUS_FULLTIME = 0


def _log(msg: str) -> None:
    os.makedirs(os.path.dirname(SWEEPLOG), exist_ok=True)
    line = f"[sweep {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}] {msg}"
    with open(SWEEPLOG, "a") as f:
        f.write(line + "\n")
    print(line, file=sys.stderr)


def _desc(team):
    try:
        return team["TeamName"][0]["Description"]
    except Exception:
        return None


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def sweep(do_commit: bool = True) -> int:
    try:
        raw = pa._http_json(pa.CALENDAR_URL)
    except Exception as e:
        _log(f"FIFA calendar fetch failed ({e}); skip this tick")
        return 0
    try:
        with open(LIVE) as f:
            live = json.load(f)
    except Exception as e:
        _log(f"live_state read failed ({e}); abort")
        return 0

    played = {frozenset(k.split(" vs ")) for k in live}
    added, ko_flags = [], []

    for m in raw.get("Results", []):
        if m.get("MatchStatus") != STATUS_FULLTIME:
            continue
        h, a = m.get("Home"), m.get("Away")
        hs, as_ = (h or {}).get("Score"), (a or {}).get("Score")
        if not isinstance(hs, int) or not isinstance(as_, int):
            continue
        hn, an = pa.engine_name(_desc(h)), pa.engine_name(_desc(a))
        if not hn or not an or frozenset((hn, an)) in played:
            continue
        stage = ""
        if m.get("StageName"):
            stage = m["StageName"][0].get("Description", "")
        if "First Stage" not in stage:  # knockout — shootout_total needs manual care
            ko_flags.append(f"{hn} {hs}-{as_} {an} [{stage}]")
            continue
        live[f"{hn} vs {an}"] = [hs, as_]
        played.add(frozenset((hn, an)))
        added.append(f"{hn} vs {an} = {hs}:{as_}")

    for kf in ko_flags:
        _log(f"⚠ KO final NOT auto-added (enter manually, shootout_total): {kf}")

    if not added:
        return 0

    backup = _dump(json.load(open(LIVE)))
    pa._atomic_write(LIVE, _dump(live))
    v = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate_live_state.py"), LIVE],
                       capture_output=True, text=True)
    if v.returncode != 0:
        pa._atomic_write(LIVE, backup)  # revert — never leave an invalid file
        _log(f"VALIDATION FAILED after {added}; reverted. {(v.stdout + v.stderr).strip()}")
        return 0

    _log("recorded: " + "; ".join(added))
    teams = sorted({t for a in added for t in a.split(" = ")[0].split(" vs ")})
    _log(f"🩹 FLAG injuries/news/suspensions to review in-session: {', '.join(teams)}")

    if do_commit:
        # pathspec-scoped commit: only live_state.json, never other staged work
        r = subprocess.run(["git", "-C", ROOT, "commit", "-m",
                            "ops(sweep): auto-record " + "; ".join(added) + " (FIFA full-time)",
                            "--", "data/live_state.json"],
                           capture_output=True, text=True)
        _log("committed live_state" if r.returncode == 0
             else f"commit skipped: {(r.stdout + r.stderr).strip()[:160]}")
    return len(added)


if __name__ == "__main__":
    sweep(do_commit=("--no-commit" not in sys.argv))
