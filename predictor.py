# predictor.py — WM 2026 Tipping Engine v4
import sys
import math
import argparse
import csv
import json as json_module
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Union, Optional
from io import StringIO
from utils.math_utils import strip_vig_shin
from stadium_data import STADIUM_DATA
try:
    from squad_data import SQUAD_VALUES
except ImportError:
    SQUAD_VALUES = {}


# ==============================================================================
# 1. STANDALONE SOLVER ENGINE (Inlined from solver.py)
# ==============================================================================

def sign(val: Union[int, float]) -> int:
    """Returns the sign of a value: 1 for positive, -1 for negative, 0 for zero."""
    return 1 if val > 0 else (-1 if val < 0 else 0)

def is_integer_like(val) -> bool:
    """Checks if a value is integer-like (integer, or float representation of an integer)."""
    if isinstance(val, (int, float)):
        return not math.isnan(val) and not math.isinf(val) and float(val).is_integer()
    return False

def flatten_grid(grid) -> List[Tuple[int, int, float]]:
    """Flattens a 2D grid structure (dict of dicts or list of lists) into a flat list of tuples."""
    flat = []
    if isinstance(grid, dict):
        for r, row in grid.items():
            if isinstance(row, dict):
                for c, val in row.items():
                    flat.append((int(r), int(c), val))
            elif isinstance(row, (list, tuple)):
                for c, val in enumerate(row):
                    flat.append((int(r), int(c), val))
    elif isinstance(grid, (list, tuple)):
        for r, row in enumerate(grid):
            if isinstance(row, dict):
                for c, val in row.items():
                    flat.append((int(r), int(c), val))
            elif isinstance(row, (list, tuple)):
                for c, val in enumerate(row):
                    flat.append((int(r), int(c), val))
    return flat

def get_grid_val(grid, r: int, c: int) -> float:
    """Safely retrieves a value from a 2D probability grid, handling out-of-bounds gracefully."""
    try:
        if isinstance(grid, dict):
            row = grid.get(r)
        elif isinstance(grid, list):
            if r < 0 or r >= len(grid):
                return 0.0
            row = grid[r]
        else:
            return 0.0

        if row is None:
            return 0.0

        if isinstance(row, dict):
            if c not in row:
                return 0.0
            val = row[c]
        elif isinstance(row, list):
            if c < 0 or c >= len(row):
                return 0.0
            val = row[c]
        else:
            return 0.0
            
        if val is None:
            raise TypeError("Grid contains None value")
        return float(val)
    except TypeError as te:
        raise te
    except Exception:
        return 0.0

def get_points(t_a: int, t_b: int, g_a: int, g_b: int, pts_exact=4, pts_diff=3, pts_tend=2) -> int:
    """
    Calculates Kicktipp points according to the scoring rules:
    - pts_exact points: Exact score (t_a == g_a and t_b == g_b)
    - pts_diff points: Correct goal difference and tendency (non-draws only)
    - pts_tend points: Correct tendency or non-exact draw on a draw outcome
    - 0 points: Otherwise
    """
    if not (is_integer_like(t_a) and is_integer_like(t_b) and is_integer_like(g_a) and is_integer_like(g_b)):
        return 0

    t_a = int(t_a)
    t_b = int(t_b)
    g_a = int(g_a)
    g_b = int(g_b)

    if t_a == g_a and t_b == g_b:
        return pts_exact
    
    diff_actual = g_a - g_b
    diff_tip = t_a - t_b
    
    sign_actual = sign(diff_actual)
    sign_tip = sign(diff_tip)
    
    if diff_actual == diff_tip:
        return pts_diff
    elif sign_actual == sign_tip:
        return pts_tend
    else:
        return 0

def solve_optimal_tip_from_grid(
    grid: Union[Dict[int, Dict[int, float]], List[List[float]]], 
    max_tip: int,
    pts_exact: int = 4,
    pts_diff: int = 3,
    pts_tend: int = 2
) -> Tuple[List[Tuple[Tuple[int, int], float]], List[Tuple[Tuple[int, int], float]], Tuple[float, float, float]]:
    """
    Solves for the optimal tip (t_a, t_b) maximizing Expected Value (EV) from a goal probability grid.
    Uses an optimized aggregate search algorithm in O(N^2 + T^2) complexity with custom points.
    """
    try:
        max_tip = int(max_tip)
    except (TypeError, ValueError):
        raise TypeError("max_tip must be an integer")

    flat = flatten_grid(grid)
    
    prob_home = 0.0
    prob_draw = 0.0
    prob_away = 0.0
    diff_probs = {}
    flat_probs = []
    
    for r, c, val in flat:
        if val is None:
            raise TypeError("Grid contains None value")
        
        val = float(val)
        
        if r > c:
            prob_home += val
        elif r == c:
            prob_draw += val
        else:
            prob_away += val
            
        diff = r - c
        diff_probs[diff] = diff_probs.get(diff, 0.0) + val
        flat_probs.append(((r, c), val))
        
    # Sort exact scores by probability descending
    sorted_scores = sorted(flat_probs, key=lambda x: x[1], reverse=True)
    
    # Calculate EV for each tip (t_a, t_b) in 0..max_tip
    expected_points = {}
    for t_a in range(max_tip + 1):
        for t_b in range(max_tip + 1):
            p_t = get_grid_val(grid, t_a, t_b)
            
            d = t_a - t_b
            if d > 0:
                ev = p_t * (pts_exact - pts_diff) + diff_probs.get(d, 0.0) * (pts_diff - pts_tend) + prob_home * pts_tend
            elif d < 0:
                ev = p_t * (pts_exact - pts_diff) + diff_probs.get(d, 0.0) * (pts_diff - pts_tend) + prob_away * pts_tend
            else:
                ev = p_t * (pts_exact - pts_diff) + prob_draw * pts_diff
                
            expected_points[(t_a, t_b)] = ev
            
    sorted_tips = sorted(expected_points.items(), key=lambda x: x[1] if not math.isnan(x[1]) else -float('inf'), reverse=True)
    
    return sorted_tips, sorted_scores, (prob_home, prob_draw, prob_away)



# ==============================================================================
# 2. BUILT-IN ELO DATABASE AND xG BASELINE ESTIMATOR (Milestone 6 Upgrade)
# ==============================================================================

# Approx Elo ratings and FIFA rankings for World Cup 2026 participants
WORLD_CUP_2026_TEAMS = {
    # Elo ratings from eloratings.net, June 2-4, 2026
    # Tier 1: 2000+
    "Spain":        {"elo": 2165, "rank": 1},
    "Argentina":    {"elo": 2113, "rank": 2},
    "France":       {"elo": 2082, "rank": 3},
    "England":      {"elo": 2020, "rank": 4},
    "Portugal":     {"elo": 1984, "rank": 5},
    "Brazil":       {"elo": 1984, "rank": 5},
    # Tier 2: 1900-2000
    "Colombia":     {"elo": 1975, "rank": 7},
    "Netherlands":  {"elo": 1944, "rank": 8},
    "Ecuador":      {"elo": 1935, "rank": 9},
    "Germany":      {"elo": 1925, "rank": 10},
    "Norway":       {"elo": 1917, "rank": 11},
    "Croatia":      {"elo": 1908, "rank": 12},
    "Turkey":       {"elo": 1906, "rank": 13},
    "Japan":        {"elo": 1906, "rank": 13},
    "Switzerland":  {"elo": 1894, "rank": 15},
    "Uruguay":      {"elo": 1892, "rank": 16},
    "Belgium":      {"elo": 1888, "rank": 17},
    # Tier 3: 1800-1900
    "Denmark":      {"elo": 1870, "rank": 18},
    "Senegal":      {"elo": 1867, "rank": 19},
    "Mexico":       {"elo": 1867, "rank": 19},
    "Paraguay":     {"elo": 1832, "rank": 21},
    "Austria":      {"elo": 1830, "rank": 22},
    "Morocco":      {"elo": 1821, "rank": 23},
    "Canada":       {"elo": 1805, "rank": 24},
    # Tier 4: 1700-1800
    "Australia":    {"elo": 1775, "rank": 25},
    "Scotland":     {"elo": 1770, "rank": 26},
    "South Korea":  {"elo": 1756, "rank": 27},
    "Czechia":      {"elo": 1750, "rank": 28},
    "Iran":         {"elo": 1760, "rank": 29},
    "USA":          {"elo": 1733, "rank": 30},
    "Panama":       {"elo": 1733, "rank": 30},
    "Algeria":      {"elo": 1728, "rank": 32},
    "Uzbekistan":   {"elo": 1718, "rank": 33},
    "Sweden":       {"elo": 1714, "rank": 34},
    "Cameroon":     {"elo": 1700, "rank": 35},
    # Tier 5: 1600-1700
    "Jordan":       {"elo": 1685, "rank": 36},
    "Ivory Coast":  {"elo": 1676, "rank": 37},
    "DR Congo":     {"elo": 1655, "rank": 38},
    "Egypt":        {"elo": 1653, "rank": 39},
    "Costa Rica":   {"elo": 1640, "rank": 40},
    "Tunisia":      {"elo": 1633, "rank": 41},
    "Iraq":         {"elo": 1608, "rank": 42},
    "Bosnia":       {"elo": 1591, "rank": 43},
    # Tier 6: <1600
    "New Zealand":  {"elo": 1585, "rank": 44},
    "Cape Verde":   {"elo": 1576, "rank": 45},
    "Saudi Arabia": {"elo": 1566, "rank": 46},
    "Ghana":        {"elo": 1510, "rank": 47},
    "Haiti":        {"elo": 1532, "rank": 48},
    "Jamaica":      {"elo": 1527, "rank": 49},
    "South Africa": {"elo": 1518, "rank": 50},
    "Curaçao":      {"elo": 1433, "rank": 51},
    "Qatar":        {"elo": 1423, "rank": 52},
}

TEAM_PPDA = {
    "Spain": 8.2,
    "Germany": 8.5,
    "Austria": 8.0,
    "Argentina": 9.8,
    "France": 11.2,
    "England": 10.5,
    "Portugal": 10.2,
    "Brazil": 9.5,
    "Colombia": 9.6,
    "Netherlands": 10.8,
    "Ecuador": 10.0,
    "Norway": 11.5,
    "Croatia": 12.0,
    "Turkey": 11.0,
    "Japan": 9.2,
    "Switzerland": 11.8,
    "Uruguay": 9.0,
    "Belgium": 11.4,
    "Denmark": 10.9,
    "Senegal": 12.2,
    "Mexico": 9.5,
    "Paraguay": 10.1,
    "Morocco": 12.5,
    "Canada": 10.3,
    "Australia": 12.8,
    "Scotland": 13.0,
    "South Korea": 10.4,
    "Czechia": 12.1,
    "Iran": 14.5,
    "USA": 9.9,
    "Panama": 13.2,
    "Algeria": 12.9,
    "Uzbekistan": 13.5,
    "Sweden": 11.3,
    "Cameroon": 13.1,
    "Jordan": 14.0,
    "Ivory Coast": 11.6,
    "DR Congo": 13.4,
    "Egypt": 13.8,
    "Costa Rica": 14.2,
    "Tunisia": 14.0,
    "Iraq": 13.9,
    "Bosnia": 12.7,
    "New Zealand": 12.5,
    "Cape Verde": 13.0,
    "Saudi Arabia": 14.8,
    "Ghana": 12.3,
    "Haiti": 14.1,
    "Jamaica": 14.5,
    "South Africa": 11.9,
    "Curaçao": 13.6,
    "Qatar": 15.2,
}

# Normalize German and alternative spellings to English Elo key names
TEAM_NAME_MAPPING = {
    "mexiko": "Mexico",
    "südafrika": "South Africa",
    "suedafrika": "South Africa",
    "südkorea": "South Korea",
    "suedkorea": "South Korea",
    "tschechien": "Czechia",
    "kanada": "Canada",
    "bosnien": "Bosnia",
    "bosnien herzegowina": "Bosnia",
    "bosnien-herzegowina": "Bosnia",
    "usa": "USA",
    "vereinigte staaten": "USA",
    "deutschland": "Germany",
    "schottland": "Scotland",
    "england": "England",
    "kroatien": "Croatia",
    "congo dr": "DR Congo",
    "dr congo": "DR Congo",
    "belgien": "Belgium",
    "ägypten": "Egypt",
    "aegypten": "Egypt",
    "spanien": "Spain",
    "kap verde": "Cape Verde",
    "cabo verde": "Cape Verde",
    "paraguay": "Paraguay",
    "schweiz": "Switzerland",
    "italien": "Italy",
    "marokko": "Morocco",
    "portugal": "Portugal",
    "brasilien": "Brazil",
    "österreich": "Austria",
    "oesterreich": "Austria",
    "dänemark": "Denmark",
    "daenemark": "Denmark",
    "frankreich": "France",
    "argentinien": "Argentina",
    "saudi-arabien": "Saudi Arabia",
    "saudi arabien": "Saudi Arabia",
    "polen": "Poland",
    "türkei": "Turkey",
    "tuerkei": "Turkey",
    "schweden": "Sweden",
    "norwegen": "Norway",
    "niederlande": "Netherlands",
    "holland": "Netherlands",
    "algerien": "Algeria",
    "kamerun": "Cameroon",
    "dr kongo": "DR Congo",
    "kongo dr": "DR Congo",
    "tunesien": "Tunisia",
    "ghana": "Ghana",
    "irak": "Iraq",
    "iran": "Iran",
    "usbekistan": "Uzbekistan",
    "katar": "Qatar",
    "jordanien": "Jordan",
    "neuseeland": "New Zealand",
    "costa rica": "Costa Rica",
    "panama": "Panama",
    "jamaika": "Jamaica",
    "haiti": "Haiti",
    "curacao": "Curaçao",
    "curaçao": "Curaçao",
    "chile": "Chile",
    "ecuador": "Ecuador",
    "wales": "Wales",
    "elfenbeinküste": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "türkiye": "Turkey",
    "turkiye": "Turkey",
    "bosnia-herzegovina": "Bosnia",
    "bosnia and herzegovina": "Bosnia",
    "cape verde": "Cape Verde",
    "kap verde": "Cape Verde",
    "cabo verde": "Cape Verde",
}


