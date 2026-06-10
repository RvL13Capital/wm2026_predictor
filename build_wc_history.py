#!/usr/bin/env python3
"""
Pull historical World Cup RESULTS from openfootball/worldcup.json into the repo's backtest schema
(phase, team_a, team_b, goals_a, goals_b), extending the data back to 2006.

IMPORTANT — this delivers RESULTS ONLY. Running the Elo->lambda *calibration* (recalibrate_lambda.py)
or the regime backtests on these years additionally needs PRE-tournament Elo per team (the
backtest_wm{year}.py modules) — openfootball has no ratings, so that is NOT produced here. The CSVs
are immediately usable for Elo-free distribution checks (goals/game, draw rate); the Elo-dependent
calibration is gated on sourcing 2006/2010 ratings (see the note printed at the end).

Output: data/wc2006_results.csv, data/wc2010_results.csv
"""
import csv
import json
import ssl
import sys
import urllib.request

BASE = "https://raw.githubusercontent.com/openfootball/worldcup.json/master"
YEARS = [2006, 2010]
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def getj(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=_CTX, timeout=30) as r:
        return json.loads(r.read().decode())


def phase_of(m):
    if m.get("group"):
        return "GROUP"
    r = (m.get("round") or "").lower()
    if "16" in r:
        return "R16"
    if "quarter" in r:
        return "QF"
    if "semi" in r:
        return "SF"
    if "third" in r or "3rd" in r:
        return "THIRD"
    if "final" in r:
        return "FINAL"
    return "KO"


def build(year):
    matches = getj(f"{BASE}/{year}/worldcup.json")["matches"]
    rows = []
    for m in matches:
        ft = (m.get("score") or {}).get("ft")
        if not ft or len(ft) < 2:
            continue
        rows.append({"phase": phase_of(m), "team_a": m["team1"], "team_b": m["team2"],
                     "goals_a": ft[0], "goals_b": ft[1]})
    path = f"data/wc{year}_results.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["phase", "team_a", "team_b", "goals_a", "goals_b"])
        w.writeheader()
        w.writerows(rows)
    g = sum(1 for r in rows if r["phase"] == "GROUP")
    print(f"✓ wrote {path}  ({len(rows)} matches, {g} group)", file=sys.stderr)


if __name__ == "__main__":
    for y in YEARS:
        build(y)
    print("\nNOTE: results only. Elo->λ calibration on 2006/2010 needs pre-tournament ratings "
          "(backtest_wm2006/2010.py with PRE_WM20XX_ELO) — not produced here.", file=sys.stderr)
