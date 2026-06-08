#!/usr/bin/env python3
"""
Player-level Golden Boot (Torschützenkönig) prediction.

  expected_player_goals = (player's recent intl goals / team's recent intl goals)
                          × team's EXPECTED TOURNAMENT GOALS

The team term comes from the bonusfragen Monte Carlo (`team_expected_goals`), which already bakes in
both the team's scoring rate AND how deep it runs (more games -> more goals). The player term is each
player's share of his nation's recent goals. The two combine into expected tournament goals per player.

Player goals: martj42 `goalscorers.csv` (Kaggle, not committed — pass its path). HONEST CAVEATS:
  - goal SHARE is a form proxy — `goalscorers.csv` lists who scored, not who played, so there's no
    true per-90 rate; squad continuity is assumed.
  - the **Polymarket Golden Boot market is the sharper signal**; this is a structural estimate.
  - the Golden Boot is inherently high-variance (often a player who simply goes deep and gets hot).

    python3 goalscorer.py [goalscorers.csv] [--sims N] [--since YYYY-MM-DD]
"""
import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tournament_bonusfragen as tbf

# engine team name -> martj42 goalscorers.csv name (only the mismatches)
TEAM_MAP = {
    "USA": "United States", "Czechia": "Czech Republic", "Bosnia": "Bosnia and Herzegovina",
}


def recent_goals(path, since):
    by = collections.defaultdict(collections.Counter)
    pens = collections.defaultdict(collections.Counter)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["date"] < since or r.get("own_goal", "").upper() == "TRUE":
            continue
        by[r["team"]][r["scorer"]] += 1
        if r.get("penalty", "").upper() == "TRUE":
            pens[r["team"]][r["scorer"]] += 1
    return by, pens


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gs = args[0] if args else "/tmp/intl/goalscorers.csv"
    sims = int(sys.argv[sys.argv.index("--sims") + 1]) if "--sims" in sys.argv else 1500
    since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "2023-01-01"
    if not os.path.exists(gs):
        sys.exit(f"need martj42 goalscorers.csv at {gs} — see module docstring")

    print(f"[gs] {sims}-sim tournament MC for team expected goals...", file=sys.stderr)
    teg = tbf.run_monte_carlo(n_sims=sims, verbose=False)["team_expected_goals"]
    by, pens = recent_goals(gs, since)

    teams2026 = [t for g in tbf.GROUPS.values() for t in g]
    rows, no_data = [], []
    for team in teams2026:
        mname = TEAM_MAP.get(team, team)
        scorers = by.get(mname, {})
        team_recent = sum(scorers.values())
        if team_recent == 0 or team not in teg:
            no_data.append(team)
            continue
        for player, goals in scorers.items():
            exp = (goals / team_recent) * teg[team]
            rows.append((exp, player, team, goals, pens[mname].get(player, 0)))
    rows.sort(reverse=True)

    print(f"\nGOLDEN BOOT — top-scorer (player) projection   [recent intl goals since {since}]")
    print(f"{'#':>2}  {'player':<24} {'team':<14} {'xGoals':>7} {'recent':>7} {'pens':>5}")
    print("  " + "-" * 62)
    for i, (exp, player, team, goals, pk) in enumerate(rows[:15], 1):
        print(f"{i:>2}  {player:<24} {team:<14} {exp:>7.2f} {goals:>7} {pk:>5}")
    print(f"\n  >> projected Golden Boot: {rows[0][1]} ({rows[0][2]}) — {rows[0][0]:.2f} expected goals")
    print("  NB: structural estimate. The Polymarket Golden Boot market is the sharper signal; the")
    print("  prop is high-variance. Goal SHARE is a form proxy (no appearance/rate data).")
    if no_data:
        print(f"\n  (no recent scorers matched for: {', '.join(no_data)})", file=sys.stderr)


if __name__ == "__main__":
    main()