# --- AUTO-LOAD DYNAMIC ELO (single source of truth across every script) -------
# Bug fix: make_bracket_html applied data/elo_2026_post_friendlies.json, but matchday_tips
# (the LIVE tip generator) did not — it ran on stale hardcoded ratings (France was off by 18).
# Overlaying at import time guarantees predictor / matchday_tips / bracket all use the same
# freshest Elo. Set WM2026_NO_FRIENDLY_ELO=1 to fall back to the hardcoded pre-friendly dict.
def _load_dynamic_elos():
    import os, json
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "elo_2026_post_friendlies.json")
    if os.path.exists(fpath) and os.environ.get("WM2026_NO_FRIENDLY_ELO") != "1":
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                post = json.load(f)
            for t, d in post.items():
                t_clean = TEAM_NAME_MAPPING.get(t.strip().lower(), t.strip())
                if t_clean in WORLD_CUP_2026_TEAMS:
                    WORLD_CUP_2026_TEAMS[t_clean]["elo"] = float(d["elo"])
        except Exception:
            pass
_load_dynamic_elos()

# ==============================================================================
# PENALTY SHOOTOUT STRENGTH (team-specific conversion rate modifier)
# ==============================================================================
# Based on historical World Cup penalty shootout records (1982-2022)
# Values are multipliers on the base conversion rate (default 0.75)
# >1.0 = historically strong at pens, <1.0 = historically weak
# Source: FIFA records, transfermarkt.de

PENALTY_STRENGTH = {
    # Elite penalty takers (>80% historical conversion in shootouts)
    "Argentina":    1.08,   # 4W-1L in WC shootouts, Messi era
    "Germany":      1.07,   # 4W-1L, historically clinical
    "Brazil":       1.03,   # 2W-1L, mixed record
    "Croatia":      1.10,   # 3W-0L in WC shootouts (2018, 2022 ×2)
    "France":       1.00,   # 2W-2L, average
    "Spain":        0.93,   # 1W-3L, historically shaky
    "England":      0.90,   # 1W-3L, notorious penalty weakness
    "Netherlands":  0.95,   # 1W-2L, inconsistent
    "Portugal":     1.02,   # 1W-0L, small sample
    "Uruguay":      1.00,   # 1W-1L, average
    "Japan":        0.92,   # 0W-2L in WC shootouts
    "South Korea":  0.98,   # 1W-1L
    "USA":          0.97,   # Limited WC shootout history
    "Mexico":       0.94,   # 0W-2L, historically weak
    "Colombia":     0.96,   # Mixed
    "Belgium":      0.98,   # Limited data
    "Morocco":      1.05,   # 2022 performance boosted
    "Switzerland":  0.96,   # 0W-1L
    "Australia":    1.00,   # 1W-0L (2022 vs Peru qualifiers)
    "Serbia":       0.97,   
    "Poland":       0.96,   
    "Denmark":      0.97,   
    "Turkey":       1.00,   
    "Ecuador":      0.98,   
    "Canada":       0.97,   
    "Costa Rica":   1.02,   # 2014 QF win
    "Panama":       0.97,
    "Ghana":        0.95,   # 2010 QF loss
    "Senegal":      0.97,
    "Cameroon":     0.97,
    "Nigeria":      0.97,
    "Algeria":      0.97,
    "Tunisia":      0.97,
    "Iran":         0.97,
    "Saudi Arabia": 0.95,
    "Qatar":        0.95,
    "Ivory Coast":  0.97,
}

import json

DEFAULT_CONSTANTS = {
    "elo_baseline_goals": 1.0,
    "elo_scale_factor": 1600.0,
    "value_beta_xi": 0.15,
    "value_beta_bench": 0.05,
    "elevation_base_loss_linear": 0.08,

    "elevation_base_loss_quadratic": 0.015,
    "elevation_acclimation_decay_rate": 7.0,
    "thermal_wbgt_threshold": 20.0,
    "thermal_base_loss_coefficient": 0.015,
    "thermal_acclimation_decay_rate": 5.0,
    "travel_rest_multiplier": 0.03,
    "travel_rest_exponent": 1.5,
    "travel_dist_multiplier": 0.05,
    "travel_dist_miles_scale": 0.001,
    "travel_dist_rest_decay": 0.30,
    "travel_tz_multiplier": 0.02,
    "travel_tz_east_weight": 1.5,
    "travel_tz_west_weight": 1.0,
    "travel_max_penalty": 0.30,
    "context_att_travel_penalty": 0.70,
    "context_def_travel_penalty": 0.30,
    "context_att_fan_support": 0.05,
    "context_def_fan_support": 0.04,
    "host_att_true_home": 0.08,
    "host_def_true_home": -0.06,
    "host_att_co_host": 0.03,
    "host_def_co_host": -0.02,
    # Match phase auto-adjustments (Milestone 1: Knockout Modeling)
    "ko_rho_multiplier_r32": 1.2,
    "ko_rho_multiplier_r16": 1.4,
    "ko_rho_multiplier_qf": 1.6,
    "ko_rho_multiplier_sf": 2.0,
    "ko_rho_multiplier_final": 2.2,
    "ko_rho_multiplier_third": 1.3,
    # Phase-specific defensive lambda factors
    # Historical WC goals/game: Group ~2.7, R32 ~2.5, R16 ~2.2, QF ~2.0, SF ~1.9, Final ~1.6
    # Factor = phase_avg / group_avg (normalized to baseline Poisson output)
    "ko_defensive_lambda_factor": 0.92,     # Legacy fallback (used if phase not in dict)
    "ko_lambda_factor_r32": 0.94,           # R32: slightly more cautious
    "ko_lambda_factor_r16": 0.90,           # R16: noticeably more defensive
    "ko_lambda_factor_qf":  0.87,           # QF: high stakes, defensive masterclasses
    "ko_lambda_factor_sf":  0.84,           # SF: extreme caution (2022: ARG-CRO 3-0 outlier)
    "ko_lambda_factor_final": 0.80,         # Final: historically the most defensive match
    "ko_lambda_factor_third": 1.02,         # 3rd place: open match, both teams freed from pressure
    # Extra Time model (Layer 2)
    "et_time_fraction": 0.333,       # 30 min / 90 min
    "et_fatigue_factor": 0.85,       # Teams are ~15% less effective due to exhaustion
    "et_rho_dampening": 0.5,         # Dixon-Coles effect is weaker in ET
    "et_depth_asymmetry": 0.0,       # 5-sub squad-depth ET skew (0 = symmetric original; ~0.20 favours stronger side). UNVALIDATED — backtest before enabling.
    # Penalty model (Layer 3)
    "pen_conversion_rate": 0.75,     # Historical average: ~75% of penalties score
    "pen_sudden_death_conversion": 0.72,  # Slightly lower under sudden death pressure
    "pen_max_sudden_death_rounds": 5,     # Max sudden death rounds to simulate
    # Bayesian Precision-Weighted Blending (Milestone 1.3)
    "blend_alpha": 0.1,
    "blend_beta": 0.5,
    "blend_gamma": 0.05,
    "blend_tau_mod": 1.0,
}

CONSTANTS = DEFAULT_CONSTANTS.copy()

