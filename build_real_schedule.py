import json
import os
from datetime import datetime, timedelta

def create_schedule():
    schedule = []
    
    # 2026 World Cup Schedule Rules:
    # 12 Groups (A-L). Each group has 6 matches. Total 72 group matches.
    # June 11: 2 matches (Group A)
    # June 12: 2 matches (Groups B, D)
    # June 13 - June 27: ~4-5 matches daily
    
    # Cluster assignments to match real FIFA venues as closely as possible
    CLUSTERS = {
        "A": ["Mexico City", "Guadalajara", "Monterrey"], # Mexico's group
        "B": ["Vancouver", "Seattle", "San Francisco"],   # Canada's group
        "C": ["Los Angeles", "San Francisco", "Seattle"],
        "D": ["Los Angeles", "Seattle", "San Francisco"], # USA's group
        "E": ["Houston", "Dallas", "Kansas City"],
        "F": ["Dallas", "Monterrey", "Houston"],
        "G": ["Atlanta", "Miami", "Dallas"],
        "H": ["Miami", "Atlanta", "Houston"],
        "I": ["New Jersey", "Philadelphia", "Boston"],
        "J": ["Boston", "New Jersey", "Toronto"],
        "K": ["Toronto", "Philadelphia", "New Jersey"],
        "L": ["Philadelphia", "Boston", "New Jersey"]
    }

    start_date = datetime(2026, 6, 11)
    
    match_id = 1
    
    # We will spread the 3 matchdays for each group to guarantee minimum 4 days rest.
    # MD1: Days 0-5 (Jun 11-16)
    # MD2: Days 5-10 (Jun 16-21)
    # MD3: Days 11-16 (Jun 22-27)
    
    group_start_offsets = {
        "A": 0, "B": 1, "C": 2, "D": 1, "E": 2, "F": 3,
        "G": 3, "H": 4, "I": 4, "J": 5, "K": 5, "L": 6
    }
    
    for md in range(3):
        for group in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]:
            offset = group_start_offsets[group] + (md * 5)
            # Cap the date so group stage ends on Jun 27 (Day 16)
            offset = min(offset, 16)
            date = start_date + timedelta(days=offset)
            
            venues = CLUSTERS[group]
            
            if md == 0:
                pairings = [(1, 2, venues[0]), (3, 4, venues[1])]
            elif md == 1:
                pairings = [(1, 3, venues[1]), (4, 2, venues[0])]
            else:
                pairings = [(4, 1, venues[0]), (2, 3, venues[1])]
                
            for p1, p2, v in pairings:
                schedule.append({
                    "match_id": match_id,
                    "date": date.strftime("%Y-%m-%d"),
                    "time": "15:00" if match_id % 2 == 0 else "20:00",
                    "venue": v,
                    "phase": "GROUP",
                    "team_a_slot": f"{group}{p1}",
                    "team_b_slot": f"{group}{p2}"
                })
                match_id += 1

    # Round of 32 (Days 17-22: Jun 28 - Jul 3)
    R32_VENUES = ["Los Angeles", "Seattle", "Dallas", "Houston", "Atlanta", "Miami", "New Jersey", "Boston",
                  "Mexico City", "Monterrey", "San Francisco", "Vancouver", "Kansas City", "Philadelphia", "Toronto", "New Jersey"]
    for i in range(16):
        date = start_date + timedelta(days=17 + (i // 3))
        schedule.append({
            "match_id": match_id,
            "date": date.strftime("%Y-%m-%d"),
            "time": "18:00",
            "venue": R32_VENUES[i],
            "phase": "R32",
            "slot_a": i * 2,
            "slot_b": i * 2 + 1
        })
        match_id += 1

    # Round of 16 (Days 23-26: Jul 4 - Jul 7)
    R16_VENUES = ["Los Angeles", "Houston", "Dallas", "Seattle", "New Jersey", "Atlanta", "Philadelphia", "Miami"]
    for i in range(8):
        date = start_date + timedelta(days=23 + (i // 2))
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

    # QF (Days 28-30: Jul 9 - Jul 11)
    QF_VENUES = ["Los Angeles", "Kansas City", "Boston", "Miami"]
    for i in range(4):
        date = start_date + timedelta(days=28 + (i // 2))
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

    # SF (Days 33-34: Jul 14 - Jul 15)
    SF_VENUES = ["Dallas", "Atlanta"]
    for i in range(2):
        date = start_date + timedelta(days=33 + i)
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

    # Third Place (Day 37: Jul 18)
    schedule.append({
        "match_id": match_id,
        "date": (start_date + timedelta(days=37)).strftime("%Y-%m-%d"),
        "time": "16:00",
        "venue": "Miami",
        "phase": "THIRD",
        "slot_a": 0,
        "slot_b": 1
    })
    match_id += 1

    # Final (Day 38: Jul 19)
    schedule.append({
        "match_id": match_id,
        "date": (start_date + timedelta(days=38)).strftime("%Y-%m-%d"),
        "time": "15:00",
        "venue": "New Jersey",
        "phase": "FINAL",
        "slot_a": 0,
        "slot_b": 1
    })

    # Sort chronologically by date
    schedule.sort(key=lambda x: x["date"])
    
    # Re-assign match_ids sequentially after sorting
    for idx, match in enumerate(schedule):
        match["match_id"] = idx + 1

    os.makedirs("data", exist_ok=True)
    with open("data/fifa_2026_schedule.json", "w") as f:
        json.dump(schedule, f, indent=2)

    print(f"Generated {len(schedule)} matches in data/fifa_2026_schedule.json")
    
    # Sanity checks
    import collections
    dates = collections.Counter([m["date"] for m in schedule if m["phase"] == "GROUP"])
    print("Group Stage Matches per day:")
    for d, c in sorted(dates.items()):
        print(f"  {d}: {c} matches")

if __name__ == "__main__":
    create_schedule()
