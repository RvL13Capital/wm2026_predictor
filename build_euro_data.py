#!/usr/bin/env python3
"""
Build Euro 2020 + 2024 group-stage RESULTS from StatsBomb open data (comp 55), for the
2026-format MD3 stakes backtest.

Why Euros: the 24-team Euro format (6 groups of 4; top-2 + best-4-of-6 thirds advance) mirrors
2026's best-8-of-12-thirds advancement math far better than the 32-team World Cups (top-2 only)
we already hold. It is the right ground truth for the one question we cannot answer on WC data:
does "3rd place can still advance" change MD3 incentives enough to beat the flat 0.87x trim?

Goals only — one lightweight matches.json per tournament. (npxG would need slow per-match event
pulls and is not needed for the stakes test.) StatsBomb tags only "Group Stage", not the group
letter, so groups are reconstructed from match co-occurrence (union-find).

Output: data/euro2020_results.csv, data/euro2024_results.csv
  columns: group, matchday, team_a, team_b, goals_a, goals_b
"""
import csv
import json
import sys
import urllib.request

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
SEASONS = {2020: 43, 2024: 282}    # competition 55 (UEFA Euro) season ids


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def reconstruct_groups(matches):
    """Union-find: any two teams that played each other share a group. -> {team: 'G#'}."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for m in matches:
        h, a = m["home_team"]["home_team_name"], m["away_team"]["away_team_name"]
        parent[find(h)] = find(a)

    label, order = {}, []
    for m in matches:                                   # label components by first appearance
        for t in (m["home_team"]["home_team_name"], m["away_team"]["away_team_name"]):
            root = find(t)
            if root not in label:
                label[root] = None
                order.append(root)
    for i, root in enumerate(order, 1):
        label[root] = f"G{i}"
    return {t: label[find(t)] for t in parent}


def build(year, season):
    matches = fetch_json(f"{BASE}/matches/55/{season}.json")
    gs = [m for m in matches if m["competition_stage"]["name"] == "Group Stage"]
    groups = reconstruct_groups(gs)
    rows = []
    for m in sorted(gs, key=lambda x: (x.get("match_week") or 0, x.get("match_date") or "")):
        h, a = m["home_team"]["home_team_name"], m["away_team"]["away_team_name"]
        rows.append({
            "group": groups[h], "matchday": m.get("match_week"),
            "team_a": h, "team_b": a,
            "goals_a": m["home_score"], "goals_b": m["away_score"],
        })
    path = f"data/euro{year}_results.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["group", "matchday", "team_a", "team_b", "goals_a", "goals_b"])
        w.writeheader()
        w.writerows(rows)
    print(f"✓ wrote {path}  ({len(rows)} group matches, {len(set(groups.values()))} groups)", file=sys.stderr)
    return rows


if __name__ == "__main__":
    for y, s in SEASONS.items():
        build(y, s)
