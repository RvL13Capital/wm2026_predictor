import json
from datetime import datetime
from stadium_data import STADIUM_DATA, haversine_distance, tz_difference

def load_schedule():
    with open('data/fifa_2026_schedule.json', 'r') as f:
        return json.load(f)

def get_group_match_contexts():
    """
    Simulates the group stage sequentially to calculate static context
    (rest_days, travel_miles, tz_crossed) for each group match.
    """
    schedule = load_schedule()
    
    # State tracker
    team_state = {}  # team -> {"date": datetime, "venue": str}
    
    from tournament_bonusfragen import GROUPS
    # Map slots to teams
    slot_to_team = {}
    for group, teams in GROUPS.items():
        for i, team in enumerate(teams):
            slot_to_team[f"{group}{i+1}"] = team
            team_state[team] = None  # No previous match
            
    contexts = {}
    
    for match in schedule:
        if match["phase"] != "GROUP":
            continue
            
        team_a = slot_to_team[match["team_a_slot"]]
        team_b = slot_to_team[match["team_b_slot"]]
        venue = match["venue"]
        m_date = datetime.strptime(match["date"], "%Y-%m-%d")
        
        ctx = {}
        
        for t, prefix in [(team_a, "a"), (team_b, "b")]:
            state = team_state[t]
            if state is None:
                ctx[f"rest_days_{prefix}"] = 7.0  # Assumed full rest for first match
                ctx[f"travel_miles_{prefix}"] = 0.0
                ctx[f"tz_crossed_{prefix}"] = 0.0
            else:
                rest = (m_date - state["date"]).days
                miles = haversine_distance(state["venue"], venue)
                tz = tz_difference(state["venue"], venue)
                
                ctx[f"rest_days_{prefix}"] = float(rest)
                ctx[f"travel_miles_{prefix}"] = miles
                ctx[f"tz_crossed_{prefix}"] = tz
                
            # Update state
            team_state[t] = {"date": m_date, "venue": venue}
            
        contexts[(team_a, team_b)] = ctx
        
    return contexts, team_state