def load_config(path: str):
    global CONSTANTS
    try:
        with open(path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
        for k, v in user_config.items():
            if k in CONSTANTS:
                CONSTANTS[k] = float(v)
    except Exception as e:
        print(f"Warnung: Fehler beim Laden der Konfiguration {path}: {e}. Nutze Standardwerte.", file=sys.stderr)

def estimate_base_lambdas_from_elo(team_a: str, team_b: str, elo_a_override: float = None, elo_b_override: float = None) -> Tuple[float, float]:
    """
    Estimates baseline expected goals (lambda) for Team A and Team B based on their Elo ratings.
    - Baseline: elo_baseline_goals (default 1.35) expected goals per team in a neutral matchup.
    - Scaling: elo_scale_factor (default 1600) Elo difference scales expected goal ratio.
    """
    def clean_name(name):
        if not name:
            return ""
        n = name.strip().lower()
        return TEAM_NAME_MAPPING.get(n, name.strip())
        
    team_a_clean = clean_name(team_a)
    team_b_clean = clean_name(team_b)
    
    # Retrieve Elo ratings (default to 1700 if unknown)
    elo_a = elo_a_override if elo_a_override is not None else WORLD_CUP_2026_TEAMS.get(team_a_clean, {}).get("elo", 1700)
    elo_b = elo_b_override if elo_b_override is not None else WORLD_CUP_2026_TEAMS.get(team_b_clean, {}).get("elo", 1700)
    
    diff = float(elo_a - elo_b)
    
    ratio = 10.0 ** (diff / CONSTANTS["elo_scale_factor"])
    
    lambda_A = CONSTANTS["elo_baseline_goals"] * ratio
    lambda_B = CONSTANTS["elo_baseline_goals"] / ratio
    
    return lambda_A, lambda_B


# ==============================================================================
# 2b. MARKET ODDS → POISSON LAMBDA REVERSE SOLVER
# ==============================================================================

def _poisson_1x2_from_lambdas(la: float, lb: float, rho: float = 0.0,
                               max_goals: int = 8) -> Tuple[float, float, float]:
    """
    Compute P(home), P(draw), P(away) from Poisson lambdas.
    Fast standalone version for the optimizer (avoids full grid generation).
    """
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    
    # Precompute Poisson PMFs
    pmf_a = []
    pmf_b = []
    for k in range(max_goals + 1):
        pa = math.exp(-la) * (la ** k) / math.factorial(k)
        pb = math.exp(-lb) * (lb ** k) / math.factorial(k)
        pmf_a.append(pa)
        pmf_b.append(pb)
    
    for a in range(max_goals + 1):
        for b in range(max_goals + 1):
            p = pmf_a[a] * pmf_b[b]
            # Dixon-Coles correction for low scores
            if rho != 0.0 and a <= 1 and b <= 1:
                if a == 0 and b == 0:
                    p *= max(0, 1.0 - rho * la * lb)
                elif a == 0 and b == 1:
                    p *= max(0, 1.0 + rho * la)
                elif a == 1 and b == 0:
                    p *= max(0, 1.0 + rho * lb)
                elif a == 1 and b == 1:
                    p *= max(0, 1.0 - rho)
            
            if a > b:
                p_home += p
            elif a == b:
                p_draw += p
            else:
                p_away += p
    
    return p_home, p_draw, p_away


def odds_to_lambdas(p_home: float, p_draw: float, p_away: float,
                     rho: float = -0.05, max_goals: int = 8) -> Tuple[float, float]:
    """
    Reverse-engineer Poisson λ values from market 1x2 probabilities.
    
    Uses a zero-dependency Nelder-Mead simplex optimizer to find (λ_a, λ_b) 
    that minimize MSE(model_probs - market_probs).
    
    Args:
        p_home: Fair probability of home win (0-1)
        p_draw: Fair probability of draw (0-1)
        p_away: Fair probability of away win (0-1)
        rho: Dixon-Coles correlation (default -0.05)
        max_goals: Grid size for Poisson calculation
    
    Returns:
        (lambda_a, lambda_b) that best match the given probabilities
    """
    # Validate inputs
    total = p_home + p_draw + p_away
    if abs(total - 1.0) > 0.05:
        raise ValueError(f"Probabilities must sum to ~1.0, got {total:.4f}")
    # Normalize
    p_home /= total
    p_draw /= total
    p_away /= total
    
    def objective(la, lb):
        """Forward KL divergence D(market ‖ model): penalises the model for
        starving outcomes the market gives real mass to (underdog/draw tails),
        which plain MSE shrugs off in favour of the big favourite term."""
        if la <= 0.01 or lb <= 0.01 or la > 5.0 or lb > 5.0:
            return 1e10  # Out of bounds
        ph, pd, pa = _poisson_1x2_from_lambdas(la, lb, rho, max_goals)
        tot = ph + pd + pa
        if tot <= 0.0:
            return 1e10
        ph, pd, pa = ph / tot, pd / tot, pa / tot   # model not self-normalised (DC + truncation)
        kl = 0.0
        if p_home > 0.0: kl += p_home * math.log(p_home / max(ph, 1e-12))
        if p_draw > 0.0: kl += p_draw * math.log(p_draw / max(pd, 1e-12))
        if p_away > 0.0: kl += p_away * math.log(p_away / max(pa, 1e-12))
        return kl
    
    # Phase 1: Coarse grid search (step=0.1, range 0.2-4.0)
    best_la, best_lb = 1.3, 1.1
    best_err = objective(best_la, best_lb)
    
    for la_10 in range(2, 41):  # 0.2 to 4.0
        la = la_10 * 0.1
        for lb_10 in range(2, 41):
            lb = lb_10 * 0.1
            err = objective(la, lb)
            if err < best_err:
                best_err = err
                best_la, best_lb = la, lb
    
    # Phase 2: Fine refinement (3 rounds, shrinking step)
    step = 0.05
    for _ in range(3):
        improved = True
        while improved:
            improved = False
            for dla in [-step, 0, step]:
                for dlb in [-step, 0, step]:
                    if dla == 0 and dlb == 0:
                        continue
                    la_try = best_la + dla
                    lb_try = best_lb + dlb
                    err = objective(la_try, lb_try)
                    if err < best_err:
                        best_err = err
                        best_la, best_lb = la_try, lb_try
                        improved = True
        step *= 0.2  # Shrink step each round
    
    return round(best_la, 4), round(best_lb, 4)


def blend_lambdas(elo_la: float, elo_lb: float,
                   market_la: float, market_lb: float,
                   market_weight: float = 0.8,
                   time_to_kickoff: Optional[float] = None,
                   volume: Optional[float] = None) -> Tuple[float, float]:
    """
    Blend Elo-based and market-implied lambdas.
    
    If time_to_kickoff and/or volume are provided, performs a log-space Bayesian blend.
    Otherwise falls back to standard linear blending.
    
    Args:
        elo_la/lb: Lambdas from Elo rating system
        market_la/lb: Lambdas reverse-engineered from market odds
        market_weight: Weight for market lambdas (0.0 = pure Elo, 1.0 = pure market)
        time_to_kickoff: Hours to kickoff (float or None)
        volume: Volume in raw matched currency (float or None)
    
    Returns:
        Blended (lambda_a, lambda_b)
    """
    if time_to_kickoff is not None or volume is not None:
        alpha = CONSTANTS.get("blend_alpha", 0.1)
        beta = CONSTANTS.get("blend_beta", 0.5)
        gamma = CONSTANTS.get("blend_gamma", 0.05)
        tau_mod = CONSTANTS.get("blend_tau_mod", 1.0)
        
        tau_mkt = 0.0
        if volume is not None:
            tau_mkt += alpha * math.log(max(1.0, volume))
        if time_to_kickoff is not None:
            tau_mkt += beta * math.exp(-gamma * time_to_kickoff)
            
        total_tau = tau_mkt + tau_mod
        if total_tau <= 0:
            la = market_la
            lb = market_lb
        else:
            eps = 1e-9
            market_la_safe = max(eps, market_la)
            market_lb_safe = max(eps, market_lb)
            elo_la_safe = max(eps, elo_la)
            elo_lb_safe = max(eps, elo_lb)
            
            ln_la = (tau_mkt * math.log(market_la_safe) + tau_mod * math.log(elo_la_safe)) / total_tau
            ln_lb = (tau_mkt * math.log(market_lb_safe) + tau_mod * math.log(elo_lb_safe)) / total_tau
            la = math.exp(ln_la)
            lb = math.exp(ln_lb)
    else:
        w = max(0.0, min(1.0, market_weight))
        la = w * market_la + (1.0 - w) * elo_la
        lb = w * market_lb + (1.0 - w) * elo_lb
        
    return round(la, 4), round(lb, 4)


def extract_true_probs_power(oh: float, od: float, oa: float) -> Tuple[float, float, float]:
    """
    Strip bookmaker margin via the Power method (Buchdahl): solve for exponent k
    such that (1/oh)^k + (1/od)^k + (1/oa)^k = 1, then renormalise.

    Unlike proportional de-vigging (divide each inverse-odd by their sum), the
    Power method removes proportionally MORE margin from longshots than from
    favourites, countering the favourite-longshot bias books bake into the price.
    Falls back to plain normalisation when the book carries no overround.
    """
    inv = [1.0 / oh, 1.0 / od, 1.0 / oa]
    s = sum(inv)
    if s <= 1.0:                      # no margin to strip — just normalise
        return inv[0] / s, inv[1] / s, inv[2] / s
    lo, hi = 1.0, 2.0                 # widen hi until it brackets the root
    while sum(v ** hi for v in inv) > 1.0 and hi < 64.0:
        hi *= 2.0
    for _ in range(60):               # bisection: sum(inv**k) is monotone decreasing in k
        mid = 0.5 * (lo + hi)
        if sum(v ** mid for v in inv) > 1.0:
            lo = mid
        else:
            hi = mid
    k = 0.5 * (lo + hi)
    p = [v ** k for v in inv]
    tot = sum(p)
    return p[0] / tot, p[1] / tot, p[2] / tot


# ==============================================================================
# 3. STATISTICAL DISTRIBUTIONS
# ==============================================================================


class ModelDistribution(Enum):
    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"


class MatchPhase(Enum):
    """Tournament match phase — affects ρ and defensive scaling automatically."""
    GROUP = "GROUP"
    R32 = "R32"       # Round of 32 (48-team format, 2026+)
    R16 = "R16"
    QUARTER = "QF"
    SEMI = "SF"
    THIRD = "THIRD"
    FINAL = "FINAL"


PHASE_ALIASES = {
    "group": MatchPhase.GROUP, "groups": MatchPhase.GROUP, "gs": MatchPhase.GROUP,
    "r32": MatchPhase.R32, "round32": MatchPhase.R32, "round_of_32": MatchPhase.R32,
    "ro32": MatchPhase.R32, "last32": MatchPhase.R32,
    "r16": MatchPhase.R16, "round16": MatchPhase.R16, "round_of_16": MatchPhase.R16,
    "ro16": MatchPhase.R16, "last16": MatchPhase.R16, "achtelfinale": MatchPhase.R16,
    "qf": MatchPhase.QUARTER, "quarter": MatchPhase.QUARTER, "quarterfinal": MatchPhase.QUARTER,
    "quarterfinals": MatchPhase.QUARTER, "viertelfinale": MatchPhase.QUARTER,
    "sf": MatchPhase.SEMI, "semi": MatchPhase.SEMI, "semifinal": MatchPhase.SEMI,
    "semifinals": MatchPhase.SEMI, "halbfinale": MatchPhase.SEMI,
    "final": MatchPhase.FINAL, "finale": MatchPhase.FINAL, "f": MatchPhase.FINAL,
    "third": MatchPhase.THIRD, "3rd": MatchPhase.THIRD, "third_place": MatchPhase.THIRD,
    "thirdplace": MatchPhase.THIRD, "platz3": MatchPhase.THIRD, "spiel_um_platz_3": MatchPhase.THIRD,
}


def parse_match_phase(s: str) -> Optional[MatchPhase]:
    """Parse a match phase string into a MatchPhase enum value."""
    if s is None:
        return None
    key = str(s).strip().lower().replace("-", "").replace(" ", "_")
    # Direct enum match
    for phase in MatchPhase:
        if key == phase.value.lower():
            return phase
    # Alias match
    return PHASE_ALIASES.get(key, None)


@dataclass(frozen=True)
class MatchModelConfig:
    dist_type: ModelDistribution
    mu_a: float          # Expected goals for Team A
    mu_b: float          # Expected goals for Team B
    alpha_a: float = 0.0 # Dispersion parameter for Team A
    alpha_b: float = 0.0 # Dispersion parameter for Team B
    rho: float = 0.0     # Dixon-Coles adjustment factor
    max_goals: int = 12  # Grid limit for goal calculations
    max_tip: int = 6     # Maximum tip to consider
    pts_exact: int = 4   # Custom Kicktipp exact points
    pts_diff: int = 3    # Custom Kicktipp difference points
    pts_tend: int = 2    # Custom Kicktipp tendency points
    phase: Optional[MatchPhase] = None  # Match phase for auto-adjustments


def poisson_probability(k: int, lam: float) -> float:
    """
    Calculates the Poisson probability P(X = k) using log-gamma to avoid overflow.
    """
    if math.isnan(lam) or math.isinf(lam):
        return 0.0
    if lam <= 0.0:
        return 1.0 if k == 0 else 0.0
    if k < 0:
        return 0.0
    try:
        log_p = k * math.log(lam) - lam - math.lgamma(k + 1)
        if log_p > 700:
            return 0.0
        return math.exp(log_p)
    except (ValueError, OverflowError):
        return 0.0

poisson_prob = poisson_probability

def negative_binomial_probability(k: int, mu: float, alpha: float) -> float:
    """
    Calculates the Negative Binomial probability P(X = k) with mean mu and dispersion alpha.
    Falls back to Poisson if alpha is near zero.
    """
    if k is None or mu is None or alpha is None:
        return 0.0
    try:
        alpha_f = float(alpha)
        mu_f = float(mu)
        k_i = int(k)
    except (ValueError, TypeError):
        return 0.0

    alpha_is_nan = math.isnan(alpha_f)
    alpha_is_inf = math.isinf(alpha_f)
    mu_is_nan = math.isnan(mu_f)
    mu_is_inf = math.isinf(mu_f)

    if mu_is_nan or mu_is_inf:
        return 0.0

    if alpha_is_nan or alpha_is_inf or alpha_f > 1e15:
        return poisson_probability(k_i, mu_f)

    if mu_f > 1e15:
        return poisson_probability(k_i, mu_f)

    if alpha_f * mu_f > 1e15:
        return poisson_probability(k_i, mu_f)

    if k_i < 0:
        return 0.0

    if alpha_f <= 1e-6 or alpha_f * mu_f < 1e-15:
        return poisson_probability(k_i, mu_f)
    if mu_f <= 0.0:
        return 1.0 if k_i == 0 else 0.0
    
    r = 1.0 / alpha_f
    p = 1.0 / (1.0 + alpha_f * mu_f)

    if p <= 0.0 or p >= 1.0:
        return poisson_probability(k_i, mu_f)
    
    try:
        log_p = (
            math.lgamma(k_i + r)
            - math.lgamma(k_i + 1)
            - math.lgamma(r)
            + k_i * math.log(1.0 - p)
            + r * math.log(p)
        )
        if log_p > 700:
            return 0.0
        return math.exp(log_p)
    except (ValueError, OverflowError):
        return poisson_probability(k_i, mu_f)

negative_binomial_prob = negative_binomial_probability
negative_binomial = negative_binomial_probability

def compute_marginal_probability(k: int, mu: float, alpha: float, dist_type: ModelDistribution) -> float:
    if dist_type == ModelDistribution.POISSON:
        return poisson_probability(k, mu)
    elif dist_type == ModelDistribution.NEGATIVE_BINOMIAL:
        return negative_binomial_probability(k, mu, alpha)
    else:
        raise ValueError(f"Unknown distribution type: {dist_type}")

def calculate_altitude_factor(elevation: float, acclimation_days: float) -> float:
    if elevation is None or acclimation_days is None:
        raise TypeError("elevation and acclimation_days must be numeric")
    if isinstance(elevation, str) or isinstance(acclimation_days, str):
        raise TypeError("elevation and acclimation_days must be numeric")
    if not isinstance(elevation, (int, float)) or not isinstance(acclimation_days, (int, float)):
        raise TypeError("elevation and acclimation_days must be numeric")

    if math.isnan(elevation) or math.isinf(elevation):
        elevation = 0.0
    if math.isnan(acclimation_days) or math.isinf(acclimation_days):
        acclimation_days = 0.0
    else:
        acclimation_days = max(0.0, acclimation_days)

    if elevation <= 1000.0:
        return 1.0
    h = (elevation - 1000.0) / 1000.0
    if h > 1000.0:
        h = 1000.0
    base_loss = CONSTANTS["elevation_base_loss_linear"] * h + CONSTANTS["elevation_base_loss_quadratic"] * (h ** 2)
    try:
        exponent = -acclimation_days / CONSTANTS["elevation_acclimation_decay_rate"]
        if exponent > 700:
            remaining_loss = base_loss
        else:
            remaining_loss = base_loss * math.exp(exponent)
    except (OverflowError, ValueError):
        remaining_loss = base_loss
    factor = 1.0 - remaining_loss
    return max(0.5, min(1.0, factor))

def calculate_wbgt(temperature: float, humidity: float) -> float:
    if temperature is None or humidity is None:
        raise TypeError("temperature and humidity must be numeric")
    if isinstance(temperature, str) or isinstance(humidity, str):
        raise TypeError("temperature and humidity must be numeric")
    if not isinstance(temperature, (int, float)) or not isinstance(humidity, (int, float)):
        raise TypeError("temperature and humidity must be numeric")

    if math.isnan(temperature) or math.isinf(temperature):
        temperature = 20.0
    if math.isnan(humidity) or math.isinf(humidity):
        humidity = 50.0

    # Clamp temperature to safe physical range [-50.0, 60.0]
    temperature = max(-50.0, min(60.0, temperature))
    humidity = max(0.0, min(100.0, humidity))

    denom = temperature + 237.3
    if abs(denom) < 1e-9:
        denom = 1e-9 if denom >= 0 else -1e-9
    try:
        exponent = (17.27 * temperature) / denom
        if exponent > 700:
            raise OverflowError
        e = (humidity / 100.0) * 6.1078 * math.exp(exponent)
        wbgt = 0.567 * temperature + 0.393 * e + 3.94
    except (OverflowError, ZeroDivisionError, ValueError):
        wbgt = 0.567 * temperature + 3.94
    return wbgt

def calculate_thermal_factor(temperature: float, humidity: float, heat_acclimation_days: float,
                             is_retractable_roof: bool = False, ppda: float = 11.0) -> float:
    if temperature is None or humidity is None or heat_acclimation_days is None:
        raise TypeError("temperature, humidity, and heat_acclimation_days must be numeric")
    if isinstance(temperature, str) or isinstance(humidity, str) or isinstance(heat_acclimation_days, str):
        raise TypeError("temperature, humidity, and heat_acclimation_days must be numeric")
    if not isinstance(temperature, (int, float)) or not isinstance(humidity, (int, float)) or not isinstance(heat_acclimation_days, (int, float)):
        raise TypeError("temperature, humidity, and heat_acclimation_days must be numeric")

    if math.isnan(heat_acclimation_days) or math.isinf(heat_acclimation_days):
        heat_acclimation_days = 0.0
    else:
        heat_acclimation_days = max(0.0, heat_acclimation_days)

    wbgt = calculate_wbgt(temperature, humidity)
    if is_retractable_roof:
        wbgt = 21.0
        
    if wbgt <= CONSTANTS["thermal_wbgt_threshold"]:
        return 1.0
        
    # PPDA tactical vulnerability multiplier (lower PPDA = more intense pressing = more heat degradation)
    # Baseline PPDA is 11.0. Clamped to [0.5, 2.0] for model robustness.
    vulnerability_multiplier = 11.0 / max(4.0, ppda)
    vulnerability_multiplier = max(0.5, min(2.0, vulnerability_multiplier))
    
    base_loss = CONSTANTS["thermal_base_loss_coefficient"] * (wbgt - CONSTANTS["thermal_wbgt_threshold"]) * vulnerability_multiplier
    try:
        exponent = -heat_acclimation_days / CONSTANTS["thermal_acclimation_decay_rate"]
        if exponent > 700:
            remaining_loss = base_loss
        else:
            remaining_loss = base_loss * math.exp(exponent)
    except (OverflowError, ValueError):
        remaining_loss = base_loss
    factor = 1.0 - remaining_loss
    return max(0.5, min(1.0, factor))


def calculate_travel_penalty(rest_days: float, travel_miles: float, tz_crossed: int, direction: str = "None") -> float:
    if rest_days is None or travel_miles is None or tz_crossed is None:
        raise TypeError("rest_days, travel_miles, and tz_crossed must be numeric")
    if isinstance(rest_days, str) or isinstance(travel_miles, str) or isinstance(tz_crossed, str):
        raise TypeError("rest_days, travel_miles, and tz_crossed must be numeric")
    if not isinstance(rest_days, (int, float)) or not isinstance(travel_miles, (int, float)) or not isinstance(tz_crossed, (int, float)):
        raise TypeError("rest_days, travel_miles, and tz_crossed must be numeric")

    rest_days = max(0.0, rest_days)
    travel_miles = max(0.0, travel_miles)
    tz_crossed = max(0, tz_crossed)
    p_rest = CONSTANTS["travel_rest_multiplier"] * max(0.0, 5.0 - rest_days) ** CONSTANTS["travel_rest_exponent"]
    p_dist = CONSTANTS["travel_dist_multiplier"] * (1.0 - math.exp(-CONSTANTS["travel_dist_miles_scale"] * travel_miles)) * math.exp(-CONSTANTS["travel_dist_rest_decay"] * rest_days)
    
    dir_clean = str(direction).strip().lower()
    if "east" in dir_clean:
        w_dir = CONSTANTS["travel_tz_east_weight"]
    elif "west" in dir_clean:
        w_dir = CONSTANTS["travel_tz_west_weight"]
    else:
        w_dir = 0.0
    cd = tz_crossed * w_dir
    p_tz = CONSTANTS["travel_tz_multiplier"] * max(0.0, cd - rest_days)
    
    return max(0.0, min(CONSTANTS["travel_max_penalty"], p_rest + p_dist + p_tz))


def normalize_status(status_str: str) -> str:
    if status_str is None:
        return "Neutral"
    s = str(status_str).strip().lower().replace('_', ' ').replace('-', ' ')
    if s in ["true home", "home"]:
        return "True Home"
    elif s in ["co host", "cohost"]:
        return "Co-Host"
    else:
        return "Neutral"

def calculate_context_adjustments(
    status: str,
    opponent_status: str,
    fan_support_pct: float,
    opponent_fan_support_pct: float,
    travel_penalty: float,
    opponent_travel_penalty: float,
    c_att_travel: float = None,
    c_def_travel: float = None,
    c_att_fan: float = None,
    c_def_fan: float = None
) -> Tuple[float, float]:
    if fan_support_pct is None or opponent_fan_support_pct is None or travel_penalty is None or opponent_travel_penalty is None:
        raise TypeError("fan support and travel penalty parameters must be numeric")
    if isinstance(fan_support_pct, str) or isinstance(opponent_fan_support_pct, str) or isinstance(travel_penalty, str) or isinstance(opponent_travel_penalty, str):
        raise TypeError("fan support and travel penalty parameters must be numeric")
    if not isinstance(fan_support_pct, (int, float)) or not isinstance(opponent_fan_support_pct, (int, float)) or not isinstance(travel_penalty, (int, float)) or not isinstance(opponent_travel_penalty, (int, float)):
        raise TypeError("fan support and travel penalty parameters must be numeric")

    # Resolve coefficients from CONSTANTS if not explicitly provided
    if c_att_travel is None:
        c_att_travel = CONSTANTS["context_att_travel_penalty"]
    if c_def_travel is None:
        c_def_travel = CONSTANTS["context_def_travel_penalty"]
    if c_att_fan is None:
        c_att_fan = CONSTANTS["context_att_fan_support"]
    if c_def_fan is None:
        c_def_fan = CONSTANTS["context_def_fan_support"]

    if math.isnan(fan_support_pct) or math.isinf(fan_support_pct):
        fan_support_pct = 0.5
    if math.isnan(opponent_fan_support_pct) or math.isinf(opponent_fan_support_pct):
        opponent_fan_support_pct = 0.5

    fan_support_pct = max(0.0, min(1.0, fan_support_pct))
    opponent_fan_support_pct = max(0.0, min(1.0, opponent_fan_support_pct))

    if math.isnan(travel_penalty) or math.isinf(travel_penalty):
        travel_penalty = 0.0
    if math.isnan(opponent_travel_penalty) or math.isinf(opponent_travel_penalty):
        opponent_travel_penalty = 0.0

    delta_att_travel = -c_att_travel * travel_penalty
    delta_def_travel = c_def_travel * travel_penalty
    
    host_att_map = {
        "True Home": CONSTANTS["host_att_true_home"], 
        "Co-Host": CONSTANTS["host_att_co_host"], 
        "Neutral": 0.0
    }
    host_def_map = {
        "True Home": CONSTANTS["host_def_true_home"], 
        "Co-Host": CONSTANTS["host_def_co_host"], 
        "Neutral": 0.0
    }
    
    status_str = normalize_status(status)
    opponent_status_str = normalize_status(opponent_status)
    
    delta_att_host = host_att_map.get(status_str, 0.0)
    delta_def_host = host_def_map.get(status_str, 0.0)
    
    net_fan_margin = fan_support_pct - opponent_fan_support_pct
    delta_att_fan = c_att_fan * net_fan_margin
    delta_def_fan = -c_def_fan * net_fan_margin
    
    delta_att = delta_att_travel + delta_att_host + delta_att_fan
    delta_def = delta_def_travel + delta_def_host + delta_def_fan
    
    delta_att = max(-5.0, min(5.0, delta_att))
    delta_def = max(-5.0, min(5.0, delta_def))
    
    return delta_att, delta_def


def get_adjusted_lambdas(
    lambda_A_base: float,
    lambda_B_base: float,
    teamA_context: dict,
    teamB_context: dict
) -> Tuple[float, float]:
    if lambda_A_base is None or lambda_B_base is None:
        raise TypeError("lambda_A_base and lambda_B_base must be numeric")
    if isinstance(lambda_A_base, str) or isinstance(lambda_B_base, str):
        raise TypeError("lambda_A_base and lambda_B_base must be numeric")
    if not isinstance(lambda_A_base, (int, float)) or not isinstance(lambda_B_base, (int, float)):
        raise TypeError("lambda_A_base and lambda_B_base must be numeric")

    def get_context_val(context, key, default):
        val = context.get(key)
        return val if val is not None else default

    elev_a = get_context_val(teamA_context, "elevation", None)
    elev_b = get_context_val(teamB_context, "elevation", None)
    elev = elev_a if elev_a is not None else (elev_b if elev_b is not None else 0.0)
    
    temp_a = get_context_val(teamA_context, "temp", None)
    temp_b = get_context_val(teamB_context, "temp", None)
    temp = temp_a if temp_a is not None else (temp_b if temp_b is not None else 20.0)
    
    hum_a = get_context_val(teamA_context, "humidity", None)
    hum_b = get_context_val(teamB_context, "humidity", None)
    hum = hum_a if hum_a is not None else (hum_b if hum_b is not None else 0.0)
    
    accl_A = get_context_val(teamA_context, "accl_days", get_context_val(teamA_context, "accl_days_A", 0.0))
    accl_B = get_context_val(teamB_context, "accl_days", get_context_val(teamB_context, "accl_days_B", 0.0))
    
    heat_accl_A = get_context_val(teamA_context, "heat_accl_days", get_context_val(teamA_context, "heat_accl_days_A", 0.0))
    heat_accl_B = get_context_val(teamB_context, "heat_accl_days", get_context_val(teamB_context, "heat_accl_days_B", 0.0))
    
    # Capacity factors
    f_alt_A = calculate_altitude_factor(elev, accl_A)
    f_alt_B = calculate_altitude_factor(elev, accl_B)
    
    venue = get_context_val(teamA_context, "venue", get_context_val(teamB_context, "venue", None))
    is_retractable = False
    if venue in STADIUM_DATA and STADIUM_DATA[venue].get("retractable_roof", False):
        is_retractable = True
        
    ppda_a = get_context_val(teamA_context, "ppda", 11.0)
    ppda_b = get_context_val(teamB_context, "ppda", 11.0)
    
    f_therm_A = calculate_thermal_factor(temp, hum, heat_accl_A, is_retractable_roof=is_retractable, ppda=ppda_a)
    f_therm_B = calculate_thermal_factor(temp, hum, heat_accl_B, is_retractable_roof=is_retractable, ppda=ppda_b)
    
    F_A = f_alt_A * f_therm_A
    F_B = f_alt_B * f_therm_B
    
    delta_att_env_A = 0.5 * math.log(F_A) if F_A > 0.0 else 0.0
    delta_def_env_A = -0.8 * math.log(F_A) if F_A > 0.0 else 0.0
    
    delta_att_env_B = 0.5 * math.log(F_B) if F_B > 0.0 else 0.0
    delta_def_env_B = -0.8 * math.log(F_B) if F_B > 0.0 else 0.0
    
    # Travel penalties
    p_travel_A = calculate_travel_penalty(
        get_context_val(teamA_context, "rest_days", 5.0),
        get_context_val(teamA_context, "travel_miles", 0.0),
        get_context_val(teamA_context, "tz_crossed", 0),
        get_context_val(teamA_context, "direction", "None")
    )
    p_travel_B = calculate_travel_penalty(
        get_context_val(teamB_context, "rest_days", 5.0),
        get_context_val(teamB_context, "travel_miles", 0.0),
        get_context_val(teamB_context, "tz_crossed", 0),
        get_context_val(teamB_context, "direction", "None")
    )
    
    # Context adjustments
    delta_att_ctx_A, delta_def_ctx_A = calculate_context_adjustments(
        status=get_context_val(teamA_context, "status", "Neutral"),
        opponent_status=get_context_val(teamB_context, "status", "Neutral"),
        fan_support_pct=get_context_val(teamA_context, "fan_pct_A", get_context_val(teamA_context, "fan_pct", get_context_val(teamA_context, "fan_support_pct", 0.5))),
        opponent_fan_support_pct=get_context_val(teamB_context, "fan_pct_B", get_context_val(teamB_context, "fan_pct", get_context_val(teamB_context, "fan_support_pct", 0.5))),
        travel_penalty=p_travel_A,
        opponent_travel_penalty=p_travel_B
    )
    
    delta_att_ctx_B, delta_def_ctx_B = calculate_context_adjustments(
        status=get_context_val(teamB_context, "status", "Neutral"),
        opponent_status=get_context_val(teamA_context, "status", "Neutral"),
        fan_support_pct=get_context_val(teamB_context, "fan_pct_B", get_context_val(teamB_context, "fan_pct", get_context_val(teamB_context, "fan_support_pct", 0.5))),
        opponent_fan_support_pct=get_context_val(teamA_context, "fan_pct_A", get_context_val(teamA_context, "fan_pct", get_context_val(teamA_context, "fan_support_pct", 0.5))),
        travel_penalty=p_travel_B,
        opponent_travel_penalty=p_travel_A
    )
    
    # Combine
    delta_att_A = delta_att_env_A + delta_att_ctx_A
    delta_def_A = delta_def_env_A + delta_def_ctx_A
    
    delta_att_B = delta_att_env_B + delta_att_ctx_B
    delta_def_B = delta_def_env_B + delta_def_ctx_B

    # --- Phase 3: Squad Value & Depth Resilience Modifiers ---
    def resolve_team(name):
        if not name:
            return ""
        cleaned_name = name.strip().lower()
        return TEAM_NAME_MAPPING.get(cleaned_name, name.strip())

    team_a_name = get_context_val(teamA_context, "team_name", get_context_val(teamA_context, "team", "Team A"))
    team_b_name = get_context_val(teamB_context, "team_name", get_context_val(teamB_context, "team", "Team B"))

    team_a_res = resolve_team(team_a_name)
    team_b_res = resolve_team(team_b_name)

    val_A = SQUAD_VALUES.get(team_a_res, {"xi": 100.0, "bench": 50.0})
    val_B = SQUAD_VALUES.get(team_b_res, {"xi": 100.0, "bench": 50.0})

    val_A_xi = val_A.get("xi", 100.0)
    val_A_bench = val_A.get("bench", 50.0)
    val_B_xi = val_B.get("xi", 100.0)
    val_B_bench = val_B.get("bench", 50.0)

    # Missing starters and VORP swapping
    missing_value_A = max(0.0, float(get_context_val(teamA_context, "missing_value", 0.0)))
    missing_count_A = max(0, int(get_context_val(teamA_context, "missing_count", 0)))
    missing_value_B = max(0.0, float(get_context_val(teamB_context, "missing_value", 0.0)))
    missing_count_B = max(0, int(get_context_val(teamB_context, "missing_count", 0)))

    # Proxy for replacing injured starters with average bench players
    avg_bench_val_A = val_A_bench / 15.0  
    effective_xi_A = max(1.0, val_A_xi - missing_value_A + (missing_count_A * avg_bench_val_A))
    effective_bench_A = max(1.0, val_A_bench - (missing_count_A * avg_bench_val_A))

    avg_bench_val_B = val_B_bench / 15.0  
    effective_xi_B = max(1.0, val_B_xi - missing_value_B + (missing_count_B * avg_bench_val_B))
    effective_bench_B = max(1.0, val_B_bench - (missing_count_B * avg_bench_val_B))

    # Thermal shock dynamic scaling
    wbgt = calculate_wbgt(temp, hum)
    if is_retractable:
        wbgt = 21.0

    threshold = CONSTANTS.get("thermal_wbgt_threshold", 20.0)
    thermal_shock_multiplier = max(0.0, (wbgt - threshold) * 0.1)

    beta_xi = CONSTANTS.get("value_beta_xi", 0.15)
    beta_bench = CONSTANTS.get("value_beta_bench", 0.05)
    beta_bench_adj = beta_bench * (1.0 + thermal_shock_multiplier)

    # Squad Value Advantage A over B
    adv_val_A = beta_xi * math.log(effective_xi_A / effective_xi_B) + beta_bench_adj * math.log(effective_bench_A / effective_bench_B)

    # Split the advantage symmetrically
    delta_att_val_A = adv_val_A / 2.0
    delta_def_val_A = -adv_val_A / 2.0

    delta_att_A += delta_att_val_A
    delta_def_A += delta_def_val_A

    exponent_A = delta_att_A + delta_def_B
    exponent_B = delta_att_B + delta_def_A

    
    if math.isnan(exponent_A) or math.isinf(exponent_A):
        exponent_A = 0.0
    else:
        exponent_A = max(-1.0, min(1.0, exponent_A))   # safety cap (was ±20): real WC2026 altitude extreme is ~0.59, so ±1 never clips legit physics
        
    if math.isnan(exponent_B) or math.isinf(exponent_B):
        exponent_B = 0.0
    else:
        exponent_B = max(-1.0, min(1.0, exponent_B))   # NB: the proposed ±0.35 WOULD clip Azteca's 0.587 — too tight
        
    if math.isnan(lambda_A_base) or math.isinf(lambda_A_base) or lambda_A_base < 0.0:
        lambda_A_base = 0.0
    if math.isnan(lambda_B_base) or math.isinf(lambda_B_base) or lambda_B_base < 0.0:
        lambda_B_base = 0.0

    try:
        lambda_A_adj = lambda_A_base * math.exp(exponent_A)
    except (OverflowError, ValueError):
        lambda_A_adj = lambda_A_base * 485165195.4097903
        
    try:
        lambda_B_adj = lambda_B_base * math.exp(exponent_B)
    except (OverflowError, ValueError):
        lambda_B_adj = lambda_B_base * 485165195.4097903
        
    lambda_A_adj = max(0.0, min(10000.0, lambda_A_adj))
    lambda_B_adj = max(0.0, min(10000.0, lambda_B_adj))
    
    return lambda_A_adj, lambda_B_adj

# Compatibility wrappers
apply_contextual_factors = get_adjusted_lambdas
def altitude_penalty(elevation: float, acclimation_days: float) -> float:
    return 1.0 - calculate_altitude_factor(elevation, acclimation_days)

def get_dixon_coles_adjustment(x: int, y: int, a_a: float, a_b: float, rho: float) -> float:
    if (math.isnan(rho) or math.isinf(rho) or
        math.isnan(a_a) or math.isinf(a_a) or
        math.isnan(a_b) or math.isinf(a_b)):
        return 1.0

    if rho == 0.0:
        return 1.0

    # Calculate bounds for rho to ensure adjustment factors are non-negative and stable
    upper_limit = 1.0
    if a_a * a_b > 0.0:
        upper_limit = min(1.0, 1.0 / (a_a * a_b))
        
    lower_limit = -1.0
    if a_a > 0.0:
        lower_limit = max(lower_limit, -1.0 / a_a)
    if a_b > 0.0:
        lower_limit = max(lower_limit, -1.0 / a_b)
        
    # Clamp rho
    rho_clamped = max(lower_limit, min(upper_limit, rho))

    if x == 0 and y == 0:
        factor = 1.0 - rho_clamped * a_a * a_b
    elif x == 1 and y == 0:
        factor = 1.0 + rho_clamped * a_b
    elif x == 0 and y == 1:
        factor = 1.0 + rho_clamped * a_a
    elif x == 1 and y == 1:
        factor = 1.0 - rho_clamped
    else:
        factor = 1.0

    if math.isnan(factor) or math.isinf(factor):
        return 1.0

    return max(0.0, factor)

def generate_joint_grid(config: MatchModelConfig) -> Dict[int, Dict[int, float]]:
    grid = {}
    try:
        raw_max_goals = int(config.max_goals)
        if math.isnan(raw_max_goals) or math.isinf(raw_max_goals):
            raw_max_goals = 12
    except (ValueError, TypeError):
        raw_max_goals = 12

    max_goals = max(0, min(100, raw_max_goals))

    p_a = [compute_marginal_probability(x, config.mu_a, config.alpha_a, config.dist_type) for x in range(max_goals + 1)]
    p_b = [compute_marginal_probability(y, config.mu_b, config.alpha_b, config.dist_type) for y in range(max_goals + 1)]
    
    a_a = p_a[1] / p_a[0] if (len(p_a) > 1 and p_a[0] > 0.0) else config.mu_a
    a_b = p_b[1] / p_b[0] if (len(p_b) > 1 and p_b[0] > 0.0) else config.mu_b
    
    for x in range(max_goals + 1):
        grid[x] = {}
        for y in range(max_goals + 1):
            base_prob = p_a[x] * p_b[y]
            adj_factor = get_dixon_coles_adjustment(x, y, a_a, a_b, config.rho)
            grid[x][y] = base_prob * adj_factor
            
    # Normalize the grid to ensure sum == 1.0 over the truncated space
    total_prob = sum(sum(grid[x].values()) for x in grid)
    if total_prob > 0.0:
        for x in grid:
            for y in grid[x]:
                grid[x][y] /= total_prob
    else:
        for x in grid:
            for y in grid[x]:
                grid[x][y] = 0.0
        grid[max_goals][max_goals] = 1.0
                
    return grid


# ==============================================================================
# 3-LAYER KNOCKOUT MODEL (90 min → Extra Time → Penalties)
# ==============================================================================

def penalty_shootout_distribution(p_a: float = 0.75, p_b: float = 0.75,
                                   p_sd_a: float = 0.72, p_sd_b: float = 0.72,
                                   max_sd_rounds: int = 5) -> Dict[Tuple[int, int], float]:
    """
    Computes the probability distribution of (goals_scored_a, goals_scored_b) 
    in a penalty shootout with early termination and sudden death.
    
    Standard format: 5 rounds, alternating kicks (A then B each round).
    Early termination if one team can't mathematically catch up.
    If tied after 5 rounds: sudden death (max_sd_rounds additional rounds).
    
    Returns dict mapping (pen_a, pen_b) -> probability, where pen_a ≠ pen_b always.
    """
    results = {}
    
    # States for 5 standard rounds: list of (goals_a, goals_b, probability)
    states = [(0, 0, 1.0)]
    
    for round_num in range(1, 6):
        remaining_kicks_a = 5 - round_num
        remaining_kicks_b = 5 - round_num
        
        # A shoots
        after_a_states = []
        for ga, gb, p in states:
            for a_scores in [True, False]:
                p_trans = p_a if a_scores else (1.0 - p_a)
                ga_new = ga + (1 if a_scores else 0)
                
                # Check if A's kick ended the shootout
                # B has remaining_kicks_b + 1 kicks left (since B hasn't shot this round)
                if ga_new > gb + (remaining_kicks_b + 1):
                    # A wins immediately
                    key = (ga_new, gb)
                    results[key] = results.get(key, 0.0) + p * p_trans
                elif gb > ga_new + remaining_kicks_a:
                    # B wins immediately
                    key = (ga_new, gb)
                    results[key] = results.get(key, 0.0) + p * p_trans
                else:
                    after_a_states.append((ga_new, gb, p * p_trans))
        
        # B shoots
        after_b_states = []
        for ga, gb, p in after_a_states:
            for b_scores in [True, False]:
                p_trans = p_b if b_scores else (1.0 - p_b)
                gb_new = gb + (1 if b_scores else 0)
                
                # Check if B's kick ended the shootout
                if ga > gb_new + remaining_kicks_b:
                    # A wins immediately
                    key = (ga, gb_new)
                    results[key] = results.get(key, 0.0) + p * p_trans
                elif gb_new > ga + remaining_kicks_a:
                    # B wins immediately
                    key = (ga, gb_new)
                    results[key] = results.get(key, 0.0) + p * p_trans
                else:
                    # If this is round 5 and it's not a tie, someone won
                    if round_num == 5 and ga != gb_new:
                        key = (ga, gb_new)
                        results[key] = results.get(key, 0.0) + p * p_trans
                    else:
                        after_b_states.append((ga, gb_new, p * p_trans))
                        
        states = after_b_states
        
    tied_states = states  # These are the tied-after-5 states
    
    # Sudden death: each team takes 1 kick per round until a winner emerges
    active_sd_states = tied_states
    
    for sd_round in range(1, max_sd_rounds + 1):
        if not active_sd_states:
            break
            
        next_sd_states = []
        for ga, gb, p in active_sd_states:
            # A scores, B misses → A wins
            p_a_wins = p * p_sd_a * (1.0 - p_sd_b)
            if p_a_wins > 0:
                key = (ga + 1, gb)
                results[key] = results.get(key, 0.0) + p_a_wins
                
            # A misses, B scores → B wins
            p_b_wins = p * (1.0 - p_sd_a) * p_sd_b
            if p_b_wins > 0:
                key = (ga, gb + 1)
                results[key] = results.get(key, 0.0) + p_b_wins
                
            # Both score → continue
            p_both_score = p * p_sd_a * p_sd_b
            if p_both_score > 0:
                next_sd_states.append((ga + 1, gb + 1, p_both_score))
                
            # Both miss → continue (no change to goals)
            p_both_miss = p * (1.0 - p_sd_a) * (1.0 - p_sd_b)
            if p_both_miss > 0:
                next_sd_states.append((ga, gb, p_both_miss))
                
        active_sd_states = next_sd_states
        
        # Check total remaining probability
        remaining = sum(p for _, _, p in active_sd_states)
        if remaining < 1e-12:
            break
            
    # Any remaining probability after max sudden death rounds: split 50/50
    for ga, gb, p in active_sd_states:
        key_a = (ga + 1, gb)
        key_b = (ga, gb + 1)
        results[key_a] = results.get(key_a, 0.0) + p * 0.5
        results[key_b] = results.get(key_b, 0.0) + p * 0.5
    
    return results


def generate_ko_final_grid(config: MatchModelConfig, max_final_goals: int = 15,
                            pen_conv_a: float = None, pen_conv_b: float = None) -> Dict[int, Dict[int, float]]:
    """
    Generates the full knockout probability grid including:
    - Layer 1: 90-minute result (Poisson/NB + Dixon-Coles)
    - Layer 2: Extra time goals (30 min, fatigue-adjusted)
    - Layer 3: Penalty shootout (all goals scored count)
    
    The final grid guarantees NO draws: P(a, b) = 0 when a == b.
    All goals from all phases are summed into the final score.
    
    Args:
        config: Match model configuration
        max_final_goals: Maximum goals per team in the final grid
        pen_conv_a: Team A penalty conversion rate (default: from CONSTANTS)
        pen_conv_b: Team B penalty conversion rate (default: from CONSTANTS)
    """
    # Layer 1: 90-minute probability grid
    grid_90 = generate_joint_grid(config)
    max_90 = config.max_goals
    
    # Extra time parameters
    et_time = CONSTANTS["et_time_fraction"]
    et_fatigue = CONSTANTS["et_fatigue_factor"]
    et_rho_damp = CONSTANTS["et_rho_dampening"]
    
    # Squad-depth asymmetry (5-sub era): the stronger side tends to retain more
    # in ET. Controlled by et_depth_asymmetry; 0.0 = original symmetric model.
    # mu is only a proxy for depth, so this is OFF by default pending a backtest.
    _asym = CONSTANTS.get("et_depth_asymmetry", 0.0)
    if _asym != 0.0:
        _tot_mu = config.mu_a + config.mu_b + 1e-6
        _ratio_a = config.mu_a / _tot_mu
        _fatigue_a = min(1.0, et_fatigue + (_ratio_a - 0.5) * _asym)
        _fatigue_b = min(1.0, et_fatigue + ((1.0 - _ratio_a) - 0.5) * _asym)
    else:
        _fatigue_a = _fatigue_b = et_fatigue
    lambda_a_et = config.mu_a * et_time * _fatigue_a
    lambda_b_et = config.mu_b * et_time * _fatigue_b
    max_et_goals = 4  # Max goals per team in ET (very rare to score more)
    
    # Penalty parameters — team-specific if provided
    base_pen_conv = CONSTANTS["pen_conversion_rate"]
    base_pen_sd_conv = CONSTANTS["pen_sudden_death_conversion"]
    pen_max_sd = int(CONSTANTS["pen_max_sudden_death_rounds"])
    
    # Apply team-specific modifiers
    actual_pen_conv_a = pen_conv_a if pen_conv_a is not None else base_pen_conv
    actual_pen_conv_b = pen_conv_b if pen_conv_b is not None else base_pen_conv
    actual_pen_sd_a = base_pen_sd_conv * (actual_pen_conv_a / base_pen_conv) if pen_conv_a is not None else base_pen_sd_conv
    actual_pen_sd_b = base_pen_sd_conv * (actual_pen_conv_b / base_pen_conv) if pen_conv_b is not None else base_pen_sd_conv
    
    # Initialize final grid
    final_grid = {}
    for a in range(max_final_goals + 1):
        final_grid[a] = {}
        for b in range(max_final_goals + 1):
            final_grid[a][b] = 0.0
    
    # ── Layer 1: 90-minute decisive results (non-draws) ──
    for a in range(max_90 + 1):
        for b in range(max_90 + 1):
            if a == b:
                continue  # Draws go to ET
            p = get_grid_val(grid_90, a, b)
            if p < 1e-15:
                continue
            if a <= max_final_goals and b <= max_final_goals:
                final_grid[a][b] += p
    
    # ── Layer 2 & 3: Draws at 90 min → Extra Time → Penalties ──
    # Pre-compute ET goal distributions
    et_dist_a = [poisson_probability(k, lambda_a_et) for k in range(max_et_goals + 1)]
    et_dist_b = [poisson_probability(k, lambda_b_et) for k in range(max_et_goals + 1)]
    
    # Pre-compute penalty distribution (team-specific conversion rates)
    pen_dist = penalty_shootout_distribution(actual_pen_conv_a, actual_pen_conv_b, actual_pen_sd_a, actual_pen_sd_b, pen_max_sd)
    
    for d in range(max_90 + 1):
        p_draw_d = get_grid_val(grid_90, d, d)
        if p_draw_d < 1e-12:
            continue
        
        # Extra time: independent Poisson for additional goals
        for ea in range(max_et_goals + 1):
            for eb in range(max_et_goals + 1):
                p_et = et_dist_a[ea] * et_dist_b[eb]
                
                if p_et < 1e-15:
                    continue
                
                if ea != eb:
                    # ── Layer 2 decisive: ET produced a winner ──
                    final_a = d + ea
                    final_b = d + eb
                    if final_a <= max_final_goals and final_b <= max_final_goals:
                        final_grid[final_a][final_b] += p_draw_d * p_et
                else:
                    # ── Layer 3: Still tied after ET → Penalties ──
                    score_after_et = d + ea  # Both teams have this score
                    p_to_pens = p_draw_d * p_et
                    
                    for (pa, pb), p_pen in pen_dist.items():
                        final_a = score_after_et + pa
                        final_b = score_after_et + pb
                        if final_a <= max_final_goals and final_b <= max_final_goals:
                            final_grid[final_a][final_b] += p_to_pens * p_pen
    
    # Verify: no draws in the final grid
    for d in range(max_final_goals + 1):
        final_grid[d][d] = 0.0
    
    # Normalize (probabilities should sum to ~1.0, small loss from grid truncation)
    total = sum(final_grid[a][b] for a in range(max_final_goals + 1) 
                for b in range(max_final_goals + 1))
    if total > 0 and abs(total - 1.0) > 0.001:
        # Renormalize if significant probability leaked beyond grid
        for a in range(max_final_goals + 1):
            for b in range(max_final_goals + 1):
                final_grid[a][b] /= total
    
    return final_grid


def apply_phase_adjustments(rho: float, lambda_a: float, lambda_b: float,
                             phase: Optional[MatchPhase] = None) -> Tuple[float, float, float]:
    """
    Applies match-phase-aware adjustments to ρ and λ values.
    
    Knockout matches at 90 minutes produce significantly more draws because:
    - Teams play more conservatively (extra time is available as a safety net)
    - Defensive tactics dominate in high-stakes elimination games
    - The psychological weight of a single mistake changes the game plan
    
    The ρ adjustment uses an additive-multiplicative hybrid approach:
    - If base ρ is non-zero: ρ_adj = ρ × multiplier  (amplifies existing correction)
    - If base ρ is zero: ρ_adj = -0.05 × (multiplier - 1)  (applies a base offset)
    This ensures knockout modeling has an effect even when ρ=0.
    
    Returns: (adjusted_rho, adjusted_lambda_a, adjusted_lambda_b)
    """
    if phase is None or phase == MatchPhase.GROUP:
        return rho, lambda_a, lambda_b

    # Phase-specific ρ multiplier (makes Dixon-Coles more negative → more draws)
    rho_multipliers = {
        MatchPhase.R32: CONSTANTS.get("ko_rho_multiplier_r32", 1.2),
        MatchPhase.R16: CONSTANTS["ko_rho_multiplier_r16"],
        MatchPhase.QUARTER: CONSTANTS["ko_rho_multiplier_qf"],
        MatchPhase.SEMI: CONSTANTS["ko_rho_multiplier_sf"],
        MatchPhase.FINAL: CONSTANTS["ko_rho_multiplier_final"],
        MatchPhase.THIRD: CONSTANTS["ko_rho_multiplier_third"],
    }

    multiplier = rho_multipliers.get(phase, 1.0)
    
    # Hybrid approach: multiplicative when rho != 0, additive fallback when rho == 0
    if abs(rho) > 1e-9:
        adjusted_rho = rho * multiplier
    else:
        # When ρ=0, apply a base correction proportional to the phase intensity
        adjusted_rho = -0.05 * (multiplier - 1.0)

    # Defensive λ scaling — phase-specific factors (teams score less as stakes rise)
    phase_lambda_keys = {
        MatchPhase.R32: "ko_lambda_factor_r32",
        MatchPhase.R16: "ko_lambda_factor_r16",
        MatchPhase.QUARTER: "ko_lambda_factor_qf",
        MatchPhase.SEMI: "ko_lambda_factor_sf",
        MatchPhase.FINAL: "ko_lambda_factor_final",
        MatchPhase.THIRD: "ko_lambda_factor_third",
    }
    
    factor_key = phase_lambda_keys.get(phase)
    if factor_key and factor_key in CONSTANTS:
        ko_def_factor = CONSTANTS[factor_key]
    else:
        ko_def_factor = CONSTANTS["ko_defensive_lambda_factor"]
    
    adjusted_lambda_a = lambda_a * ko_def_factor
    adjusted_lambda_b = lambda_b * ko_def_factor

    return adjusted_rho, adjusted_lambda_a, adjusted_lambda_b


def validate_team_name(name: str, strict: bool = False) -> str:
    """
    Validates a team name against the Elo database. Returns the resolved name.
    Warns on stderr if the team is unknown. Raises ValueError in strict mode.
    """
    if not name:
        return name
    
    cleaned = name.strip().lower()
    resolved = TEAM_NAME_MAPPING.get(cleaned, name.strip())
    
    if resolved not in WORLD_CUP_2026_TEAMS:
        msg = f"⚠ Team '{name}' (resolved: '{resolved}') not found in WC 2026 database. Using fallback Elo=1700."
        if strict:
            raise ValueError(msg)
        print(msg, file=sys.stderr)
    
    return resolved


def compute_ev_breakdown(grid: Dict, tip: Tuple[int, int],
                         pts_exact: int = 4, pts_diff: int = 3, pts_tend: int = 2,
                         max_goals: int = 12) -> Dict[str, float]:
    """
    Decomposes the expected value of a tip into its component sources:
    - ev_exact: EV contribution from exact score matches
    - ev_diff: EV contribution from correct difference (but not exact)
    - ev_tend: EV contribution from correct tendency only
    - ev_zero: probability of scoring 0 points
    
    Also returns the probability of scoring each point tier.
    """
    t_a, t_b = tip
    ev_exact = 0.0
    ev_diff = 0.0
    ev_tend = 0.0
    p_exact = 0.0
    p_diff = 0.0
    p_tend = 0.0
    p_zero = 0.0

    for g_a in range(max_goals + 1):
        for g_b in range(max_goals + 1):
            p = get_grid_val(grid, g_a, g_b)
            pts = get_points(t_a, t_b, g_a, g_b, pts_exact, pts_diff, pts_tend)
            
            if pts == pts_exact:
                ev_exact += p * pts_exact
                p_exact += p
            elif pts == pts_diff:
                ev_diff += p * pts_diff
                p_diff += p
            elif pts == pts_tend:
                ev_tend += p * pts_tend
                p_tend += p
            else:
                p_zero += p

    return {
        "ev_total": ev_exact + ev_diff + ev_tend,
        "ev_exact": ev_exact,
        "ev_diff": ev_diff,
        "ev_tend": ev_tend,
        "p_exact": p_exact,  # P(4 pts)
        "p_diff": p_diff,    # P(3 pts)
        "p_tend": p_tend,     # P(2 pts)
        "p_zero": p_zero,     # P(0 pts)
    }


def run_sensitivity_analysis(base_lambda_a: float, base_lambda_b: float,
                              config_template: MatchModelConfig,
                              perturbations: List[float] = None) -> Dict:
    """
    Runs sensitivity analysis by perturbing λ_A and λ_B and checking if the
    optimal tip changes. Reports tip stability and confidence.
    """
    if perturbations is None:
        perturbations = [-0.20, -0.10, 0.0, 0.10, 0.20]
    
    results = []
    base_tip = None
    base_ev = None
    
    for delta_a in perturbations:
        for delta_b in perturbations:
            mu_a = base_lambda_a * (1.0 + delta_a)
            mu_b = base_lambda_b * (1.0 + delta_b)
            
            if mu_a <= 0.0 or mu_b <= 0.0:
                continue
            
            perturbed_config = MatchModelConfig(
                dist_type=config_template.dist_type,
                mu_a=mu_a,
                mu_b=mu_b,
                alpha_a=config_template.alpha_a,
                alpha_b=config_template.alpha_b,
                rho=config_template.rho,
                max_goals=config_template.max_goals,
                max_tip=config_template.max_tip,
                pts_exact=config_template.pts_exact,
                pts_diff=config_template.pts_diff,
                pts_tend=config_template.pts_tend,
                phase=config_template.phase,
            )
            
            tips, _, _ = solve_optimal_tip(perturbed_config)
            optimal = tips[0]
            
            entry = {
                "delta_a": delta_a,
                "delta_b": delta_b,
                "mu_a": mu_a,
                "mu_b": mu_b,
                "tip": optimal[0],
                "ev": optimal[1],
                "rank2_tip": tips[1][0] if len(tips) > 1 else None,
                "rank2_ev": tips[1][1] if len(tips) > 1 else 0.0,
            }
            results.append(entry)
            
            if delta_a == 0.0 and delta_b == 0.0:
                base_tip = optimal[0]
                base_ev = optimal[1]
    
    # Analyze stability
    unique_tips = set()
    for r in results:
        unique_tips.add(r["tip"])
    
    tip_consistency = sum(1 for r in results if r["tip"] == base_tip) / max(len(results), 1)
    
    # EV spread (gap between rank 1 and rank 2 at baseline)
    baseline_entry = next((r for r in results if r["delta_a"] == 0.0 and r["delta_b"] == 0.0), None)
    ev_gap = 0.0
    if baseline_entry:
        ev_gap = baseline_entry["ev"] - baseline_entry["rank2_ev"]
    
    # Confidence label
    if tip_consistency >= 0.95 and ev_gap >= 0.05:
        confidence = "LOCK"
    elif tip_consistency >= 0.80 and ev_gap >= 0.02:
        confidence = "STRONG"
    elif tip_consistency >= 0.60:
        confidence = "MARGINAL"
    else:
        confidence = "COIN-FLIP"
    
    return {
        "base_tip": base_tip,
        "base_ev": base_ev,
        "confidence": confidence,
        "tip_consistency": tip_consistency,
        "ev_gap": ev_gap,
        "unique_tips": list(unique_tips),
        "num_scenarios": len(results),
        "details": results,
    }


def solve_optimal_tip(config_or_lamA, lam_B=None, rho=0.0, max_goals=12, max_tip=6):
    """
    Solves for the optimal Kicktipp tip given a match configuration.
    Supports both MatchModelConfig objects and raw lambda values.
    """
    if isinstance(config_or_lamA, MatchModelConfig):
        config = config_or_lamA
    else:
        config = MatchModelConfig(
            dist_type=ModelDistribution.POISSON,
            mu_a=config_or_lamA,
            mu_b=lam_B if lam_B is not None else config_or_lamA,
            alpha_a=0.0,
            alpha_b=0.0,
            rho=rho,
            max_goals=max_goals,
            max_tip=max_tip
        )
        
    if config.mu_a is None or config.mu_b is None:
        raise TypeError("mu_a and mu_b must be numeric")
    if isinstance(config.mu_a, str) or isinstance(config.mu_b, str):
        raise TypeError("mu_a and mu_b must be numeric")
        
    grid = generate_joint_grid(config)

    try:
        raw_max_tip = int(config.max_tip)
        if math.isnan(raw_max_tip) or math.isinf(raw_max_tip):
            raw_max_tip = 6
    except (ValueError, TypeError):
        raw_max_tip = 6
    max_tip_clamped = max(0, min(100, raw_max_tip))
    
    sorted_tips, sorted_scores, outcomes = solve_optimal_tip_from_grid(
        grid, 
        max_tip_clamped,
        pts_exact=config.pts_exact,
        pts_diff=config.pts_diff,
        pts_tend=config.pts_tend
    )
    
    return sorted_tips, sorted_scores[:5], outcomes


# ==============================================================================
# BATCH PREDICTION ENGINE
# ==============================================================================

def predict_single_match(row: dict, pts_exact: int = 4, pts_diff: int = 3,
                         pts_tend: int = 2, max_tip: int = 5, max_goals: int = 12,
                         strict: bool = False) -> dict:
    """
    Runs the full prediction pipeline for a single match defined by a dict.
    Returns a dict with the prediction results.
    """
    team_a = row.get("team_a", "Team A")
    team_b = row.get("team_b", "Team B")
    elo_a = row.get("elo_a", None)
    elo_b = row.get("elo_b", None)
    
    # Validate team names
    if strict:
        validate_team_name(team_a, strict=True)
        validate_team_name(team_b, strict=True)
    
    # Base lambdas from Elo
    lambda_a_base, lambda_b_base = estimate_base_lambdas_from_elo(team_a, team_b, elo_a, elo_b)
    
    # Apply form multipliers
    form_a = float(row.get("form_a", row.get("formA", 1.0)))
    form_b = float(row.get("form_b", row.get("formB", 1.0)))
    lambda_a_base *= form_a
    lambda_b_base *= form_b
    
    # ── Market odds integration ──
    # If odds are provided, reverse-engineer market-implied lambdas and blend
    odds_source = None
    market_z = 0.0
    odds_home = row.get("odds_home", row.get("odds_h", None))
    odds_draw = row.get("odds_draw", row.get("odds_d", None))
    odds_away = row.get("odds_away", row.get("odds_a", None))
    market_weight = float(row.get("market_weight", 0.8))
    
    # Parse time_to_kickoff and volume for Bayesian blending
    time_to_kickoff = row.get("time_to_kickoff", row.get("time_to_ko", None))
    if time_to_kickoff is not None:
        try:
            time_to_kickoff = float(time_to_kickoff)
        except (ValueError, TypeError):
            time_to_kickoff = None
            
    volume = row.get("volume", row.get("vol", None))
    if volume is not None:
        try:
            volume = float(volume)
        except (ValueError, TypeError):
            volume = None
            
    if odds_home is not None and odds_draw is not None and odds_away is not None:
        try:
            oh, od, oa = float(odds_home), float(odds_draw), float(odds_away)
            if oh > 1.0 and od > 1.0 and oa > 1.0:
                # Strip vig using Shin's Method and get fair probabilities and insider proportion z
                raw_h, raw_d, raw_a = 1.0/oh, 1.0/od, 1.0/oa
                (p_h, p_d, p_a), market_z = strip_vig_shin(raw_h, raw_d, raw_a)
                
                # Reverse Poisson: P(1x2) → λ
                rho_for_reverse = float(row.get("rho", -0.05))
                market_la, market_lb = odds_to_lambdas(p_h, p_d, p_a, rho_for_reverse)
                
                # Blend: default 80% market, 20% Elo (supporting Bayesian blend if time/volume are provided)
                lambda_a_base, lambda_b_base = blend_lambdas(
                    lambda_a_base, lambda_b_base,
                    market_la, market_lb,
                    market_weight,
                    time_to_kickoff=time_to_kickoff,
                    volume=volume
                )
                odds_source = "manual"
        except (ValueError, TypeError) as e:
            import sys
            print(f"⚠ Warning: Odds parsing failed for {row.get('team_a')} vs {row.get('team_b')} ({e}). Falling back to Elo-only.", file=sys.stderr)
    
    # Build context dicts
    def ctx(suffix):
        c = {}
        for key in ["elevation", "temp", "humidity"]:
            if key in row:
                c[key] = float(row[key])
        mappings = {
            "accl_days": f"accl_days_{suffix}",
            "heat_accl_days": f"heat_accl_days_{suffix}",
            "rest_days": f"rest_days_{suffix}",
            "travel_miles": f"travel_miles_{suffix}",
            "tz_crossed": f"tz_crossed_{suffix}",
            "direction": f"direction_{suffix}",
            "status": f"status_{suffix}",
            "fan_support_pct": f"fan_pct_{suffix}",
            "missing_value": f"missing_value_{suffix}",
            "missing_count": f"missing_count_{suffix}",
        }
        for ctx_key, row_key in mappings.items():
            if row_key in row:
                val = row[row_key]
                if ctx_key in ("tz_crossed", "missing_count"):
                    c[ctx_key] = int(float(val)) if val is not None else 0
                elif ctx_key in ("direction", "status"):
                    c[ctx_key] = str(val) if val is not None else "None"
                else:
                    c[ctx_key] = float(val) if val is not None else 0.0
        return c
    
    ctx_a = ctx("a")
    ctx_b = ctx("b")
    
    ctx_a["team_name"] = team_a
    ctx_b["team_name"] = team_b
    
    # Inject venue and PPDA
    venue = row.get("venue", None)
    if venue:
        ctx_a["venue"] = venue
        ctx_b["venue"] = venue
    ctx_a["ppda"] = TEAM_PPDA.get(team_a, 11.0)
    ctx_b["ppda"] = TEAM_PPDA.get(team_b, 11.0)
    
    # Adjusted lambdas
    lambda_a, lambda_b = get_adjusted_lambdas(lambda_a_base, lambda_b_base, ctx_a, ctx_b)
    
    # Parse match phase
    phase = parse_match_phase(row.get("phase"))
    
    # Apply phase adjustments
    rho = float(row.get("rho", -0.05))
    rho_adj, lambda_a, lambda_b = apply_phase_adjustments(rho, lambda_a, lambda_b, phase)
    
    # Distribution parameters
    alpha_a = float(row.get("alpha_a", 0.0))
    alpha_b = float(row.get("alpha_b", 0.0))
    dist_type = ModelDistribution.NEGATIVE_BINOMIAL if (alpha_a > 0.0 or alpha_b > 0.0) else ModelDistribution.POISSON
    
    # Generate 90-minute base grid for BOTH stages (to be used for Golden Boot tracking)
    config_90 = MatchModelConfig(
        dist_type=dist_type,
        mu_a=lambda_a,
        mu_b=lambda_b,
        alpha_a=alpha_a,
        alpha_b=alpha_b,
        rho=rho_adj,
        max_goals=max_goals,
        max_tip=max_tip,
        pts_exact=pts_exact,
        pts_diff=pts_diff,
        pts_tend=pts_tend,
        phase=phase,
    )
    grid_90 = generate_joint_grid(config_90)
    
    # Determine if this is a knockout match that uses the 3-layer model
    # (KO model: 90min + ET + penalties — final score always has a winner)
    # 3rd place match uses the KO model too (it also goes to ET/pens)
    is_ko_with_et = phase is not None and phase not in (MatchPhase.GROUP,)
    
    if is_ko_with_et:
        # KO matches: auto-increase max_tip to cover penalty-inflated scores
        ko_max_tip = max(max_tip, 10)
        ko_max_final = 15  # Grid extends to 15 to cover extreme penalty scenarios
        
        config = MatchModelConfig(
            dist_type=dist_type,
            mu_a=lambda_a,
            mu_b=lambda_b,
            alpha_a=alpha_a,
            alpha_b=alpha_b,
            rho=rho_adj,
            max_goals=max_goals,
            max_tip=ko_max_tip,
            pts_exact=pts_exact,
            pts_diff=pts_diff,
            pts_tend=pts_tend,
            phase=phase,
        )
        
        # Generate the 3-layer KO grid (with team-specific penalty strength)
        base_pen_rate = CONSTANTS["pen_conversion_rate"]
        pen_mod_a = PENALTY_STRENGTH.get(team_a, 1.0)
        pen_mod_b = PENALTY_STRENGTH.get(team_b, 1.0)
        grid = generate_ko_final_grid(
            config, max_final_goals=ko_max_final,
            pen_conv_a=base_pen_rate * pen_mod_a,
            pen_conv_b=base_pen_rate * pen_mod_b,
        )
        
        # Solve optimal tip against KO grid
        tips, scores, outcomes = solve_optimal_tip_from_grid(
            grid, pts_exact=pts_exact, pts_diff=pts_diff, pts_tend=pts_tend,
            max_tip=ko_max_tip
        )
        
        optimal_tip = tips[0][0]
        optimal_ev = tips[0][1]
        
        # Override outcomes: for KO, draw is always 0 (the solver might 
        # report a tiny draw prob from numerical noise, force it to 0)
        p_home = outcomes[0]
        p_away = outcomes[2]
        outcomes = (p_home, 0.0, p_away)
        
        # EV breakdown
        breakdown = compute_ev_breakdown(grid, optimal_tip, pts_exact, pts_diff, pts_tend, ko_max_final)
    else:
        # GROUP stage: use standard model
        tips, scores, outcomes = solve_optimal_tip(config_90)
        optimal_tip = tips[0][0]
        optimal_ev = tips[0][1]
        grid = grid_90
        breakdown = compute_ev_breakdown(grid, optimal_tip, pts_exact, pts_diff, pts_tend, max_goals)
    
    return {
        "team_a": team_a,
        "team_b": team_b,
        "phase": phase.value if phase else "GROUP",
        "lambda_a_base": lambda_a_base,
        "lambda_b_base": lambda_b_base,
        "lambda_a_adj": lambda_a,
        "lambda_b_adj": lambda_b,
        "rho_base": rho,
        "rho_adj": rho_adj,
        "optimal_tip": f"{optimal_tip[0]}:{optimal_tip[1]}",
        "optimal_tip_a": optimal_tip[0],
        "optimal_tip_b": optimal_tip[1],
        "ev": optimal_ev,
        "p_home": outcomes[0],
        "p_draw": outcomes[1],
        "p_away": outcomes[2],
        "top_scores": [(s[0], s[1], p) for (s, p) in scores[:5]],
        "top_tips": [{"tip": f"{t[0]}:{t[1]}", "ev": ev} for t, ev in tips[:5]],
        "breakdown": breakdown,
        "config": config if is_ko_with_et else config_90,
        "grid": grid,
        "grid_90": grid_90,
        "is_ko_model": is_ko_with_et,
        "odds_source": odds_source,
        "market_z": market_z,
    }


def run_batch_prediction(csv_path: str, **kwargs) -> List[dict]:
    """
    Reads a CSV of matches and runs predictions for all of them.
    """
    results = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean row values
            clean_row = {}
            for k, v in row.items():
                if v is not None and v.strip() != '':
                    clean_row[k] = v.strip()
            
            try:
                result = predict_single_match(clean_row, **kwargs)
                results.append(result)
            except Exception as e:
                results.append({
                    "team_a": clean_row.get("team_a", "?"),
                    "team_b": clean_row.get("team_b", "?"),
                    "error": str(e),
                })
    
    return results


def format_batch_output(results: List[dict], json_output: bool = False) -> str:
    """Formats batch prediction results as either a table or JSON."""
    if json_output:
        serializable = []
        for r in results:
            entry = {k: v for k, v in r.items() if k not in ("config", "grid")}
            serializable.append(entry)
        return json_module.dumps(serializable, indent=2, ensure_ascii=False)
    
    lines = []
    lines.append("=" * 100)
    lines.append(f"{'Match':<30} {'Phase':<7} {'Tip':>5} {'EV':>7} {'Home%':>7} {'Draw%':>7} {'Away%':>7} {'Conf':>10}")
    lines.append("=" * 100)
    
    total_ev = 0.0
    for r in results:
        if "error" in r:
            lines.append(f"  {r['team_a']} vs {r['team_b']}: ERROR - {r['error']}")
            continue
        
        match_label = f"{r['team_a']} - {r['team_b']}"
        if len(match_label) > 28:
            match_label = match_label[:28]
        
        total_ev += r["ev"]
        
        # Determine confidence from EV gap
        tips = r.get("top_tips", [])
        if len(tips) >= 2:
            gap = tips[0]["ev"] - tips[1]["ev"]
            if gap >= 0.05:
                conf = "LOCK"
            elif gap >= 0.02:
                conf = "STRONG"
            elif gap >= 0.005:
                conf = "MARGINAL"
            else:
                conf = "COIN-FLIP"
        else:
            conf = "—"
        
        lines.append(f"  {match_label:<28} {r['phase']:<7} {r['optimal_tip']:>5} {r['ev']:>7.3f} {r['p_home']*100:>6.1f}% {r['p_draw']*100:>6.1f}% {r['p_away']*100:>6.1f}% {conf:>10}")
    
    lines.append("=" * 100)
    valid = [r for r in results if "error" not in r]
    lines.append(f"  Σ Expected Points: {total_ev:.2f} over {len(valid)} matches | Avg: {total_ev/max(len(valid),1):.3f}/match")
    lines.append("=" * 100)
    
    return "\n".join(lines)


def format_strategic_output(result: dict, team_a: str, team_b: str,
                           is_estimated: bool = True, sensitivity: dict = None,
                           verbose: bool = False) -> str:
    """
    Generates the enhanced strategic output with reasoning, EV breakdown,
    and risk profile.
    """
    lines = []
    
    phase = result.get("phase", "GROUP")
    phase_label = f" [{phase}]" if phase != "GROUP" else ""
    
    lines.append(f"{'═' * 62}")
    lines.append(f"  Spiel: {team_a} vs {team_b}{phase_label}")
    lines.append(f"{'═' * 62}")
    
    # Lambda display
    label = "ELO-Basis" if is_estimated else "Manuell"
    lines.append(f"\n  ⚽ Torerwartung ({label}):")
    lines.append(f"     λ_base: {result['lambda_a_base']:.3f} ({team_a}) | {result['lambda_b_base']:.3f} ({team_b})")
    lines.append(f"     λ_adj:  {result['lambda_a_adj']:.3f} ({team_a}) | {result['lambda_b_adj']:.3f} ({team_b})")
    
    if result.get("rho_base") != result.get("rho_adj"):
        lines.append(f"     ρ:      {result['rho_base']:.3f} → {result['rho_adj']:.3f} (K.o.-Anpassung)")
    else:
        lines.append(f"     ρ:      {result['rho_adj']:.3f}")
    
    # Tendency probabilities
    lines.append(f"\n  📊 Tendenzwahrscheinlichkeiten:")
    lines.append(f"     Heimsieg ({team_a}): {result['p_home']*100:>5.1f}%")
    lines.append(f"     Unentschieden:       {result['p_draw']*100:>5.1f}%")
    lines.append(f"     Auswärtssieg ({team_b}): {result['p_away']*100:>5.1f}%")
    
    # Top exact scores
    lines.append(f"\n  🎯 Wahrscheinlichste Ergebnisse:")
    for (ga, gb, p) in result.get("top_scores", [])[:5]:
        lines.append(f"     {ga}:{gb}  ({p*100:.1f}%)")
    
    # Optimal tip with reasoning
    tips = result.get("top_tips", [])
    lines.append(f"\n  {'─' * 58}")
    lines.append(f"  ★ OPTIMALER TIPP")
    lines.append(f"  {'─' * 58}")
    
    if tips:
        best = tips[0]
        lines.append(f"     ➤  {best['tip']}  |  E = {best['ev']:.4f} Punkte")
        
        # EV breakdown
        bd = result.get("breakdown", {})
        if bd:
            lines.append(f"\n  💡 EV-Zerlegung:")
            lines.append(f"     Exakt-Treffer:   {bd.get('ev_exact', 0):.4f}  (P = {bd.get('p_exact', 0)*100:.2f}%)")
            lines.append(f"     Differenz-Match: {bd.get('ev_diff', 0):.4f}  (P = {bd.get('p_diff', 0)*100:.2f}%)")
            lines.append(f"     Tendenz-Match:   {bd.get('ev_tend', 0):.4f}  (P = {bd.get('p_tend', 0)*100:.2f}%)")
            lines.append(f"     Summe:           {bd.get('ev_total', 0):.4f}")
        
        # Risk profile
        if bd:
            lines.append(f"\n  🎲 Risikoprofil:")
            lines.append(f"     P(4 Punkte) = {bd.get('p_exact', 0)*100:>5.2f}%  │  P(3 Punkte) = {bd.get('p_diff', 0)*100:>5.2f}%")
            lines.append(f"     P(2 Punkte) = {bd.get('p_tend', 0)*100:>5.2f}%  │  P(0 Punkte) = {bd.get('p_zero', 0)*100:>5.2f}%")
        
        # Strategic reasoning
        if len(tips) >= 2:
            ev_gap = tips[0]["ev"] - tips[1]["ev"]
            lines.append(f"\n  🧠 Strategische Analyse:")
            
            t1 = tips[0]["tip"]
            t2 = tips[1]["tip"]
            t1_parts = t1.split(":")
            t2_parts = t2.split(":")
            
            if ev_gap >= 0.05:
                lines.append(f"     Tipp {t1} ist deutlich dominant (Δ = +{ev_gap:.4f}).")
                lines.append(f"     Hohe Sicherheit — dieser Tipp ist ein LOCK.")
            elif ev_gap >= 0.02:
                lines.append(f"     Tipp {t1} schlägt {t2} klar (Δ = +{ev_gap:.4f}).")
                lines.append(f"     STARKER Tipp mit solidem EV-Vorsprung.")
            elif ev_gap >= 0.005:
                lines.append(f"     Tipp {t1} schlägt {t2} knapp (Δ = +{ev_gap:.4f}).")
                lines.append(f"     MARGINALER Vorsprung — bei leicht anderen Annahmen könnte {t2} besser sein.")
            else:
                lines.append(f"     Tipp {t1} und {t2} sind praktisch gleichwertig (Δ = +{ev_gap:.4f}).")
                lines.append(f"     COIN-FLIP — beide Tipps sind vertretbar.")
            
            # Explain WHY this tip is optimal
            if bd:
                total_ev = bd.get("ev_total", 0)
                if total_ev > 0:
                    exact_pct = bd.get("ev_exact", 0) / total_ev * 100
                    diff_pct = bd.get("ev_diff", 0) / total_ev * 100
                    tend_pct = bd.get("ev_tend", 0) / total_ev * 100
                    
                    dominant = "Exakt-Treffer" if exact_pct >= diff_pct and exact_pct >= tend_pct else \
                               "Differenz-Bonus" if diff_pct >= tend_pct else "Tendenz-Basis"
                    lines.append(f"     Haupttreiber: {dominant} ({max(exact_pct, diff_pct, tend_pct):.0f}% des EV)")
    
    # Remaining top tips
    if len(tips) > 1:
        lines.append(f"\n  📋 Alternative Tipps:")
        for i, t in enumerate(tips[1:5], 2):
            lines.append(f"     Rang {i}: {t['tip']:>5}  |  E = {t['ev']:.4f}")
    
    # Sensitivity analysis results
    if sensitivity:
        lines.append(f"\n  {'─' * 58}")
        lines.append(f"  🔬 Sensitivitätsanalyse (λ ± 10%, ± 20%)")
        lines.append(f"  {'─' * 58}")
        lines.append(f"     Konfidenz:        {sensitivity['confidence']}")
        lines.append(f"     Tipp-Stabilität:  {sensitivity['tip_consistency']*100:.0f}% ({sensitivity['num_scenarios']} Szenarien)")
        lines.append(f"     EV-Lücke:         {sensitivity['ev_gap']:.4f}")
        lines.append(f"     Alternative Tips: {', '.join(f'{t[0]}:{t[1]}' for t in sensitivity['unique_tips'])}")
    
    # Verbose: full grid
    if verbose and "grid" in result:
        grid = result["grid"]
        lines.append(f"\n  📊 Wahrscheinlichkeitsmatrix (Top 8×8):")
        header = "       " + "".join(f" {g_b:>6}" for g_b in range(8))
        lines.append(f"     {header}")
        for g_a in range(8):
            row_vals = "".join(f" {get_grid_val(grid, g_a, g_b)*100:>5.1f}%" for g_b in range(8))
            lines.append(f"     {g_a:>2}:{row_vals}")
    
    lines.append(f"\n{'═' * 62}")
    
    return "\n".join(lines)


# ==============================================================================
# CLI MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="WM 2026 Tippspiel-Optimierer v4 (Advanced Knockout + Sensitivity + Batch)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  Single match:   python3 predictor.py --teamA Germany --teamB Japan
  With phase:     python3 predictor.py --teamA Germany --teamB Japan --phase QF
  With odds:      python3 predictor.py --teamA Germany --teamB Japan --odds-home 1.85 --odds-draw 3.40 --odds-away 4.50
  Market weight:  python3 predictor.py --teamA Germany --teamB Japan --odds-home 1.85 --odds-draw 3.40 --odds-away 4.50 --market-weight 1.0
  Sensitivity:    python3 predictor.py --teamA Germany --teamB Japan --sensitivity
  Batch mode:     python3 predictor.py --batch data/sample_matchday.csv
  JSON output:    python3 predictor.py --batch data/sample_matchday.csv --json
"""
    )
    parser.add_argument("--teamA", type=str, default="Team A", help="Name von Heimteam")
    parser.add_argument("--teamB", type=str, default="Team B", help="Name von Auswärtsteam")
    parser.add_argument("--lambdaA", type=float, default=None, help="Torerwartung lambda für Team A (xG)")
    parser.add_argument("--lambdaB", type=float, default=None, help="Torerwartung lambda für Team B (xG)")
    parser.add_argument("--rho", type=float, default=-0.05, help="Dixon-Coles Korrekturfaktor")
    parser.add_argument("--max_tip", type=int, default=5, help="Maximaler Tore-Tipp")
    parser.add_argument("--max_goals", type=int, default=12, help="Grid limit for goal calculations")
    
    # Distributions
    parser.add_argument("--distribution", type=str, default="poisson", choices=["poisson", "negative_binomial"], help="Goal probability distribution")
    parser.add_argument("--alphaA", type=float, default=0.0, help="Dispersion parameter for Team A")
    parser.add_argument("--alphaB", type=float, default=0.0, help="Dispersion parameter for Team B")
    
    # Match Phase (NEW in v4)
    parser.add_argument("--phase", type=str, default=None, help="Match phase: GROUP, R16, QF, SF, FINAL, THIRD")
    
    # Environmental Factors
    parser.add_argument("--elevation", type=float, default=0.0, help="Stadium elevation in meters")
    parser.add_argument("--temp", type=float, default=20.0, help="Ambient temperature in Celsius")
    parser.add_argument("--humidity", type=float, default=0.0, help="Relative humidity percentage")
    parser.add_argument("--accl_days_A", type=float, default=0.0, help="Altitude acclimation days for Team A")
    parser.add_argument("--accl_days_B", type=float, default=0.0, help="Altitude acclimation days for Team B")
    parser.add_argument("--heat_accl_days_A", type=float, default=0.0, help="Heat acclimation days for Team A")
    parser.add_argument("--heat_accl_days_B", type=float, default=0.0, help="Heat acclimation days for Team B")
    
    # Travel & Fatigue
    parser.add_argument("--rest_days_A", type=float, default=5.0, help="Days of rest for Team A")
    parser.add_argument("--rest_days_B", type=float, default=5.0, help="Days of rest for Team B")
    parser.add_argument("--travel_miles_A", type=float, default=0.0, help="Miles traveled for Team A")
    parser.add_argument("--travel_miles_B", type=float, default=0.0, help="Miles traveled for Team B")
    parser.add_argument("--tz_crossed_A", type=int, default=0, help="Time zones crossed for Team A")
    parser.add_argument("--tz_crossed_B", type=int, default=0, help="Time zones crossed for Team B")
    parser.add_argument("--travel_dir_A", type=str, default="None", choices=["East", "West", "None"], help="Travel direction for Team A")
    parser.add_argument("--travel_dir_B", type=str, default="None", choices=["East", "West", "None"], help="Travel direction for Team B")
    
    # Host & Fans
    parser.add_argument("--status_A", type=str, default="Neutral", choices=["True Home", "True_Home", "Co-Host", "Co_Host", "Neutral"], help="Host status of Team A")
    parser.add_argument("--status_B", type=str, default="Neutral", choices=["True Home", "True_Home", "Co-Host", "Co_Host", "Neutral"], help="Host status of Team B")
    parser.add_argument("--fan_pct_A", type=float, default=0.5, help="Fan support percentage for Team A")
    parser.add_argument("--fan_pct_B", type=float, default=0.5, help="Fan support percentage for Team B")
    
    # Custom Tipping Points
    parser.add_argument("--pts_exact", type=int, default=4, help="Kicktipp points for exact match")
    parser.add_argument("--pts_diff", type=int, default=3, help="Kicktipp points for correct goal difference")
    parser.add_argument("--pts_tendency", type=int, default=2, help="Kicktipp points for correct tendency")
    
    # Team Form Factors
    parser.add_argument("--formA", type=float, default=1.0, help="Form factor multiplier for Team A")
    parser.add_argument("--formB", type=float, default=1.0, help="Form factor multiplier for Team B")
    
    # Missing / Injured Starters (Phase 3)
    parser.add_argument("--missing_value_A", type=float, default=0.0, help="Total market value of missing starters for Team A in millions €")
    parser.add_argument("--missing_value_B", type=float, default=0.0, help="Total market value of missing starters for Team B in millions €")
    parser.add_argument("--missing_count_A", type=int, default=0, help="Number of missing starters for Team A")
    parser.add_argument("--missing_count_B", type=int, default=0, help="Number of missing starters for Team B")
    
    # v4 Features
    parser.add_argument("--config", type=str, default=None, help="JSON config file path")
    parser.add_argument("--batch", type=str, default=None, help="CSV file for batch prediction")
    parser.add_argument("--json", action="store_true", default=False, help="Output results as JSON")
    parser.add_argument("--output", type=str, default=None, help="Write results to file")
    parser.add_argument("--sensitivity", action="store_true", default=False, help="Run sensitivity analysis")
    parser.add_argument("--verbose", action="store_true", default=False, help="Show full probability grid")
    parser.add_argument("--strict", action="store_true", default=False, help="Exit on unknown team names")
    
    # Market Odds Integration
    parser.add_argument("--odds-home", type=float, default=None, help="Decimal odds for home win (e.g., 1.85)")
    parser.add_argument("--odds-draw", type=float, default=None, help="Decimal odds for draw (e.g., 3.40)")
    parser.add_argument("--odds-away", type=float, default=None, help="Decimal odds for away win (e.g., 4.50)")
    parser.add_argument("--market-weight", type=float, default=0.8, help="Blend ratio: 0=Elo only, 1=market only (default: 0.8)")
    parser.add_argument("--fetch-odds", action="store_true", default=False, help="Auto-fetch odds from Polymarket/APIs")
    parser.add_argument("--odds-api-key", type=str, default=None, help="API key for the-odds-api.com")
    
    args = parser.parse_args()
    
    if args.config:
        load_config(args.config)

    # ── BATCH MODE ──
    if args.batch:
        results = run_batch_prediction(
            args.batch,
            pts_exact=args.pts_exact,
            pts_diff=args.pts_diff,
            pts_tend=args.pts_tendency,
            max_tip=args.max_tip,
            max_goals=args.max_goals,
            strict=args.strict,
        )
        output = format_batch_output(results, json_output=args.json)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"Results written to {args.output}")
        else:
            print(output)
        return

    # ── SINGLE MATCH MODE ──
    status_map = {
        "True Home": "True Home", "True_Home": "True Home",
        "Co-Host": "Co-Host", "Co_Host": "Co-Host",
        "Neutral": "Neutral"
    }
    
    # Validate team names
    if args.strict:
        validate_team_name(args.teamA, strict=True)
        validate_team_name(args.teamB, strict=True)
    else:
        validate_team_name(args.teamA, strict=False)
        validate_team_name(args.teamB, strict=False)
    
    teamA_context = {
        "team_name": args.teamA,
        "elevation": args.elevation, "temp": args.temp, "humidity": args.humidity,
        "accl_days": args.accl_days_A, "heat_accl_days": args.heat_accl_days_A,
        "rest_days": args.rest_days_A, "travel_miles": args.travel_miles_A,
        "tz_crossed": args.tz_crossed_A, "direction": args.travel_dir_A,
        "status": status_map[args.status_A], "fan_support_pct": args.fan_pct_A,
        "missing_value": args.missing_value_A,
        "missing_count": args.missing_count_A,
    }
    teamB_context = {
        "team_name": args.teamB,
        "elevation": args.elevation, "temp": args.temp, "humidity": args.humidity,
        "accl_days": args.accl_days_B, "heat_accl_days": args.heat_accl_days_B,
        "rest_days": args.rest_days_B, "travel_miles": args.travel_miles_B,
        "tz_crossed": args.tz_crossed_B, "direction": args.travel_dir_B,
        "status": status_map[args.status_B], "fan_support_pct": args.fan_pct_B,
        "missing_value": args.missing_value_B,
        "missing_count": args.missing_count_B,
    }
    
    # Base expected goals
    lambda_A_base = args.lambdaA
    lambda_B_base = args.lambdaB
    is_estimated = False
    if lambda_A_base is None or lambda_B_base is None:
        lambda_A_base, lambda_B_base = estimate_base_lambdas_from_elo(args.teamA, args.teamB)
        is_estimated = True

    # Form multipliers
    if args.formA != 1.0 or args.formB != 1.0:
        lambda_A_base *= args.formA
        lambda_B_base *= args.formB

    # ── Market odds integration (CLI) ──
    odds_info = None
    odds_home = args.odds_home
    odds_draw = args.odds_draw
    odds_away = args.odds_away
    
    # Auto-fetch from Polymarket/APIs if requested
    if args.fetch_odds and odds_home is None:
        try:
            from odds_client import OddsClient
            client = OddsClient(odds_api_key=args.odds_api_key)
            match_odds = client.get_match_probabilities(args.teamA, args.teamB)
            if match_odds:
                # Convert probabilities back to decimal odds for the reverse solver
                odds_home = 1.0 / match_odds.p_home if match_odds.p_home > 0.01 else None
                odds_draw = 1.0 / match_odds.p_draw if match_odds.p_draw > 0.01 else None
                odds_away = 1.0 / match_odds.p_away if match_odds.p_away > 0.01 else None
                odds_info = f"auto-fetched from {match_odds.source}"
            else:
                print(f"⚠ Could not fetch odds for {args.teamA} vs {args.teamB}. Using Elo only.")
        except ImportError:
            print("⚠ odds_client.py not found. Using Elo only.")
        except Exception as e:
            print(f"⚠ Odds fetch error: {e}. Using Elo only.")
    
    if odds_home is not None and odds_draw is not None and odds_away is not None:
        if odds_home > 1.0 and odds_draw > 1.0 and odds_away > 1.0:
            total_raw = 1.0/odds_home + 1.0/odds_draw + 1.0/odds_away   # kept for vig display
            p_h, p_d, p_a = extract_true_probs_power(odds_home, odds_draw, odds_away)
            
            market_la, market_lb = odds_to_lambdas(p_h, p_d, p_a, args.rho)
            mw = args.market_weight
            
            elo_la_orig, elo_lb_orig = lambda_A_base, lambda_B_base
            lambda_A_base, lambda_B_base = blend_lambdas(
                lambda_A_base, lambda_B_base, market_la, market_lb, mw
            )
            
            if not odds_info:
                overround = (total_raw - 1.0) * 100
                odds_info = f"manual odds {odds_home}/{odds_draw}/{odds_away} (vig={overround:.1f}%)"
            
            is_estimated = False
            if not args.json:
                print(f"📊 Market odds: {odds_info}")
                print(f"   Market λ: ({market_la:.3f}, {market_lb:.3f})  |  Elo λ: ({elo_la_orig:.3f}, {elo_lb_orig:.3f})")
                print(f"   Blended λ ({mw:.0%} market): ({lambda_A_base:.3f}, {lambda_B_base:.3f})")
                print()
    
    # Contextual adjustment
    lambda_A, lambda_B = get_adjusted_lambdas(lambda_A_base, lambda_B_base, teamA_context, teamB_context)
    
    # Phase adjustment
    phase = parse_match_phase(args.phase)
    rho_adj, lambda_A, lambda_B = apply_phase_adjustments(args.rho, lambda_A, lambda_B, phase)
    
    dist_type = ModelDistribution.NEGATIVE_BINOMIAL if args.distribution == "negative_binomial" else ModelDistribution.POISSON
    config = MatchModelConfig(
        dist_type=dist_type,
        mu_a=lambda_A, mu_b=lambda_B,
        alpha_a=args.alphaA, alpha_b=args.alphaB,
        rho=rho_adj,
        max_goals=args.max_goals, max_tip=args.max_tip,
        pts_exact=args.pts_exact, pts_diff=args.pts_diff, pts_tend=args.pts_tendency,
        phase=phase,
    )
    
    tips, scores, outcomes = solve_optimal_tip(config)
    
    # Build result dict
    grid = generate_joint_grid(config)
    optimal_tip = tips[0][0]
    breakdown = compute_ev_breakdown(grid, optimal_tip, args.pts_exact, args.pts_diff, args.pts_tendency, args.max_goals)
    
    result = {
        "team_a": args.teamA, "team_b": args.teamB,
        "phase": phase.value if phase else "GROUP",
        "lambda_a_base": lambda_A_base, "lambda_b_base": lambda_B_base,
        "lambda_a_adj": lambda_A, "lambda_b_adj": lambda_B,
        "rho_base": args.rho, "rho_adj": rho_adj,
        "optimal_tip": f"{optimal_tip[0]}:{optimal_tip[1]}",
        "p_home": outcomes[0], "p_draw": outcomes[1], "p_away": outcomes[2],
        "top_scores": [(s[0], s[1], p) for (s, p) in scores[:5]],
        "top_tips": [{"tip": f"{t[0]}:{t[1]}", "ev": ev} for t, ev in tips[:5]],
        "breakdown": breakdown,
        "grid": grid,
        "ev": tips[0][1],
    }
    
    # Sensitivity analysis
    sensitivity = None
    if args.sensitivity:
        sensitivity = run_sensitivity_analysis(lambda_A, lambda_B, config)
    
    # Output
    if args.json:
        json_result = {k: v for k, v in result.items() if k != "grid"}
        if sensitivity:
            json_result["sensitivity"] = {k: v for k, v in sensitivity.items() if k != "details"}
        output = json_module.dumps(json_result, indent=2, ensure_ascii=False)
    else:
        output = format_strategic_output(result, args.teamA, args.teamB, is_estimated, sensitivity, args.verbose)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Results written to {args.output}")
    else:
        print(output)

if __name__ == "__main__":
    main()


