#!/usr/bin/env python3
"""
Build non-penalty xG (npxG) datasets for WC2018 + WC2022 from StatsBomb open data
(https://github.com/statsbomb/open-data, free / non-commercial license).

npxG per team per match = Σ shot.statsbomb_xg over shots that are NOT penalties and NOT
in the shootout period (period 5). Penalties (~0.76 xG each) are a separate process and
shootout goals never count toward the match scoreline, so both are excluded — this is the
"cleaned by penalties" open-play-quality signal.

Output: data/wc2018_xg.csv, data/wc2022_xg.csv
  columns: phase, team_a, team_b, goals_a, goals_b, npxg_a, npxg_b   (a=home, b=away)
"""
import json
import sys
import csv
import urllib.request

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
SEASONS = {2018: 3, 2022: 106}
STAGE = {
    "Group Stage": "GROUP", "Round of 16": "R16", "Quarter-finals": "QF",
    "Semi-finals": "SF", "3rd Place Final": "THIRD", "Final": "FINAL",
}
NAME_FIX = {"United States": "USA"}   # align with PRE_WM20XX_ELO keys


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def npxg_for_match(match_id):
    """Return {team_name: non-penalty xG} for a match."""
    events = fetch_json(f"{BASE}/events/{match_id}.json")
    out = {}
    for e in events:
        if e.get("type", {}).get("name") != "Shot":
            continue
        if e.get("period") == 5:                       # penalty shootout
            continue
        shot = e.get("shot", {})
        if shot.get("type", {}).get("name") == "Penalty":
            continue
        xg = shot.get("statsbomb_xg")
        if xg is None:
            continue
        team = e["team"]["name"]
        out[team] = out.get(team, 0.0) + float(xg)
    return out


def build(year):
    season = SEASONS[year]
    matches = fetch_json(f"{BASE}/matches/43/{season}.json")
    rows = []
    for i, m in enumerate(sorted(matches, key=lambda x: x["match_id"]), 1):
        home = NAME_FIX.get(m["home_team"]["home_team_name"], m["home_team"]["home_team_name"])
        away = NAME_FIX.get(m["away_team"]["away_team_name"], m["away_team"]["away_team_name"])
        phase = STAGE[m["competition_stage"]["name"]]
        npxg = npxg_for_match(m["match_id"])
        # map npxg keys (raw StatsBomb names) onto home/away
        raw_home = m["home_team"]["home_team_name"]
        raw_away = m["away_team"]["away_team_name"]
        rows.append({
            "phase": phase, "team_a": home, "team_b": away,
            "goals_a": m["home_score"], "goals_b": m["away_score"],
            "npxg_a": round(npxg.get(raw_home, 0.0), 3),
            "npxg_b": round(npxg.get(raw_away, 0.0), 3),
        })
        if i % 16 == 0:
            print(f"  {year}: {i}/{len(matches)} matches", file=sys.stderr)
    path = f"data/wc{year}_xg.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["phase", "team_a", "team_b", "goals_a", "goals_b", "npxg_a", "npxg_b"])
        w.writeheader()
        w.writerows(rows)
    print(f"✓ wrote {path}  ({len(rows)} matches)", file=sys.stderr)
    return rows


if __name__ == "__main__":
    for y in (2018, 2022):
        build(y)
