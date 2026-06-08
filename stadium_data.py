import math
from typing import Dict, Tuple

# Venue metadata for FIFA World Cup 2026
# Coordinates are (latitude, longitude)
# tz_offset is the UTC offset during June/July (Daylight Saving Time in US/CAN, Standard Time in MEX)

STADIUM_DATA: Dict[str, dict] = {
    "Mexico City":  {"name": "Estadio Azteca",          "lat": 19.3029, "lon": -99.1505, "tz_offset": -6, "elevation": 2240, "retractable_roof": False},
    "Guadalajara":  {"name": "Estadio Akron",           "lat": 20.6817, "lon": -103.4626, "tz_offset": -6, "elevation": 1566, "retractable_roof": False},
    "Monterrey":    {"name": "Estadio BBVA",            "lat": 25.6700, "lon": -100.2444, "tz_offset": -6, "elevation":  540, "retractable_roof": False},
    "New Jersey":   {"name": "MetLife Stadium",         "lat": 40.8128, "lon": -74.0742,  "tz_offset": -4, "elevation":    5, "retractable_roof": False},
    "Dallas":       {"name": "AT&T Stadium",            "lat": 32.7473, "lon": -97.0945,  "tz_offset": -5, "elevation":  131, "retractable_roof": True},
    "Los Angeles":  {"name": "SoFi Stadium",            "lat": 33.9535, "lon": -118.3390, "tz_offset": -7, "elevation":   30, "retractable_roof": False},
    "Miami":        {"name": "Hard Rock Stadium",       "lat": 25.9580, "lon": -80.2389,  "tz_offset": -4, "elevation":    2, "retractable_roof": False},
    "Seattle":      {"name": "Lumen Field",             "lat": 47.5952, "lon": -122.3316, "tz_offset": -7, "elevation":   56, "retractable_roof": False},
    "Boston":       {"name": "Gillette Stadium",        "lat": 42.0909, "lon": -71.2643,  "tz_offset": -4, "elevation":   10, "retractable_roof": False},
    "Houston":      {"name": "NRG Stadium",             "lat": 29.6847, "lon": -95.4107,  "tz_offset": -5, "elevation":   15, "retractable_roof": True},
    "Atlanta":      {"name": "Mercedes-Benz Stadium",   "lat": 33.7554, "lon": -84.4010,  "tz_offset": -4, "elevation":  320, "retractable_roof": True},
    "Philadelphia": {"name": "Lincoln Financial Field", "lat": 39.9008, "lon": -75.1675,  "tz_offset": -4, "elevation":   12, "retractable_roof": False},
    "San Francisco":{"name": "Levi's Stadium",          "lat": 37.4032, "lon": -121.9698, "tz_offset": -7, "elevation":    3, "retractable_roof": False},
    "Kansas City":  {"name": "Arrowhead Stadium",       "lat": 39.0489, "lon": -94.4839,  "tz_offset": -5, "elevation":  247, "retractable_roof": False},
    "Toronto":      {"name": "BMO Field",               "lat": 43.6332, "lon": -79.4186,  "tz_offset": -4, "elevation":   76, "retractable_roof": False},
    "Vancouver":    {"name": "BC Place",                "lat": 49.2767, "lon": -123.1120, "tz_offset": -7, "elevation":    3, "retractable_roof": True},
}

def haversine_distance(city1: str, city2: str) -> float:
    """Calculate the great circle distance in miles between two cities."""
    if city1 not in STADIUM_DATA or city2 not in STADIUM_DATA:
        return 0.0
    
    lat1, lon1 = STADIUM_DATA[city1]["lat"], STADIUM_DATA[city1]["lon"]
    lat2, lon2 = STADIUM_DATA[city2]["lat"], STADIUM_DATA[city2]["lon"]
    
    R = 3958.8  # Earth radius in miles
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def tz_difference(city1: str, city2: str) -> float:
    """Calculate the absolute timezone difference in hours between two cities."""
    if city1 not in STADIUM_DATA or city2 not in STADIUM_DATA:
        return 0.0
        
    return abs(STADIUM_DATA[city1]["tz_offset"] - STADIUM_DATA[city2]["tz_offset"])
