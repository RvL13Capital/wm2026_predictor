import json
import os
from datetime import datetime, timedelta

# Create a deterministic but realistic schedule of 104 matches.
# FIFA actually grouped venues by West, Central, and East to minimize travel.

VENUES_BY_CLUSTER = {
    "A": ["Mexico City", "Guadalajara"],
    "B": ["Vancouver", "Seattle"],
    "C": ["San Francisco", "Los Angeles"],
    "D": ["Los Angeles", "Seattle"],
    "E": ["Monterrey", "Houston"],
    "F": ["Dallas", "Kansas City"],
    "G": ["Atlanta", "Miami"],
    "H": ["Toronto", "Boston"],
    "I": ["Philadelphia", "New Jersey"],
    "J": ["Miami", "New Jersey"],
    "K": ["Mexico City", "Monterrey"],
    "L": ["San Francisco", "Vancouver"],
}

# The World Cup starts on June 11, 2026
START_DATE = datetime(2026, 6, 11)

schedule = []
match_id = 1

# --- GROUP STAGE (72 Matches) ---
# Each group has 6 matches. 
# Matchday 1: 1v2, 3v4
# Matchday 2: 1v3, 4v2
# Matchday 3: 4v1, 2v3

for matchday in range(3):
    day_offset = matchday * 5 # Each matchday spans about 5 days
    
    for group_idx, group_name in enumerate(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]):
        date = START_DATE + timedelta(days=day_offset + (group_idx // 3))
        
        venues = VENUES_BY_CLUSTER[group_name]
        
        if matchday == 0:
            pairings = [(1, 2, venues[0]), (3, 4, venues[1])]
        elif matchday == 1:
            pairings = [(1, 3, venues[1]), (4, 2, venues[0])]
        else:
            pairings = [(4, 1, venues[0]), (2, 3, venues[1])]
            
        for a_seed, b_seed, venue in pairings:
            schedule.append({
                "match_id": match_id,
                "date": date.strftime("%Y-%m-%d"),
                "time": "15:00" if match_id % 2 == 0 else "20:00",
                "venue": venue,
                "phase": "GROUP",
                "team_a_slot": f"{group_name}{a_seed}",
                "team_b_slot": f"{group_name}{b_seed}"
            })
            match_id += 1

# --- ROUND OF 32 (16 Matches) ---
# Days 17-21
R32_VENUES = ["Los Angeles", "Seattle", "Dallas", "Houston", "Atlanta", "Miami", "New Jersey", "Boston",
              "Mexico City", "Monterrey", "San Francisco", "Vancouver", "Kansas City", "Philadelphia", "Toronto", "New Jersey"]

# R32 bracket from tournament_bonusfragen
r32_bracket = [
    ("W_A", "3_M75"), ("R_I", "R_J"), ("W_E", "3_M77"), ("R_F", "R_C"),
    ("W_I", "3_M79"), ("R_D", "R_E"), ("W_C", "3_M81"), ("R_A", "R_B"),
    ("W_L", "3_M82"), ("R_K", "R_H"), ("W_G", "3_M85"), ("R_A", "R_B"), # Note: actual bracket logic handled by sim
    ("W_H", "3_M88"), ("R_B", "R_L"), ("W_D", "3_M75"), ("W_B", "3_M77")
]

for i in range(16):
    date = START_DATE + timedelta(days=17 + (i // 4))
    schedule.append({
        "match_id": match_id,
        "date": date.strftime("%Y-%m-%d"),
        "time": "18:00",
        "venue": R32_VENUES[i],
        "phase": "R32",
        "slot_a": i * 2,       # Use index for sequential pairing in simulator
        "slot_b": i * 2 + 1
    })
    match_id += 1

# --- ROUND OF 16 (8 Matches) ---
# Days 23-26
R16_VENUES = ["Los Angeles", "Houston", "Dallas", "Seattle", "New Jersey", "Atlanta", "Philadelphia", "Miami"]
for i in range(8):
    date = START_DATE + timedelta(days=23 + (i // 2))
    schedule.append({
        "match_id": match_id,
        "date": date.strftime("%Y-%m-%d"),
        "time": "20:00",
        "venue": R16_VENUES[i],
        "phase": "R16",
        "slot_a": i * 2,
        "slot_b": i * 2 + 1
    })
    match_id += 1

# --- QUARTERFINALS (4 Matches) ---
# Days 29-31
QF_VENUES = ["Los Angeles", "Kansas City", "Boston", "Miami"]
for i in range(4):
    date = START_DATE + timedelta(days=29 + (i // 2))
    schedule.append({
        "match_id": match_id,
        "date": date.strftime("%Y-%m-%d"),
        "time": "20:00",
        "venue": QF_VENUES[i],
        "phase": "QF",
        "slot_a": i * 2,
        "slot_b": i * 2 + 1
    })
    match_id += 1

# --- SEMIFINALS (2 Matches) ---
# Days 34-35
SF_VENUES = ["Dallas", "Atlanta"]
for i in range(2):
    date = START_DATE + timedelta(days=34 + i)
    schedule.append({
        "match_id": match_id,
        "date": date.strftime("%Y-%m-%d"),
        "time": "20:00",
        "venue": SF_VENUES[i],
        "phase": "SF",
        "slot_a": i * 2,
        "slot_b": i * 2 + 1
    })
    match_id += 1

# --- THIRD PLACE (1 Match) ---
# Day 38
schedule.append({
    "match_id": match_id,
    "date": (START_DATE + timedelta(days=38)).strftime("%Y-%m-%d"),
    "time": "16:00",
    "venue": "Miami",
    "phase": "THIRD",
    "slot_a": 0,
    "slot_b": 1
})
match_id += 1

# --- FINAL (1 Match) ---
# Day 39
schedule.append({
    "match_id": match_id,
    "date": (START_DATE + timedelta(days=39)).strftime("%Y-%m-%d"),
    "time": "15:00",
    "venue": "New Jersey",
    "phase": "FINAL",
    "slot_a": 0,
    "slot_b": 1
})

os.makedirs("data", exist_ok=True)
with open("data/fifa_2026_schedule.json", "w") as f:
    json.dump(schedule, f, indent=2)

print(f"Generated {len(schedule)} matches in data/fifa_2026_schedule.json")
