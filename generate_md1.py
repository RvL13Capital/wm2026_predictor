import json
import csv
from stadium_data import STADIUM_DATA
from tournament_bonusfragen import GROUPS

# Map slots to teams
slot_to_team = {}
for group, teams in GROUPS.items():
    for i, team in enumerate(teams):
        slot_to_team[f"{group}{i+1}"] = team

with open('data/fifa_2026_schedule.json', 'r') as f:
    schedule = json.load(f)

# Extract first match for each team to form MD1 (which is the first 24 matches of the schedule)
# Wait, the schedule is roughly chronologically ordered, but we just need MD1.
# Each team plays exactly once in MD1.

md1_matches = []
seen_teams = set()

for match in schedule:
    if match["phase"] != "GROUP":
        continue
    ta = slot_to_team[match["team_a_slot"]]
    tb = slot_to_team[match["team_b_slot"]]
    if ta not in seen_teams and tb not in seen_teams:
        elev = STADIUM_DATA[match["venue"]]["elevation"]
        md1_matches.append({
            "team_a": ta,
            "team_b": tb,
            "phase": "GROUP",
            "elevation": elev,
            "rest_days_a": 7.0,
            "rest_days_b": 7.0,
            "travel_miles_a": 0.0,
            "travel_miles_b": 0.0,
            "tz_crossed_a": 0,
            "tz_crossed_b": 0
        })
        seen_teams.add(ta)
        seen_teams.add(tb)

with open('data/matchday1.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=md1_matches[0].keys())
    writer.writeheader()
    writer.writerows(md1_matches)

print(f"Generated {len(md1_matches)} matches for MD1")
