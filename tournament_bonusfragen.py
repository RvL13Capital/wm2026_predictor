#!/usr/bin/env python3
"""
WM 2026 Kicktipp Bonusfragen — Monte Carlo Tournament Simulator

Simulates the entire FIFA World Cup 2026 tournament N times to determine
the optimal pre-tournament bonus tips:
  - 12× Group winner (Gruppensieger A–L)
  - 4× Semifinalist (Halbfinale)
  - 1× World Cup winner (Weltmeister)
  - 1× Top scorer's team (Torschützenkönig-Mannschaft)

Usage:
    python3 tournament_bonusfragen.py                          # Default 10,000 sims
    python3 tournament_bonusfragen.py --sims 50000             # More sims for precision
    python3 tournament_bonusfragen.py --fetch-odds             # Use Polymarket live data
    python3 tournament_bonusfragen.py --json --output tips.json # JSON output
"""

import argparse
import json
import math
import random
import sys
import time
import functools
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import predictor

# ==============================================================================
# WM 2026 GROUP DATA (all 48 teams confirmed)
# ==============================================================================

GROUPS = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Canada", "Bosnia", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["USA", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Host teams get home advantage in their group matches
HOST_TEAMS = {"Mexico", "Canada", "USA"}

# ==============================================================================
# STADIUM VENUES & ELEVATION DATA (FIFA World Cup 2026)
# ==============================================================================
# Only stadiums >1000m altitude have meaningful performance impact.
# Source: FIFA match schedule, June 2026 confirmed assignments.

STADIUMS = {
    # Mexico — altitude matters!
    "Mexico City":  {"elevation": 2240, "name": "Estadio Azteca"},
    "Guadalajara":  {"elevation": 1566, "name": "Estadio Akron"},
    "Monterrey":    {"elevation":  540, "name": "Estadio BBVA"},
    # USA — all near sea level
    "New Jersey":   {"elevation":    5, "name": "MetLife Stadium"},
    "Dallas":       {"elevation":  131, "name": "AT&T Stadium"},
    "Los Angeles":  {"elevation":   30, "name": "SoFi Stadium"},
    "Miami":        {"elevation":    2, "name": "Hard Rock Stadium"},
    "Seattle":      {"elevation":   56, "name": "Lumen Field"},
    "Boston":       {"elevation":   10, "name": "Gillette Stadium"},
    "Houston":      {"elevation":   15, "name": "NRG Stadium"},
    "Atlanta":      {"elevation":  320, "name": "Mercedes-Benz Stadium"},
    "Philadelphia": {"elevation":   12, "name": "Lincoln Financial Field"},
    "San Francisco":{"elevation":    3, "name": "Levi's Stadium"},
    "Kansas City":  {"elevation":  247, "name": "Arrowhead Stadium"},
    # Canada — near sea level
    "Toronto":      {"elevation":   76, "name": "BMO Field"},
    "Vancouver":    {"elevation":    3, "name": "BC Place"},
}

# Specific match → venue assignments for GROUP matches with altitude > 1000m
# Only these matches need altitude correction (all others are < 1000m → factor = 1.0)
# Format: (team_a, team_b) → city name (order-independent lookup)
HIGH_ALTITUDE_MATCHES = {
    # Mexico City (2240m) — Group A and K matches
    ("Mexico", "South Africa"):     "Mexico City",   # Jun 11 — Opening Match
    ("Czechia", "Mexico"):          "Mexico City",   # Jun 24
    ("Uzbekistan", "Colombia"):     "Mexico City",   # Jun 23 — Group K
    # Guadalajara (1566m) — Group A, K, and H matches
    ("South Korea", "Czechia"):     "Guadalajara",   # Jun 11
    ("Mexico", "South Korea"):      "Guadalajara",   # Jun 18
    ("Colombia", "DR Congo"):       "Guadalajara",   # Jun 23
    ("Uruguay", "Spain"):           "Guadalajara",   # Jun 26 (Group H)
}

# Altitude acclimatization days per team
# Mexico = 30+ (lives at altitude), CONCACAF neighbors some exposure
# European/Asian/African teams = 0 (no altitude exposure assumed)
# Teams can gain partial acclimatization from pre-tournament training camps
ALTITUDE_ACCLIMATIZATION = {
    "Mexico":       30,    # Lives at altitude, fully adapted
    "Ecuador":      14,    # Quito at 2850m, but team in camp by June
    "Colombia":     10,    # Bogotá at 2640m, partial adaptation
    "Bolivia":       7,    # Not qualified, but kept for reference
    "Costa Rica":    3,    # San José at 1170m, minimal
    "Paraguay":      2,    # Asunción 43m, but some camp time
    "USA":           5,    # Home team, some camp at altitude sites
    "Canada":        3,    # Some camp time near Mexico
    # All other teams default to 0 (no acclimatization)
}

def _get_match_elevation(team_a: str, team_b: str) -> tuple:
    """Return (elevation, accl_days_a, accl_days_b) for a match.
    Only applies altitude if the match is at a high-altitude venue."""
    # Check both orderings
    city = HIGH_ALTITUDE_MATCHES.get((team_a, team_b))
    if city is None:
        city = HIGH_ALTITUDE_MATCHES.get((team_b, team_a))
    
    if city is None:
        return 0.0, 0.0, 0.0  # Not a high-altitude match
    
    elevation = STADIUMS[city]["elevation"]
    accl_a = float(ALTITUDE_ACCLIMATIZATION.get(team_a, 0))
    accl_b = float(ALTITUDE_ACCLIMATIZATION.get(team_b, 0))
    
    return float(elevation), accl_a, accl_b

# ==============================================================================
# INJURY-BASED ELO CORRECTIONS (Stand: 22. Juni 2026, after MD2 Groups A–G)
# ==============================================================================
# Source: Verified via ESPN injuries tracker, Yahoo/CBC/UPI squad reports, FIFA/ESPN match reports.
# MD2: Mexico (Montes) + South Africa (Sithole/Zwane) MD2 suspensions SERVED — reverted.
# Canada's Ismaël Koné OUT for the tournament (tibia+fibula fracture vs Qatar);
#      Qatar's Madibo + Homam Ahmed both sent off vs Canada -> [SUSPENSION MD3].
# 22 Jun: Belgium's Jeremy Doku OUT with a respiratory infection — missed MD2 (Iran 0:0),
#      doubtful for MD3 (operator-confirmed). Surfaced via dropped-from-squad lineup scan.
# Negative values = weaker due to injuries + form crisis
# Suspension entries are flagged [SUSPENSION MDx] — REVERT after the team plays that matchday.
INJURY_ELO_ADJUSTMENTS = {
    "Netherlands": -42,   # Xavi Simons (ACL) OUT, de Ligt (back) OUT, Timber definitively OUT (replaced by Geertruida), Verbruggen (keeper) injured in friendly.
    "Brazil":      -38,   # Rodrygo (ACL/meniscus) OUT, Militão (hamstring surgery) OUT, Estevão OUT. Neymar (grade-2 calf tear) CONFIRMED OUT of opener + MD2 — Ancelotti targets MD3 vs Haiti (Jun 20); held 1-1 by Morocco.
    "Japan":       -32,   # Mitoma (hamstring) OUT of squad, Kubo doubtful, captain Wataru Endo struggling with foot injury.
    "USA":         -18,   # Richards back. Cardoso (ankle) still OUT. Pulisic (calf knock vs Paraguay) day-to-day — expected to feature vs Australia MD2, possibly off the bench [monitor T-45 XI].
    "Mexico":       -5,   # WAS -10: Montes MD2 suspension SERVED (Mexico won 1-0 vs South Korea without him), back for MD3. Malagón (Achilles) still OUT.
    "Argentina":   -12,   # WAS -15: Messi fit again (20' + penalty vs Iceland, full training). Romero (MCL), Foyth, Panichelli, Balerdi still OUT.
    "France":       -8,   # WAS -14: full first-choice XI available — started + won 3-1 vs Senegal (Mbappé x2; Saliba/Koundé/Tchouaméni/Dembélé all played). Only Ekitike (Achilles) + Kamara OUT (squad depth).
    "England":     -12,   # White (knee) OUT, Branthwaite (thigh) OUT, Grealish (foot) OUT, Saka managing Achilles workload.
    "Canada":       -8,   # WAS -15: Davies fit & AVAILABLE (rested vs Qatar for continuity, starts MD3). NEW: Ismaël Koné OUT for the tournament (tibia+fibula fracture vs Qatar). Flores (ACL) OUT, Bombito (tibia). Won 6-0 vs Qatar.
    "Uruguay":     -10,   # de Arrascaeta (calf tear) group doubt, Ronald Araújo (calf) injured in training, Cáceres (concussion).
    "Belgium":     -14,   # 22 Jun: + Doku (respiratory infection) OUT, missed MD2. De Bruyne recovering, Lukaku injury-hit season; Debast (hamstring) back for MD3 after a 2-match absence (partial offset).
    "Spain":        -3,   # WAS -8: Yamal, Nico Williams, Dani Olmo all came off the bench vs Cape Verde (Jun 15) — fit/available going forward (minutes-managed). Only Fermín López (metatarsal), Barrenetxea still OUT.
    "Bosnia":       -6,   # Džeko (shoulder, 40) BENCH-only for the opener per official XI (Lukić starts with Demirović), Tabaković (metatarsal) bench, Šunjić (muscle) bench; 3rd GK Hadžikić withdrew (Jurkas in).
    "Portugal":     -5,   # Rúben Dias missed MD1 injured (unclear duration — monitor). Ronaldo fit (started vs DR Congo). Mateus Nunes health issues.
    "Germany":      -5,   # Gnabry (adductor) OUT, Karl (thigh muscle tear) OUT — Ouédraogo called up.
    "Croatia":      -5,   # Modrić cheekbone fracture (playing with mask).
    # 25 Jun: Qatar -8 [SUSPENSION MD3] REMOVED — Madibo + Homam Ahmed served their bans in
    #         Bosnia-Qatar (3:1); Qatar eliminated, no further fixtures. Entry retired per convention.
}

# ==============================================================================
# TRANSFERMARKT SQUAD VALUE & FORM (Stand: Juni 2026)
# ==============================================================================
# value_m: Squad total market value in millions EUR (Transfermarkt, June 2026)
# change_pct: Value change since last Transfermarkt update (~Dec 2025 → Jun 2026)
#   Positive = players appreciated (strong club season → good form)
#   Negative = players depreciated (poor season, aging stars, injuries)
# Sources: transfermarkt.de/com, June 2026 pre-WC update

SQUAD_MARKET_VALUES = {
    # Tier 1: €900M+ (WM-Favoriten)
    "France":       {"value_m": 1550, "change_pct":  1.5},  # xG 0.88 vs CIV 1.31 — genuinely outplayed. Form DOWN.
    "England":      {"value_m": 1370, "change_pct":  0.5},  # xG 1.86 vs URU (unlucky); but 0.89 vs JPN (poor). Mixed.
    "Spain":        {"value_m": 1220, "change_pct":  7.0},  # xG 1.36 vs Iraq 0.15! DOMINANT. 1-1 = pure Pech.
    "Portugal":     {"value_m": 1010, "change_pct":  2.5},  # Stable post-Ronaldo transition
    "Germany":      {"value_m":  982, "change_pct":  5.0},  # 4-0 Finland xG 2.78! Wirtz+Musiala fire. HOT.
    "Brazil":       {"value_m":  943, "change_pct": -4.0},  # Rodrygo ACL OUT, no Neymar in squad
    # Tier 2: €500M–900M
    "Netherlands":  {"value_m":  814, "change_pct": -3.0},  # Simons ACL OUT + de Ligt OUT
    "Argentina":    {"value_m":  800, "change_pct":  2.5},  # Strong form, Messi managed/fit
    "Norway":       {"value_m":  592, "change_pct":  3.0},  # Haaland valuation anchoring
    "Belgium":      {"value_m":  551, "change_pct": -8.5},  # Golden generation aging hard
    "Ivory Coast":  {"value_m":  522, "change_pct": 12.0},  # 🔥 BEAT FRANCE 2-1 (Jun 4)! Peak momentum
    "Morocco":      {"value_m":  490, "change_pct":  6.0},  # Continued post-2022 growth
    "Senegal":      {"value_m":  478, "change_pct":  2.0},  # Strong African contingent
    "Turkey":       {"value_m":  474, "change_pct":  7.0},  # Yildiz/Güler breakout + Elo surge +116
    # Tier 3: €200M–500M
    "Denmark":      {"value_m":  420, "change_pct":  1.0},  # Stable
    "Croatia":      {"value_m":  388, "change_pct": -6.0},  # Modrić 40 + cheekbone fracture, aging midfield
    "USA":          {"value_m":  386, "change_pct":  5.0},  # Pulisic solid; but injuries to Cardoso/Richards
    "Ecuador":      {"value_m":  376, "change_pct": 10.0},  # System-level re-pricing (Pacho €80M, Hincapié €50M)
    "Sweden":       {"value_m":  350, "change_pct": -2.0},
    "Switzerland":  {"value_m":  333, "change_pct": -1.0},  # Xhaka aging
    "Colombia":     {"value_m":  298, "change_pct":  4.2},  # Young squad rising
    "Japan":        {"value_m":  281, "change_pct":  5.5},  # European-based core thriving
    "Austria":      {"value_m":  272, "change_pct":  3.5},  # Bundesliga contingent
    "Algeria":      {"value_m":  257, "change_pct":  0.5},  
    "Ghana":        {"value_m":  238, "change_pct": -4.0},  # Squad rebuilding
    "Canada":       {"value_m":  204, "change_pct":  7.0},  # David/Davies peak values
    "Scotland":     {"value_m":  200, "change_pct":  1.0},
    "Cameroon":     {"value_m":  197, "change_pct": -2.0},  
    "Mexico":       {"value_m":  194, "change_pct":  0.5},  # Liga MX-heavy, stable
    "Czechia":      {"value_m":  192, "change_pct":  1.0},  
    "Nigeria":      {"value_m":  160, "change_pct":  3.0},  # Value varies by call-up
    "Egypt":        {"value_m":  160, "change_pct":  1.0},
    "Paraguay":     {"value_m":  154, "change_pct":  3.0},
    "Uruguay":      {"value_m":  480, "change_pct":  4.0},  # Bielsa boost, Valverde peaks
    # Tier 4: <€200M
    "South Korea":  {"value_m":  142, "change_pct":  1.5},  # Son still anchoring
    "DR Congo":     {"value_m":  142, "change_pct":  4.0},  # AFCON run boosted
    "Bosnia":       {"value_m":  126, "change_pct": -1.0},  # Džeko retiring
    "Australia":    {"value_m":   78, "change_pct":  2.0},  
    "Tunisia":      {"value_m":   68, "change_pct":  0.5},  
    "Cape Verde":   {"value_m":   56, "change_pct":  2.0},  # WC debutant
    "Haiti":        {"value_m":   56, "change_pct":  3.0},  # Isidor/Bellegarde valued
    "Uzbekistan":   {"value_m":   48, "change_pct":  3.0},  # WC debutant
    "South Africa": {"value_m":   45, "change_pct":  3.0},  
    "Saudi Arabia": {"value_m":   41, "change_pct": -5.0},  # SPL imports don't lift NT
    "New Zealand":  {"value_m":   40, "change_pct":  0.0},
    "Iran":         {"value_m":   34, "change_pct":  0.0},  # Domestic-heavy
    "Panama":       {"value_m":   35, "change_pct":  1.0},  
    "Costa Rica":   {"value_m":   29, "change_pct": -2.0},  
    "Curaçao":      {"value_m":   26, "change_pct":  1.0},  # WC debutant
    "Iraq":         {"value_m":   21, "change_pct":  2.0},  
    "Qatar":        {"value_m":   20, "change_pct": -5.0},  # Lowest returning 2022 host
    "Jordan":       {"value_m":   18, "change_pct":  5.0},  # Asian Cup run, WC debutant
    "Jamaica":      {"value_m":    9, "change_pct":  2.0},  # Lowest valued squad (avg age 23.1)
}


# ==============================================================================
# xG/xGA OFFENSIVE-DEFENSIVE STRENGTH SPLIT
# ==============================================================================
# Separates team quality into attacking (xG) and defensive (xGA) components.
# Without this, Elo gives ONE number per team → a defensive team like Uruguay
# and an offensive team like Belgium are modeled the same if they have equal Elo.
#
# attack_str: Relative attacking quality (1.0 = average WC team)
#   Derived from: goals scored/game + xG/game in recent competitive matches
#   Values >1.0 = above average attack, <1.0 = below average
#
# defend_str: Relative defensive quality (1.0 = average WC team) 
#   Derived from: goals conceded/game + xGA/game in recent competitive matches
#   Values <1.0 = GOOD defense (concedes less), >1.0 = weak defense
#
# How it works in the model:
#   λ_a (team A expected goals) = base_λ_a × attack_str_a × defend_str_b
#   λ_b (team B expected goals) = base_λ_b × attack_str_b × defend_str_a
#
# This means: strong attack vs weak defense → more goals (both multiply up)
#             weak attack vs strong defense → fewer goals
#
# Sources: FotMob, WhoScored, xGscore.io — goals scored/conceded per game
# in competitive matches 2024-2026 (WCQ, Nations League, Continental cups)
# Normalized to average = 1.0
#
# IMPORTANT: These are RELATIVE to WC average, not absolute xG values.
# A team with attack_str=1.3 scores ~30% more than the WC average team.

XG_STRENGTH = {
    # Format: "Team": {"attack_str": x.xx, "defend_str": x.xx}
    # attack_str > 1.0 = strong attack
    # defend_str < 1.0 = strong defense (concedes fewer)
    #
    # CALIBRATION NOTES (Jun 6, 2026):
    # - Values are OPPOSITION-ADJUSTED: raw G/g and GA/g corrected for
    #   quality of opponents faced (WCQ vs friendlies vs top teams)
    # - SQUAD TURNOVER: penalized if key players from peak period are
    #   now injured, retired, or aging past prime
    # - Argentina: raw 0.2 GA/g was vs Honduras/Paraguay/Bolivia.
    #   Against top-20 opposition, GA/g ≈ 0.6. Plus Romero MCL OUT.
    # - Germany: 3.6 G/g includes 4-0 Finland, 7-0 Bosnia. vs top-20: ~2.0.
    # - England: 0.4 GA/g is real (conceded 0-1 goals in every match)
    #   but attack xG vs Japan was 0.89 — genuinely limited.
    
    # Tier 1: Elite both ends (adjusted for opponent quality + squad health)
    "Spain":        {"attack_str": 1.25, "defend_str": 0.60},  # xG 1.36 vs Iraq 0.15 = real. Young squad intact.
    "Argentina":    {"attack_str": 1.15, "defend_str": 0.65},  # WAS 0.45 defend — corrected: Romero OUT, weak oppo inflated stats
    "England":      {"attack_str": 1.05, "defend_str": 0.55},  # xG 0.89 vs JPN = attack limited. Defense genuinely elite.
    
    # Missing teams
    "Egypt":        {"attack_str": 1.00, "defend_str": 0.90},
    "New Zealand":  {"attack_str": 0.85, "defend_str": 1.10},
    "Scotland":     {"attack_str": 0.95, "defend_str": 0.90},

    
    # Tier 2: Strong attack, decent defense
    "France":       {"attack_str": 1.30, "defend_str": 0.80},  # Attack real (Mbappé). Defend 0.75→0.80: lost 1-2 to CIV, leaky.
    "Germany":      {"attack_str": 1.25, "defend_str": 0.85},  # WAS 1.40 attack — corrected: 4-0 Finland ≠ WC level. vs USA/top: ~2.0 G/g
    "Portugal":     {"attack_str": 1.15, "defend_str": 0.75},  # Ronaldo 38y. Attack declining. Defense organized.
    
    # Tier 3: Good but flawed
    "Brazil":       {"attack_str": 1.05, "defend_str": 0.80},  # Rodrygo OUT + no Neymar = attack weakened significantly
    "Netherlands":  {"attack_str": 1.05, "defend_str": 0.80},  # Simons OUT = creative loss. Not the same team.
    "Colombia":     {"attack_str": 1.10, "defend_str": 0.80},  # Balanced, young. xG data consistent.
    "Ecuador":      {"attack_str": 1.05, "defend_str": 0.75},  # Tight defense real (CONMEBOL QF). Attack modest vs top teams.
    
    # Tier 4: One strength dominant
    "Norway":       {"attack_str": 1.30, "defend_str": 1.05},  # Haaland IS the attack. Defense genuinely poor.
    "Belgium":      {"attack_str": 1.10, "defend_str": 1.05},  # Golden gen aging: Lukaku 33, KDB 35. Both ends declining.
    "Turkey":       {"attack_str": 1.10, "defend_str": 0.90},  # Yildiz 21y, Güler 21y — exciting but WC inexperience.
    "Canada":       {"attack_str": 1.05, "defend_str": 0.95},  # David quality, but team defense suspect.
    
    # Tier 5: Defensive identity (these teams WILL park the bus)
    "Croatia":      {"attack_str": 0.90, "defend_str": 0.70},  # Modrić 40y+fracture. Attack much weaker than 2022. Defense still good.
    "Uruguay":      {"attack_str": 0.85, "defend_str": 0.60},  # Always defensive. Suárez retired. Núñez inconsistent.
    "Morocco":      {"attack_str": 0.90, "defend_str": 0.70},  # 2022 defense real — Hakimi, Aguerd still there. But Amrabat aging.
    "Iran":         {"attack_str": 0.80, "defend_str": 0.70},  # Classic: sit deep, counter. Queiroz-era DNA.
    "Tunisia":      {"attack_str": 0.80, "defend_str": 0.75},  # Same mold: compact, hard to break.
    "Costa Rica":   {"attack_str": 0.75, "defend_str": 0.80},  # 2014/2022: always defended. Aging squad.
    
    # Tier 6: Balanced mid-table
    "Switzerland":  {"attack_str": 0.95, "defend_str": 0.80},
    "Denmark":      {"attack_str": 1.00, "defend_str": 0.80},
    "Sweden":       {"attack_str": 1.05, "defend_str": 0.90},
    "Austria":      {"attack_str": 1.05, "defend_str": 0.85},  # Rangnick pressing but drops deep vs top teams
    "USA":          {"attack_str": 0.95, "defend_str": 0.85},  # Home advantage will help separately
    "Senegal":      {"attack_str": 0.95, "defend_str": 0.80},
    "Japan":        {"attack_str": 1.00, "defend_str": 0.85},  # Mitoma OUT = reduced threat
    "Ivory Coast":  {"attack_str": 1.05, "defend_str": 0.85},  # Beat France but one match ≠ consistency
    "Mexico":       {"attack_str": 0.90, "defend_str": 0.85},
    "Scotland":     {"attack_str": 0.95, "defend_str": 0.85},
    "South Korea":  {"attack_str": 0.95, "defend_str": 0.90},  # Son 33y — still good but slowing
    "Algeria":      {"attack_str": 0.90, "defend_str": 0.85},
    "Nigeria":      {"attack_str": 0.95, "defend_str": 0.90},
    "Egypt":        {"attack_str": 0.95, "defend_str": 0.80},
    "Cameroon":     {"attack_str": 0.95, "defend_str": 0.95},
    "Ghana":        {"attack_str": 0.85, "defend_str": 1.00},
    "Australia":    {"attack_str": 0.85, "defend_str": 0.95},
    "Paraguay":     {"attack_str": 0.90, "defend_str": 0.85},  # Enciso/Almirón give some threat
    "Czechia":      {"attack_str": 0.90, "defend_str": 0.85},
    "Bosnia":       {"attack_str": 0.85, "defend_str": 0.95},  # Džeko retired.
    "DR Congo":     {"attack_str": 0.85, "defend_str": 0.95},
    
    # Tier 7: WC debutants / weaker (will adapt defensively)
    "Saudi Arabia": {"attack_str": 0.80, "defend_str": 0.95},  # 2022: beat Argentina parking bus. Will try again.
    "Uzbekistan":   {"attack_str": 0.80, "defend_str": 0.95},
    "Cape Verde":   {"attack_str": 0.80, "defend_str": 0.95},
    "Haiti":        {"attack_str": 0.80, "defend_str": 1.05},
    "South Africa": {"attack_str": 0.80, "defend_str": 0.95},
    "Panama":       {"attack_str": 0.75, "defend_str": 0.90},
    "Curaçao":      {"attack_str": 0.75, "defend_str": 1.05},
    "Iraq":         {"attack_str": 0.75, "defend_str": 1.00},
    "Qatar":        {"attack_str": 0.70, "defend_str": 1.00},
    "Jordan":       {"attack_str": 0.75, "defend_str": 0.90},
    "New Zealand":  {"attack_str": 0.80, "defend_str": 1.00},
    "Jamaica":      {"attack_str": 0.80, "defend_str": 1.05},
}

def compute_xg_form_multipliers(team_a: str, team_b: str) -> Tuple[float, float]:
    """
    Compute matchup-specific lambda multipliers from xG/xGA strength data,
    with TACTICAL DAMPENING for mismatched games.
    
    Three adjustments beyond raw xG/xGA:
    
    1. BASE: form_a = attack_a × defend_b (matchup-dependent)
    
    2. TACTICAL DAMPENING: When Elo gap > 150, the underdog parks the bus.
       Both form multipliers get pulled toward 1.0 (= fewer goals for both).
       Historical WC data: mismatches average ~2.1 total goals vs ~2.7 in even.
       Saudi Arabia beat Argentina 2-1 in 2022 by sitting deep + countering.
    
    3. TOURNAMENT REGRESSION: Raw xG/xGA from qualifiers gets regressed toward
       1.0 by 25%, because WC opponents are stronger than qualifying opponents.
       A team that scored 3.6 G/g vs Finland won't do that vs Spain.
    """
    import predictor as pred
    
    xg_a = XG_STRENGTH.get(team_a, {"attack_str": 1.0, "defend_str": 1.0})
    xg_b = XG_STRENGTH.get(team_b, {"attack_str": 1.0, "defend_str": 1.0})
    
    # Step 1: Raw matchup multipliers
    form_a = xg_a["attack_str"] * xg_b["defend_str"]
    form_b = xg_b["attack_str"] * xg_a["defend_str"]
    
    # Step 2: Tactical dampening for mismatched games
    # When there's a big Elo gap, the weaker team sits deep → game compresses
    # toward fewer goals. Both teams score LESS than raw xG suggests.
    elo_a = pred.WORLD_CUP_2026_TEAMS.get(team_a, {}).get("elo", 1700)
    elo_b = pred.WORLD_CUP_2026_TEAMS.get(team_b, {}).get("elo", 1700)
    elo_gap = abs(elo_a - elo_b)
    
    if elo_gap > 150:
        # ASYMMETRIC tactical dampening:
        # - Favorite: form pulled DOWN toward 1.0 (bus parking blocks them)
        # - Underdog: form pulled DOWN toward own raw value (bus = fewer counters too)
        # This is asymmetric because bus parking reduces BOTH teams' goals,
        # not just the favorite's. The old symmetric pull was wrong:
        # it buffed Qatar's counter-attack unrealistically.
        dampen = min(0.20, (elo_gap - 150) / 1000.0)
        
        # Determine who is favorite vs underdog
        if elo_a >= elo_b:
            # team_a is favorite: their attack gets dampened (bus blocks them)
            form_a = form_a * (1.0 - dampen) + 1.0 * dampen
            # team_b is underdog: their attack gets slightly dampened too
            # (sitting deep = fewer counter-attack chances)
            form_b = form_b * (1.0 - dampen * 0.5) + xg_b["attack_str"] * dampen * 0.5
        else:
            form_b = form_b * (1.0 - dampen) + 1.0 * dampen
            form_a = form_a * (1.0 - dampen * 0.5) + xg_a["attack_str"] * dampen * 0.5
    
    # Step 3: Clamp to reasonable range
    # Floor 0.65 (not 0.60): two defensive teams shouldn't produce <1.7 total goals
    form_a = max(0.65, min(1.40, form_a))
    form_b = max(0.65, min(1.40, form_b))
    
    return form_a, form_b
# ==============================================================================
# STAR STRIKER CONCENTRATION (DATA-BACKED)
# ==============================================================================
# For Golden Boot prediction: what fraction of team goals does the #1 striker
# typically score? Calculated from ACTUAL NT career statistics.
#
# Method: star_goals / team_total_goals over same career period.
# Then adjusted for WC context: tournament concentration is typically
# HIGHER than career avg (fewer games, star plays every minute).
# WC adjustment: career_pct × 1.15 for non-PK takers, × 1.20 for PK takers.
#
# Sources (verified June 5, 2026):
#   - Mbappé: 56 goals / ~140 FRA goals (2018-2026) = 0.40. WC2022: 8/16 = 0.50
#   - Kane: 78 goals / ~200 ENG goals (2015-2026) = 0.39. WC2018: 6/12 = 0.50
#   - Haaland: 55 goals / ~120 NOR goals (2019-2026) = 0.46. 16g in 8 WCQ matches!
#   - Ronaldo: 143 goals / ~340 POR goals (2003-2026) = 0.42. PK taker.
#   - Lautaro: 36 goals / ~160 ARG goals (2019-2026) = 0.23. Messi still scores too.
#   - Son: 56 goals / ~140 KOR goals (2014-2026) = 0.40.
#   - Valencia: 49 goals / ~130 ECU goals (2012-2026) = 0.38.
#   - Morata: 37 goals / ~200 ESP goals (2014-2026) = 0.19. Merino/Oyarzabal 6 each in 2025.
STRIKER_CONCENTRATION = {
    # Tier 1: Dominant focal strikers (>0.40 career concentration + PK)
    "Norway":       {"striker": "Haaland",    "concentration": 0.50, "penalty": True},   # 55/120=0.46 career, WCQ 16/~35≈0.46, WC boost → 0.50
    "Portugal":     {"striker": "Ronaldo",    "concentration": 0.45, "penalty": True},   # 143/340=0.42, PK taker, WC boost → 0.45
    "South Korea":  {"striker": "Son",        "concentration": 0.43, "penalty": True},   # 56/140=0.40, PK taker, focal point, WC boost → 0.43
    "France":       {"striker": "Mbappé",     "concentration": 0.43, "penalty": True},   # 56/140=0.40 career, WC2022 was 0.50, avg → 0.43
    "England":      {"striker": "Kane",       "concentration": 0.42, "penalty": True},   # 78/200=0.39, PK taker, WC2018 was 0.50, avg → 0.42
    # Tier 2: Strong focal strikers (0.35-0.40)
    "Ecuador":      {"striker": "Valencia",   "concentration": 0.40, "penalty": True},   # 49/130=0.38, PK taker, all-time NT top scorer
    "Canada":       {"striker": "David",      "concentration": 0.38, "penalty": True},   # Top scorer, PK taker, lone #9
    "Uruguay":      {"striker": "Núñez",      "concentration": 0.37, "penalty": True},   # PK taker, but Valverde/Suárez also score
    "Belgium":      {"striker": "Lukaku",     "concentration": 0.36, "penalty": True},   # All-time Belgian top scorer, but aging
    "Iran":         {"striker": "Azmoun",     "concentration": 0.36, "penalty": True},   # Clear focal point
    "Mexico":       {"striker": "Giménez",    "concentration": 0.35, "penalty": True},   # Feyenoord star, PK taker
    "Denmark":      {"striker": "Højlund",    "concentration": 0.34, "penalty": True},   # Emerging, took over from Dolberg
    "Morocco":      {"striker": "En-Nesyri",  "concentration": 0.33, "penalty": True},   # Fenerbahçe, PK taker
    # Tier 3: Moderate concentration (0.25-0.35)
    "Croatia":      {"striker": "Kramarić",   "concentration": 0.30, "penalty": True},   # Modrić/Brozović also contribute
    "Argentina":    {"striker": "Lautaro",    "concentration": 0.28, "penalty": False},  # 36/160=0.23 career. Messi still scores + takes PKs.
    "Netherlands":  {"striker": "Brobbey",    "concentration": 0.28, "penalty": False},  # Depay injured, Brobbey new focal. Low sample.
    "Turkey":       {"striker": "Yildiz",     "concentration": 0.28, "penalty": False},  # Young, goals spread with Güler/Aktürkoğlu
    "Senegal":      {"striker": "Dia",        "concentration": 0.30, "penalty": True},   # Lazio, clear focal striker
    "Australia":    {"striker": "Duke",       "concentration": 0.30, "penalty": True},
    "Austria":      {"striker": "Arnautović", "concentration": 0.28, "penalty": True},   # 37 years old, may not start every game
    "Colombia":     {"striker": "Córdoba",    "concentration": 0.28, "penalty": True},   # Young talent, but distributed squad
    "Japan":        {"striker": "Ueda",       "concentration": 0.25, "penalty": False},  # Goals very spread: Mitoma(out), Kubo, Doan
    "Switzerland":  {"striker": "Embolo",     "concentration": 0.25, "penalty": False},  # Monaco, but goals spread across squad
    "USA":          {"striker": "Balogun",    "concentration": 0.25, "penalty": False},  # Young, Pulisic also scores a lot
    "Paraguay":     {"striker": "Enciso",     "concentration": 0.25, "penalty": False},  # Very young (21), limited NT sample
    # Tier 4: Very distributed scoring (<0.25)
    "Germany":      {"striker": "Havertz",    "concentration": 0.22, "penalty": False},  # 4-0 vs Finland: Undav(2), Wirtz, Musiala. All different.
    "Spain":        {"striker": "Morata",     "concentration": 0.20, "penalty": False},  # 37/200=0.19. 2025: Merino/Oyarzabal 6 each, Morata 2. Most distributed.
    "Brazil":       {"striker": "Endrick",    "concentration": 0.22, "penalty": False},  # Rodrygo ACL out; Vinícius/Raphinha/Endrick rotate
}
# Default for unlisted teams: 0.22 concentration (slightly below avg)
STRIKER_CONCENTRATION_DEFAULT = 0.22


def compute_squad_elo_adjustments(squad_values: dict = None) -> dict:
    """
    Compute Elo adjustments based on Transfermarkt squad values and form.
    
    Logic:
    1. Squad Value → Elo (max ±40):
       log(value_m) normalized to median ~200M, scaled to ±40 Elo
       This captures squad quality that Elo may lag behind on.
    
    2. Form (Value Change %) → Elo (max ±20):
       Positive change = good season = positive form
       Capped at ±20 Elo to avoid over-reacting
    
    Combined: max ±60 Elo adjustment per team.
    """
    import math
    if squad_values is None:
        squad_values = SQUAD_MARKET_VALUES
    
    if not squad_values:
        return {}
    
    # Compute median value for normalization
    values = [v["value_m"] for v in squad_values.values()]
    values.sort()
    median_value = values[len(values) // 2]
    
    adjustments = {}
    for team, data in squad_values.items():
        value_m = data["value_m"]
        change_pct = data.get("change_pct", 0.0)
        
        # 1. Squad value → Elo modifier (±40 max)
        # log-ratio to median, scaled
        if value_m > 0 and median_value > 0:
            log_ratio = math.log(value_m / median_value) / math.log(10)  # log10 ratio
            # Clamp to [-1, +1] range, scale to ±40
            value_elo = max(-40, min(40, log_ratio * 40))
        else:
            value_elo = 0
        
        # 2. Form (change %) → Elo modifier (±20 max)
        # 10% increase = +20 Elo, 10% decrease = -20 Elo, linear
        form_elo = max(-20, min(20, change_pct * 2.0))
        
        total_adj = round(value_elo + form_elo)
        if total_adj != 0:
            adjustments[team] = total_adj
    
    return adjustments

# ==============================================================================
# R32 BRACKET STRUCTURE
# ==============================================================================
# The R32 bracket pairs are determined by FIFA regulations.
# Source: https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage
#
# R32 Match numbering:
#   M73: 2A vs 2B          M74: 1C vs 2F          M75: 1E vs 3rd(ABCDF)
#   M76: 1F vs 2C          M77: 1I vs 3rd(CDFGH)  M78: 2E vs 2I
#   M79: 1A vs 3rd(CEFHI)  M80: 1L vs 3rd(EHIJK)
#   M81: 1G vs 3rd(AEHIJ)  M82: 1D vs 3rd(BEFIJ)
#   M83: 1H vs 2J          M84: 2K vs 2L
#   M85: 1B vs 3rd(EFGIJ)  M86: 1J vs 2H
#   M87: 2D vs 2G          M88: 1K vs 3rd(DEIJL)

# Fixed R32 pairings (no third-place uncertainty):
# M73: Runner-up A vs Runner-up B
# M74: Winner C vs Runner-up F
# M76: Winner F vs Runner-up C
# M78: Runner-up E vs Runner-up I
# M83: Winner H vs Runner-up J
# M84: Runner-up K vs Runner-up L
# M86: Winner J vs Runner-up H
# M87: Runner-up D vs Runner-up G

# R32 pairings with 3rd-place slots:
# M75: Winner E vs 3rd(A/B/C/D/F)
# M77: Winner I vs 3rd(C/D/F/G/H)
# M79: Winner A vs 3rd(C/E/F/H/I)
# M80: Winner L vs 3rd(E/H/I/J/K)
# M81: Winner G vs 3rd(A/E/H/I/J)
# M82: Winner D vs 3rd(B/E/F/I/J)
# M85: Winner B vs 3rd(E/F/G/I/J)
# M88: Winner K vs 3rd(D/E/I/J/L)

# Third-place possible source groups for each slot:
THIRD_PLACE_POOLS = {
    "M75": ["A", "B", "C", "D", "F"],       # W_E plays 3rd from one of these
    "M77": ["C", "D", "F", "G", "H"],       # W_I plays 3rd from one of these
    "M79": ["C", "E", "F", "H", "I"],       # W_A plays 3rd from one of these
    "M80": ["E", "H", "I", "J", "K"],       # W_L plays 3rd from one of these
    "M81": ["A", "E", "H", "I", "J"],       # W_G plays 3rd from one of these
    "M82": ["B", "E", "F", "I", "J"],       # W_D plays 3rd from one of these
    "M85": ["E", "F", "G", "I", "J"],       # W_B plays 3rd from one of these
    "M88": ["D", "E", "I", "J", "L"],       # W_K plays 3rd from one of these
}

# R32 matches in official order (M73-M88), using string identifiers:
# "W_X" = Winner of Group X, "R_X" = Runner-up of Group X,
# "3_Mnn" = 3rd-place team assigned to match Mnn
R32_BRACKET = [
    ("R_A", "R_B"),      # M73
    ("W_C", "R_F"),      # M74
    ("W_E", "3_M75"),    # M75
    ("W_F", "R_C"),      # M76
    ("W_I", "3_M77"),    # M77
    ("R_E", "R_I"),      # M78
    ("W_A", "3_M79"),    # M79
    ("W_L", "3_M80"),    # M80
    ("W_G", "3_M81"),    # M81
    ("W_D", "3_M82"),    # M82
    ("W_H", "R_J"),      # M83
    ("R_K", "R_L"),      # M84
    ("W_B", "3_M85"),    # M85
    ("W_J", "R_H"),      # M86
    ("R_D", "R_G"),      # M87
    ("W_K", "3_M88"),    # M88
]

# R16 pairings — which R32 winners play each other (0-indexed into R32_BRACKET):
# M89: W(M73) vs W(M75)  → idx 0 vs 2
# M90: W(M74) vs W(M77)  → idx 1 vs 4
# M91: W(M76) vs W(M78)  → idx 3 vs 5
# M92: W(M79) vs W(M80)  → idx 6 vs 7
# M93: W(M83) vs W(M84)  → idx 10 vs 11
# M94: W(M81) vs W(M82)  → idx 8 vs 9
# M95: W(M86) vs W(M88)  → idx 13 vs 15
# M96: W(M85) vs W(M87)  → idx 12 vs 14
R16_BRACKET = [
    (0, 2),    # M89: W(M73) vs W(M75)
    (1, 4),    # M90: W(M74) vs W(M77)
    (3, 5),    # M91: W(M76) vs W(M78)
    (6, 7),    # M92: W(M79) vs W(M80)
    (10, 11),  # M93: W(M83) vs W(M84)
    (8, 9),    # M94: W(M81) vs W(M82)
    (13, 15),  # M95: W(M86) vs W(M88)
    (12, 14),  # M96: W(M85) vs W(M87)
]

# QF pairings (winners of R16 matches):
# M97: W(M89) vs W(M90)  → idx 0 vs 1
# M98: W(M93) vs W(M94)  → idx 4 vs 5
# M99: W(M91) vs W(M92)  → idx 2 vs 3
# M100: W(M95) vs W(M96) → idx 6 vs 7
QF_BRACKET = [(0, 1), (4, 5), (2, 3), (6, 7)]

# SF pairings:
# M101: W(M97) vs W(M98) → idx 0 vs 1
# M102: W(M99) vs W(M100)→ idx 2 vs 3
SF_BRACKET = [(0, 1), (2, 3)]



def precompute_grids(host_teams: set = None, market_probs: dict = None) -> dict:
    """
    Precompute probability grids for all 72 group stage matches.
    Now injecting true chronological context (rest_days, travel_miles).
    """
    import schedule_context
    group_contexts, _ = schedule_context.get_group_match_contexts()
    
    cache = {}
    print("  📊 Precomputing 72 group match probability grids with schedule context...")
    
    for group_name, teams in GROUPS.items():
        # Matchups
        matchups = [
            (teams[0], teams[1]), (teams[2], teams[3]), # MD1 (assumed order)
            (teams[0], teams[2]), (teams[1], teams[3]), # MD2
            (teams[0], teams[3]), (teams[1], teams[2])  # MD3
        ]
        
        for pair_idx, (team_a, team_b) in enumerate(matchups):
            row = {
                "team_a": team_a,
                "team_b": team_b,
                "phase": "GROUP"
            }
            
            # Inject context
            ctx = group_contexts.get((team_a, team_b))
            if not ctx:
                ctx = group_contexts.get((team_b, team_a))
                if ctx:
                    # swap prefix
                    row["rest_days_a"] = str(ctx["rest_days_b"])
                    row["rest_days_b"] = str(ctx["rest_days_a"])
                    row["travel_miles_a"] = str(ctx["travel_miles_b"])
                    row["travel_miles_b"] = str(ctx["travel_miles_a"])
                    row["tz_crossed_a"] = str(ctx["tz_crossed_b"])
                    row["tz_crossed_b"] = str(ctx["tz_crossed_a"])
            
            if ctx and "rest_days_a" not in row:
                for k, v in ctx.items():
                    row[k] = str(v)
            
            # Inject xG/xGA matchup-specific form multipliers
            form_a, form_b = compute_xg_form_multipliers(team_a, team_b)
            row["form_a"] = str(form_a)
            row["form_b"] = str(form_b)
            
            if host_teams:
                if team_a in host_teams:
                    row["status_a"] = "True Home"
                    row["fan_pct_a"] = "0.70"
                    row["fan_pct_b"] = "0.30"
                elif team_b in host_teams:
                    row["status_b"] = "True Home"
                    row["fan_pct_a"] = "0.30"
                    row["fan_pct_b"] = "0.70"
            
            if market_probs:
                p_a = market_probs.get(team_a, None)
                p_b = market_probs.get(team_b, None)
                if p_a is not None and p_b is not None:
                    s_a = math.sqrt(max(p_a, 0.001))
                    s_b = math.sqrt(max(p_b, 0.001))
                    p_a_win_raw = s_a / (s_a + s_b)
                    p_b_win_raw = s_b / (s_a + s_b)
                    mismatch = abs(p_a_win_raw - p_b_win_raw)
                    p_draw = 0.27 * (1.0 - mismatch)
                    rem = 1.0 - p_draw
                    p_home = p_a_win_raw * rem
                    p_away = p_b_win_raw * rem
                    oh = round(1.0 / max(p_home, 0.01), 2)
                    od = round(1.0 / max(p_draw, 0.01), 2)
                    oa = round(1.0 / max(p_away, 0.01), 2)
                    row["odds_home"] = str(oh)
                    row["odds_draw"] = str(od)
                    row["odds_away"] = str(oa)
                    row["market_weight"] = "0.7"
            
            # Altitude correction for high-elevation venues
            elev, accl_a, accl_b = _get_match_elevation(team_a, team_b)
            if elev > 1000:
                row["elevation"] = str(elev)
                row["accl_days_a"] = str(accl_a)
                row["accl_days_b"] = str(accl_b)
            
            def _compute_grid(f_a, f_b):
                row_copy = row.copy()
                row_copy["form_a"] = str(f_a)
                row_copy["form_b"] = str(f_b)
                result = predictor.predict_single_match(row_copy)
                grid = result["grid"]
                flat = []
                cum_weights = []
                cumulative = 0.0
                for ga_str, inner in grid.items():
                    for gb_str, prob in inner.items():
                        p = float(prob)
                        if p > 0:
                            flat.append((int(ga_str), int(gb_str)))
                            cumulative += p
                            cum_weights.append(cumulative)
                if cumulative > 0:
                    cum_weights = [w / cumulative for w in cum_weights]
                return flat, cum_weights
            
            # MD3 (last two matchups per group): flat x0.87 trim for EVERY
            # matchday-3 game — the only validated MD3 effect
            # (validation/md3_regime_backtest.py). Replaces the unvalidated
            # conditional x0.85 *_DAMPENED variants (S11).
            if pair_idx >= 4:
                form_a *= 0.87
                form_b *= 0.87
            cache[(team_a, team_b, False)] = _compute_grid(form_a, form_b)
    
    return cache


def _get_ko_grid(team_a: str, team_b: str, phase: str,
                  host_teams: set, ko_cache: dict,
                  elevation: float = 0.0,
                  elo_a: float = None, elo_b: float = None,
                  travel_a: float = 0.0, travel_b: float = 0.0,
                  rest_a: float = 5.0, rest_b: float = 5.0) -> Tuple[list, list]:
    """Get or compute KO match grid (cached by team pair and exact Elos)."""
    # Round Elo to integers for sensible caching
    elo_a_key = int(elo_a) if elo_a is not None else None
    elo_b_key = int(elo_b) if elo_b is not None else None
    
    # Cache key includes travel and rest to ensure proper context isolation
    key = (team_a, team_b, phase, elevation, elo_a_key, elo_b_key, int(travel_a), int(travel_b), int(rest_a), int(rest_b))
    if key in ko_cache:
        return ko_cache[key]
    
    row = {
        "team_a": team_a, "team_b": team_b, "phase": phase, 
        "elevation": elevation,
        "travel_miles_a": str(travel_a), "travel_miles_b": str(travel_b),
        "rest_days_a": str(rest_a), "rest_days_b": str(rest_b)
    }
    if elo_a is not None:
        row["elo_a"] = elo_a
    if elo_b is not None:
        row["elo_b"] = elo_b
    
    # Inject xG/xGA matchup-specific form multipliers
    form_a, form_b = compute_xg_form_multipliers(team_a, team_b)
    row["form_a"] = str(form_a)
    row["form_b"] = str(form_b)
    
    if host_teams:
        if team_a in host_teams:
            row["status_a"] = "True Home"
            row["fan_pct_a"] = "0.65"
            row["fan_pct_b"] = "0.35"
        elif team_b in host_teams:
            row["status_b"] = "True Home"
            row["fan_pct_a"] = "0.35"
            row["fan_pct_b"] = "0.65"
    
    # Market odds outright translation removed for KO matches to rely on pure Elo
    
    result = predictor.predict_single_match(row)
    grid = result["grid_90"]  # Extract ONLY 90-minute grid for Golden Boot goals
    
    flat = []
    cum_weights = []
    cumulative = 0.0
    for a, inner in grid.items():
        for b, prob in inner.items():
            flat.append((int(a), int(b)))
            cumulative += float(prob)
            cum_weights.append(cumulative)
            
    if cumulative > 0:
        cum_weights = [w / cumulative for w in cum_weights]
    
    ko_cache[key] = (flat, cum_weights)
    return flat, cum_weights


def _sample_from_grid(flat: list, cum_weights: list, rng: random.Random) -> Tuple[int, int]:
    """Fast binary-search sampling from precomputed cumulative weights."""
    r = rng.random()
    # Binary search
    lo, hi = 0, len(cum_weights) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum_weights[mid] < r:
            lo = mid + 1
        else:
            hi = mid
    return flat[lo]


def simulate_group(group_name: str, teams: List[str],
                   grid_cache: dict = None,
                   rng: random.Random = None) -> List[dict]:
    """
    Simulate all 6 matches in a group using precomputed grids.
    Returns list of dicts sorted by: points, goal_diff, goals_for (descending).
    """
    standings = {}
    for team in teams:
        standings[team] = {
            "team": team, "group": group_name,
            "pts": 0, "gf": 0, "ga": 0, "gd": 0, "w": 0, "d": 0, "l": 0
        }
    
    # Matches array aligned with schedule generator
    m0v1 = (teams[0], teams[1])
    m0v2 = (teams[0], teams[2])
    m0v3 = (teams[0], teams[3])
    m1v2 = (teams[1], teams[2])
    m1v3 = (teams[1], teams[3])
    m2v3 = (teams[2], teams[3])
    
    matchdays = [
        [m0v1, m2v3], # MD1
        [m0v2, m1v3], # MD2
        [m0v3, m1v2]  # MD3
    ]
    
    match_results = {}
    
    for md_idx, matchday in enumerate(matchdays):
        # MD3: the flat x0.87 trim is baked into the precomputed grids (S11);
        # the old conditional dead-rubber detection was unvalidated and wrong
        # in the 48-team format (0 points after two games is NOT elimination).
        for team_a, team_b in matchday:
            key = (team_a, team_b, False)

            if grid_cache and key in grid_cache:
                flat, cum_weights = grid_cache[key]
                ga, gb = _sample_from_grid(flat, cum_weights, rng)
            else:
                ga, gb = 1, 0
                
            match_results[(team_a, team_b)] = (ga, gb)
            match_results[(team_b, team_a)] = (gb, ga)
            
            standings[team_a]["gf"] += ga
            standings[team_a]["ga"] += gb
            standings[team_b]["gf"] += gb
            standings[team_b]["ga"] += ga
            
            if ga > gb:
                standings[team_a]["pts"] += 3
                standings[team_a]["w"] += 1
                standings[team_b]["l"] += 1
            elif ga == gb:
                standings[team_a]["pts"] += 1
                standings[team_b]["pts"] += 1
                standings[team_a]["d"] += 1
                standings[team_b]["d"] += 1
            else:
                standings[team_b]["pts"] += 3
                standings[team_b]["w"] += 1
                standings[team_a]["l"] += 1
    
    for team in standings:
        standings[team]["gd"] = standings[team]["gf"] - standings[team]["ga"]
        # Drawing-of-lots value for final tiebreaks (S11: Elo removed — it is
        # not in any FIFA regulation and biased ties toward favourites).
        standings[team]["lot"] = rng.random() if rng is not None else 0.0
    
    import functools
    def fifa_cmp(x, y):
        # 1. Overall Points
        if x["pts"] != y["pts"]: return 1 if x["pts"] > y["pts"] else -1
        # 2. Overall Goal Difference
        if x["gd"] != y["gd"]: return 1 if x["gd"] > y["gd"] else -1
        # 3. Overall Goals For
        if x["gf"] != y["gf"]: return 1 if x["gf"] > y["gf"] else -1
        
        # 4. Head-to-Head (pairwise)
        gx, gy = match_results.get((x["team"], y["team"]), (0, 0))
        pts_x = 3 if gx > gy else (1 if gx == gy else 0)
        pts_y = 3 if gy > gx else (1 if gx == gy else 0)
        if pts_x != pts_y: return 1 if pts_x > pts_y else -1
        
        # 5. H2H GD (same as comparing goals since it's 1 match)
        if gx != gy: return 1 if gx > gy else -1
        
        # 6. Drawing of lots (S11)
        lx, ly = x.get("lot", 0.0), y.get("lot", 0.0)
        if lx != ly: return 1 if lx > ly else -1
        return 0
    
    sorted_standings = sorted(
        standings.values(),
        key=functools.cmp_to_key(fifa_cmp),
        reverse=True
    )
    
    for i, s in enumerate(sorted_standings):
        s["pos"] = i + 1
    
    return sorted_standings


# ==============================================================================
# KNOCKOUT STAGE SIMULATION
# ==============================================================================

def get_best_third_place_teams(all_group_standings: dict) -> List[str]:
    """
    Determine the 8 best third-placed teams across all 12 groups.
    
    Ranking: points, goal diff, goals for, Elo tiebreak.
    """
    thirds = []
    for group_name, standings in all_group_standings.items():
        third = standings[2]  # 0-indexed: pos 3
        third["from_group"] = group_name
        thirds.append(third)
    
    # Sort by the same criteria
    thirds.sort(
        key=lambda x: (
            x["pts"],
            x["gd"],
            x["gf"],
            x.get("lot", 0.0)   # drawing of lots (S11: Elo removed)
        ),
        reverse=True
    )
    
    # Top 8 qualify
    return thirds[:8]


@functools.lru_cache(maxsize=None)
def _penalty_win_prob(team_a: str, team_b: str) -> float:
    """
    Computes the probability of team_a winning the shootout against team_b
    using the detailed penalty shootout distribution and team-specific penalty strengths.
    """
    base_pen_rate = predictor.CONSTANTS.get("pen_conversion_rate", 0.75)
    pen_mod_a = predictor.PENALTY_STRENGTH.get(team_a, 1.0)
    pen_mod_b = predictor.PENALTY_STRENGTH.get(team_b, 1.0)
    
    p_a = base_pen_rate * pen_mod_a
    p_b = base_pen_rate * pen_mod_b
    
    # Sudden death rates
    base_sd_rate = predictor.CONSTANTS.get("pen_sudden_death_conversion", 0.72)
    p_sd_a = base_sd_rate * pen_mod_a
    p_sd_b = base_sd_rate * pen_mod_b
    
    max_sd_rounds = int(predictor.CONSTANTS.get("pen_max_sudden_death_rounds", 5))
    
    dist = predictor.penalty_shootout_distribution(
        p_a=p_a, p_b=p_b,
        p_sd_a=p_sd_a, p_sd_b=p_sd_b,
        max_sd_rounds=max_sd_rounds
    )
    
    # Sum up probability of A winning
    p_a_win = sum(p for (ga, gb), p in dist.items() if ga > gb)
    return p_a_win


def _simulate_ko_match(team_a: str, team_b: str, phase: str,
                        host_teams: set, ko_cache: dict, rng: random.Random,
                        elevation: float = 0.0,
                        elo_a: float = None, elo_b: float = None,
                        travel_a: float = 0.0, travel_b: float = 0.0,
                        rest_a: float = 5.0, rest_b: float = 5.0) -> Tuple[str, int, int]:
    """Simulate KO match using cached grid. Returns (winner, ga, gb).
    
    Three-phase model:
    1. 90 min: Sample from probability grid (already KO-dampened)
    2. Extra Time (if draw): ~30 min at 35% intensity → Poisson sample
    3. Penalties (if still draw): Near-coinflip, max 55/45 edge
    
    Historical WC data shows:
    - ~25% of KO matches go to extra time
    - ~50% of those go to penalties (so ~12% of all KO matches)
    - Penalty shootouts are nearly 50/50 regardless of Elo
    """
    flat, cum_weights = _get_ko_grid(team_a, team_b, phase, host_teams, ko_cache, elevation, elo_a, elo_b, travel_a, travel_b, rest_a, rest_b)
    ga, gb = _sample_from_grid(flat, cum_weights, rng)
    
    if ga > gb:
        winner = team_a
    elif gb > ga:
        winner = team_b
    else:
        # Draw after 90 min → Extra Time simulation
        # ET is ~33% of regulation time at reduced intensity (~35% of λ)
        # This gives ~0.3-0.5 expected goals per team in ET
        eff_elo_a = elo_a if elo_a is not None else predictor.WORLD_CUP_2026_TEAMS.get(team_a, {}).get("elo", 1500)
        eff_elo_b = elo_b if elo_b is not None else predictor.WORLD_CUP_2026_TEAMS.get(team_b, {}).get("elo", 1500)
        
        # ET intensity from the ENGINE's model (S11): phase-adjusted λ scaled
        # by et_time_fraction x et_fatigue_factor — replaces a rogue Elo→goals
        # mapping (1.2 + (elo-1700)/800, x0.35 x0.33) that ignored the
        # recalibrated constants and ran ~2x colder than the 3-layer KO grid.
        la_b, lb_b = predictor.estimate_base_lambdas_from_elo(team_a, team_b, eff_elo_a, eff_elo_b)
        _rho_p, la_p, lb_p = predictor.apply_phase_adjustments(
            -0.05, la_b, lb_b, predictor.parse_match_phase(phase))
        et_scale = predictor.CONSTANTS["et_time_fraction"] * predictor.CONSTANTS["et_fatigue_factor"]
        et_lambda_a = max(0.05, la_p * et_scale)
        et_lambda_b = max(0.05, lb_p * et_scale)
        
        # Poisson sample for extra time goals
        def _poisson_sample(lam, r):
            """Simple Poisson sampling via inverse CDF."""
            L = math.exp(-lam)
            k = 0
            p = 1.0
            while True:
                p *= r.random()
                if p < L:
                    return k
                k += 1
        
        et_a = _poisson_sample(et_lambda_a, rng)
        et_b = _poisson_sample(et_lambda_b, rng)
        
        ga += et_a
        gb += et_b
        
        if ga > gb:
            winner = team_a
        elif gb > ga:
            winner = team_b
        else:
            # Still drawn → Penalty Shootout
            p_a_pens = _penalty_win_prob(team_a, team_b)
            winner = team_a if rng.random() < p_a_pens else team_b
    
    return winner, ga, gb


# ==============================================================================
# FULL TOURNAMENT SIMULATION
# ==============================================================================

def simulate_tournament(grid_cache: dict, host_teams: set = None,
                        market_probs: dict = None,
                        ko_cache: dict = None,
                        rng: random.Random = None) -> dict:
    """
    Simulate the entire WM 2026 tournament once using precomputed grids.
    """
    if rng is None:
        rng = random.Random()
    if ko_cache is None:
        ko_cache = {}
    
    total_goals = defaultdict(int)
    dynamic_elos = {team: data["elo"] for team, data in predictor.WORLD_CUP_2026_TEAMS.items()}
    
    def _update_elo(team_a: str, team_b: str, goals_a: int, goals_b: int, is_ko: bool = False):
        """Update local Elo ratings for Cinderella momentum."""
        elo_a = dynamic_elos.get(team_a, 1500)
        elo_b = dynamic_elos.get(team_b, 1500)
        
        # K-factor (higher for KO matches)
        K = 40 if is_ko else 30
        
        # Expected scores
        e_a = 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))
        e_b = 1.0 - e_a
        
        # Actual scores
        if goals_a > goals_b:
            s_a, s_b = 1.0, 0.0
        elif goals_b > goals_a:
            s_a, s_b = 0.0, 1.0
        else:
            s_a, s_b = 0.5, 0.5
            
        dynamic_elos[team_a] = elo_a + K * (s_a - e_a)
        dynamic_elos[team_b] = elo_b + K * (s_b - e_b)
    
    # ── GROUP STAGE ──
    all_standings = {}
    group_winners = {}
    group_runners_up = {}
    
    for group_name, teams in GROUPS.items():
        standings = simulate_group(group_name, teams, grid_cache, rng)
        all_standings[group_name] = standings
        group_winners[group_name] = standings[0]["team"]
        group_runners_up[group_name] = standings[1]["team"]
        
        for s in standings:
            total_goals[s["team"]] += s["gf"]
            
    # Best 3rd-place teams
    best_thirds = get_best_third_place_teams(all_standings)
    third_teams = [t["team"] for t in best_thirds]
    
    # ── ROUND OF 32 ──
    # Assign 3rd-place qualifiers to their match slots
    qualified_third_groups = set(t["from_group"] for t in best_thirds)
    third_by_group = {t["from_group"]: t["team"] for t in best_thirds}
    
    # Proper backtracking assignment of 3rd-place teams to match slots.
    slot_order = ["M75", "M77", "M79", "M80", "M81", "M82", "M85", "M88"]
    
    def _solve_third_assignment(idx, used, assignment):
        """Backtracking solver for 3rd-place slot assignment."""
        if idx == len(slot_order):
            return assignment.copy()  # Found valid assignment
        slot = slot_order[idx]
        pool = THIRD_PLACE_POOLS[slot]
        for g in pool:
            if g in qualified_third_groups and g not in used:
                assignment[f"3_{slot}"] = third_by_group[g]
                used.add(g)
                result = _solve_third_assignment(idx + 1, used, assignment)
                if result is not None:
                    return result
                used.discard(g)
                del assignment[f"3_{slot}"]
        return None  # No valid assignment from this state
    
    third_assigned = _solve_third_assignment(0, set(), {})
    if third_assigned is None:
        # Fallback (should never happen with 8-of-12 groups qualifying)
        third_assigned = {}
        used_groups = set()
        for slot in slot_order:
            pool = THIRD_PLACE_POOLS[slot]
            available = [g for g in pool if g in qualified_third_groups and g not in used_groups]
            if available:
                chosen = available[0]
                third_assigned[f"3_{slot}"] = third_by_group[chosen]
                used_groups.add(chosen)
            else:
                third_assigned[f"3_{slot}"] = "TBD"
    
    r32_matches = []
    for slot_a, slot_b in R32_BRACKET:
        def resolve_slot(slot):
            if slot.startswith("W_"):
                return group_winners[slot[2:]]
            elif slot.startswith("R_"):
                return group_runners_up[slot[2:]]
            elif slot.startswith("3_"):
                return third_assigned.get(slot, "TBD")
            return "TBD"
        
        r32_matches.append({"A": resolve_slot(slot_a), "B": resolve_slot(slot_b)})
    
    r32_winners = []
    for m_info in r32_matches:
        team_a = m_info["A"]
        team_b = m_info["B"]
        winner, ga, gb = _simulate_ko_match(
            team_a, team_b, "R32", host_teams, ko_cache, rng,
            elevation=0.0, elo_a=dynamic_elos.get(team_a), elo_b=dynamic_elos.get(team_b)
        )
        total_goals[team_a] += ga
        total_goals[team_b] += gb
        _update_elo(team_a, team_b, ga, gb, is_ko=True)
        r32_winners.append(winner)
    
    # ── ROUND OF 16 ──
    r16_winners = []
    for idx_a, idx_b in R16_BRACKET:
        team_a = r32_winners[idx_a]
        team_b = r32_winners[idx_b]
        winner, ga, gb = _simulate_ko_match(
            team_a, team_b, "R16", host_teams, ko_cache, rng, 
            elevation=0.0, elo_a=dynamic_elos.get(team_a), elo_b=dynamic_elos.get(team_b)
        )
        total_goals[team_a] += ga
        total_goals[team_b] += gb
        _update_elo(team_a, team_b, ga, gb, is_ko=True)
        r16_winners.append(winner)
    
    # ── QUARTERFINALS ──
    qf_winners = []
    for idx_a, idx_b in QF_BRACKET:
        team_a = r16_winners[idx_a]
        team_b = r16_winners[idx_b]
        winner, ga, gb = _simulate_ko_match(
            team_a, team_b, "QF", host_teams, ko_cache, rng,
            elevation=0.0, elo_a=dynamic_elos.get(team_a), elo_b=dynamic_elos.get(team_b)
        )
        total_goals[team_a] += ga
        total_goals[team_b] += gb
        _update_elo(team_a, team_b, ga, gb, is_ko=True)
        qf_winners.append(winner)
    
    semifinalists = list(qf_winners)
    
    # ── SEMIFINALS ──
    sf_winners = []
    for idx_a, idx_b in SF_BRACKET:
        team_a = qf_winners[idx_a]
        team_b = qf_winners[idx_b]
        winner, ga, gb = _simulate_ko_match(
            team_a, team_b, "SF", host_teams, ko_cache, rng,
            elevation=0.0, elo_a=dynamic_elos.get(team_a), elo_b=dynamic_elos.get(team_b)
        )
        total_goals[team_a] += ga
        total_goals[team_b] += gb
        _update_elo(team_a, team_b, ga, gb, is_ko=True)
        sf_winners.append(winner)
    
    # ── FINAL ──
    champion_winner, ga, gb = _simulate_ko_match(
        sf_winners[0], sf_winners[1], "FINAL", host_teams, ko_cache, rng,
        elevation=2.0, elo_a=dynamic_elos.get(sf_winners[0]), elo_b=dynamic_elos.get(sf_winners[1])
    )
    total_goals[sf_winners[0]] += ga
    total_goals[sf_winners[1]] += gb
    _update_elo(sf_winners[0], sf_winners[1], ga, gb, is_ko=True)
    
    return {
        "group_winners": group_winners,
        "group_runners_up": group_runners_up,
        "third_place_teams": third_teams,
        "semifinalists": semifinalists,
        "finalists": list(sf_winners),
        "champion": champion_winner,
        "total_goals": dict(total_goals),
    }


# ==============================================================================
# MONTE CARLO AGGREGATION
# ==============================================================================

def run_monte_carlo(n_sims: int = 10000, market_probs: dict = None,
                    seed: int = None, verbose: bool = True,
                    apply_injuries: bool = True,
                    apply_squad_value: bool = True) -> dict:
    """
    Run N full tournament simulations and aggregate results.
    """
    import predictor
    import copy
    original_teams = copy.deepcopy(predictor.WORLD_CUP_2026_TEAMS)
    try:
        return _run_monte_carlo_inner(n_sims, market_probs, seed, verbose, apply_injuries, apply_squad_value)
    finally:
        predictor.WORLD_CUP_2026_TEAMS.clear()
        predictor.WORLD_CUP_2026_TEAMS.update(original_teams)

def _run_monte_carlo_inner(n_sims: int = 10000, market_probs: dict = None,
                    seed: int = None, verbose: bool = True,
                    apply_injuries: bool = True,
                    apply_squad_value: bool = True) -> dict:
    """
    Run N full tournament simulations and aggregate results.
    
    Performance: precomputes all 72 group match grids once (~2s),
    then each simulation only needs to sample from cached distributions.
    KO match grids are also cached by team pair.
    """
    rng = random.Random(seed)
    
    # Apply injury Elo adjustments
    original_elos = {}
    if apply_injuries and INJURY_ELO_ADJUSTMENTS:
        if verbose:
            print("  🏥 Applying injury Elo adjustments:", file=sys.stderr)
        for team, adj in sorted(INJURY_ELO_ADJUSTMENTS.items(), key=lambda x: x[1]):
            if team in predictor.WORLD_CUP_2026_TEAMS:
                old_elo = predictor.WORLD_CUP_2026_TEAMS[team]["elo"]
                original_elos[team] = old_elo
                new_elo = old_elo + adj
                predictor.WORLD_CUP_2026_TEAMS[team]["elo"] = new_elo
                if verbose:
                    print(f"    {team:20s} {old_elo} → {new_elo} ({adj:+d})", file=sys.stderr)
    
    # Apply squad value + form Elo adjustments
    if apply_squad_value and SQUAD_MARKET_VALUES:
        squad_adjustments = compute_squad_elo_adjustments()
        if squad_adjustments and verbose:
            print("  💰 Applying squad value & form Elo adjustments:", file=sys.stderr)
        for team, adj in sorted(squad_adjustments.items(), key=lambda x: x[1], reverse=True):
            if team in predictor.WORLD_CUP_2026_TEAMS:
                if team not in original_elos:
                    original_elos[team] = predictor.WORLD_CUP_2026_TEAMS[team]["elo"]
                old_elo = predictor.WORLD_CUP_2026_TEAMS[team]["elo"]
                new_elo = old_elo + adj
                predictor.WORLD_CUP_2026_TEAMS[team]["elo"] = new_elo
                if verbose and abs(adj) >= 10:
                    print(f"    {team:20s} {old_elo} → {new_elo} ({adj:+d})", file=sys.stderr)
    
    # Counters
    group_winner_counts = {g: Counter() for g in GROUPS}
    semifinal_counts = Counter()
    champion_counts = Counter()
    total_goals_sum = defaultdict(int)
    top_scorer_team_counts = Counter()
    
    # Precompute group match grids (72 matches, computed once)
    if verbose:
        print("  📊 Precomputing 72 group match probability grids...", file=sys.stderr)
    
    t_cache = time.time()
    # Precompute grids for 90-min group stage
    grid_cache = precompute_grids(host_teams=HOST_TEAMS, market_probs=market_probs)
    ko_cache = {}  # KO grids cached lazily as new matchups appear
    
    if verbose:
        print(f"  ✅ Cache built in {time.time() - t_cache:.1f}s ({len(grid_cache)} grids)", file=sys.stderr)
    
    t0 = time.time()
    
    for i in range(n_sims):
        result = simulate_tournament(
            grid_cache=grid_cache,
            host_teams=HOST_TEAMS,
            market_probs=market_probs,
            ko_cache=ko_cache,
            rng=rng
        )
        
        # Group winners
        for group, winner in result["group_winners"].items():
            group_winner_counts[group][winner] += 1
        
        # Semifinalists
        for team in result["semifinalists"]:
            semifinal_counts[team] += 1
        
        # Champion
        champion_counts[result["champion"]] += 1
        
        # Goals (for top scorer team estimation)
        for team, goals in result["total_goals"].items():
            total_goals_sum[team] += goals
        
        # Golden Boot: simulate individual star-striker goals per team
        # using Binomial(team_total_goals, striker_concentration)
        # The Golden Boot goes to the PLAYER with most goals, not the team
        if result["total_goals"]:
            star_goals = {}
            for team, team_total in result["total_goals"].items():
                sc = STRIKER_CONCENTRATION.get(team)
                conc = sc["concentration"] if sc else STRIKER_CONCENTRATION_DEFAULT
                # Binomial via Bernoulli trials: each goal has 'conc' probability
                # of being scored by the star striker
                if team_total > 0:
                    star_goals[team] = sum(1 for _ in range(team_total) if rng.random() < conc)
                else:
                    star_goals[team] = 0
            # Team whose star striker scored the most individual goals
            max_goals = max(star_goals.values())
            top_teams = [t for t, g in star_goals.items() if g == max_goals]
            top_team = rng.choice(top_teams)
            top_scorer_team_counts[top_team] += 1

        
        # Progress
        if verbose and (i + 1) % max(1, n_sims // 10) == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (n_sims - i - 1) / rate
            print(f"  ⏳ {i+1:,}/{n_sims:,} simulations ({rate:.0f}/s, ETA {eta:.0f}s)", 
                  end="\r", file=sys.stderr)
    
    if verbose:
        elapsed = time.time() - t0
        print(f"  ✅ {n_sims:,} simulations completed in {elapsed:.1f}s ({n_sims/elapsed:.0f}/s)     ",
              file=sys.stderr)
    
    # ── Build results ──
    results = {
        "n_sims": n_sims,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    
    # Group winners (most probable for each group)
    results["group_winners"] = {}
    for group in sorted(GROUPS.keys()):
        counts = group_winner_counts[group]
        total = sum(counts.values())
        sorted_teams = counts.most_common()
        results["group_winners"][group] = {
            "tip": sorted_teams[0][0],
            "probability": round(sorted_teams[0][1] / total, 4),
            "all": {t: round(c / total, 4) for t, c in sorted_teams}
        }
    
    # Semifinalists (top 4 most probable)
    sf_total = n_sims  # Each sim has exactly 4 semifinalists
    sf_sorted = semifinal_counts.most_common()
    results["semifinalists"] = {
        "tips": [t for t, _ in sf_sorted[:4]],
        "probabilities": {t: round(c / sf_total, 4) for t, c in sf_sorted[:8]},
    }
    
    # Champion (with optional Shrinkage to Market Odds 50/50)
    if market_probs:
        blended_champ = {}
        for team in predictor.WORLD_CUP_2026_TEAMS:
            mc_prob = champion_counts[team] / n_sims
            mkt_prob = market_probs.get(team, mc_prob)
            blended_champ[team] = (mc_prob + mkt_prob) / 2.0
            
        champ_sorted = sorted(blended_champ.items(), key=lambda x: x[1], reverse=True)
        results["champion"] = {
            "tip": champ_sorted[0][0],
            "probability": round(champ_sorted[0][1], 4),
            "all": {t: round(c, 4) for t, c in champ_sorted if c > 0.005},
        }
    else:
        champ_sorted = champion_counts.most_common()
        results["champion"] = {
            "tip": champ_sorted[0][0],
            "probability": round(champ_sorted[0][1] / n_sims, 4),
            "all": {t: round(c / n_sims, 4) for t, c in champ_sorted if c / n_sims > 0.005},
        }
    
    # Top scorer team
    ts_sorted = top_scorer_team_counts.most_common()
    results["top_scorer_team"] = {
        "tip": ts_sorted[0][0],
        "probability": round(ts_sorted[0][1] / n_sims, 4),
        "avg_goals": {t: round(g / n_sims, 1) for t, g in total_goals_sum.items()},
        "all": {t: round(c / n_sims, 4) for t, c in ts_sorted[:10]},
    }
    
    # per-team expected tournament goals consumed by goalscorer.py
    results["team_expected_goals"] = {t: round(g / n_sims, 3)
                                      for t, g in sorted(total_goals_sum.items(), key=lambda x: -x[1])}
    
    return results


# ==============================================================================
# OUTPUT FORMATTING
# ==============================================================================

def format_results(results: dict) -> str:
    """Format Monte Carlo results as a readable Kicktipp tip sheet."""
    lines = []
    
    lines.append("")
    lines.append("═" * 62)
    lines.append("  ⚽ KICKTIPP BONUSFRAGEN — OPTIMALE TIPS")
    lines.append(f"  🎲 Basierend auf {results['n_sims']:,} Monte-Carlo-Simulationen")
    lines.append(f"  ⏱  Berechnet in {results['elapsed_seconds']:.1f}s")
    if "provenance" in results:
        lines.append(f"  📅 Timestamp: {results['provenance']['timestamp']}")
        lines.append(f"  🌱 Seed: {results['provenance']['seed']}")
        lines.append(f"  ⚙️  Cmd: {results['provenance']['command']}")
        if "commit" in results['provenance']:
            lines.append(f"  🔗 Commit: {results['provenance']['commit']}")
    lines.append("═" * 62)
    
    # ── Group winners ──
    lines.append("")
    lines.append("  ┌─────────────────────────────────────────────────────────┐")
    lines.append("  │  GRUPPENSIEGER                                         │")
    lines.append("  ├─────────────────────────────────────────────────────────┤")
    
    for group in sorted(results["group_winners"].keys()):
        gw = results["group_winners"][group]
        tip = gw["tip"]
        prob = gw["probability"] * 100
        
        # Show runner-up probability
        all_probs = gw["all"]
        others = [(t, p) for t, p in all_probs.items() if t != tip]
        runner_up = others[0] if others else ("?", 0)
        
        bar = "█" * int(prob / 3) + "░" * (20 - int(prob / 3))
        lines.append(f"  │  Gruppe {group}:  {tip:<18} {prob:5.1f}%  {bar}  │")
    
    lines.append("  └─────────────────────────────────────────────────────────┘")
    
    # ── Semifinalists ──
    lines.append("")
    lines.append("  ┌─────────────────────────────────────────────────────────┐")
    lines.append("  │  HALBFINALE (4 Teams)                                  │")
    lines.append("  ├─────────────────────────────────────────────────────────┤")
    
    sf_probs = results["semifinalists"]["probabilities"]
    for i, (team, prob) in enumerate(sorted(sf_probs.items(), key=lambda x: x[1], reverse=True)[:8]):
        marker = "  ★" if i < 4 else "   "
        bar = "█" * int(prob * 100 / 3) + "░" * (20 - int(prob * 100 / 3))
        tip_marker = " ◀ TIP" if i < 4 else ""
        lines.append(f"  │{marker} {team:<18} {prob*100:5.1f}%  {bar}{tip_marker:>6}  │")
    
    lines.append("  └─────────────────────────────────────────────────────────┘")
    
    # ── Champion ──
    lines.append("")
    lines.append("  ┌─────────────────────────────────────────────────────────┐")
    lines.append("  │  WELTMEISTER                                           │")
    lines.append("  ├─────────────────────────────────────────────────────────┤")
    
    champ = results["champion"]
    for team, prob in sorted(champ["all"].items(), key=lambda x: x[1], reverse=True)[:8]:
        marker = "  ★" if team == champ["tip"] else "   "
        tip_marker = " ◀ TIP" if team == champ["tip"] else ""
        bar = "█" * int(prob * 100 / 2) + "░" * (20 - int(prob * 100 / 2))
        lines.append(f"  │{marker} {team:<18} {prob*100:5.1f}%  {bar}{tip_marker:>6}  │")
    
    lines.append("  └─────────────────────────────────────────────────────────┘")
    
    # ── Top scorer team (Golden Boot) ──
    lines.append("")
    lines.append("  ┌─────────────────────────────────────────────────────────┐")
    lines.append("  │  TORSCHÜTZENKÖNIG-MANNSCHAFT (Golden Boot)              │")
    lines.append("  ├─────────────────────────────────────────────────────────┤")
    
    ts = results["top_scorer_team"]
    for team, prob in sorted(ts["all"].items(), key=lambda x: x[1], reverse=True)[:6]:
        marker = "  ★" if team == ts["tip"] else "   "
        tip_marker = " ◀ TIP" if team == ts["tip"] else ""
        sc = STRIKER_CONCENTRATION.get(team)
        striker_name = f"({sc['striker']})" if sc else ""
        avg = ts["avg_goals"].get(team, 0)
        lines.append(f"  │{marker} {team:<15} {prob*100:5.1f}%  {striker_name:<12} Ø{avg:.1f}g{tip_marker:>6}  │")
    
    lines.append("  └─────────────────────────────────────────────────────────┘")
    
    # ── Summary tip sheet ──
    lines.append("")
    lines.append("  ╔═════════════════════════════════════════════════════════╗")
    lines.append("  ║  📋 ZUSAMMENFASSUNG — DEINE TIPS                      ║")
    lines.append("  ╠═════════════════════════════════════════════════════════╣")
    
    for group in sorted(results["group_winners"].keys()):
        gw = results["group_winners"][group]
        lines.append(f"  ║  Gruppe {group}:    {gw['tip']:<20} ({gw['probability']*100:.0f}%)         ║")
    
    sf_tips = results["semifinalists"]["tips"]
    ts_sc = STRIKER_CONCENTRATION.get(ts["tip"])
    ts_striker = f" ({ts_sc['striker']})" if ts_sc else ""
    lines.append(f"  ║                                                         ║")
    lines.append(f"  ║  Halbfinale: {', '.join(sf_tips):<42} ║")
    lines.append(f"  ║  Weltmeister: {champ['tip']:<43}║")
    lines.append(f"  ║  Torschützen: {ts['tip'] + ts_striker:<43}║")
    lines.append("  ╚═════════════════════════════════════════════════════════╝")
    lines.append("")
    
    return "\n".join(lines)


# ==============================================================================
# CLI
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="WM 2026 Kicktipp Bonusfragen — Monte Carlo Tournament Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  Default (10k sims):     python3 tournament_bonusfragen.py
  High precision:         python3 tournament_bonusfragen.py --sims 50000
  With Polymarket odds:   python3 tournament_bonusfragen.py --fetch-odds
  JSON output:            python3 tournament_bonusfragen.py --json --output tips.json
  Reproducible:           python3 tournament_bonusfragen.py --seed 42
"""
    )
    
    parser.add_argument("--sims", type=int, default=10000, help="Number of simulations (default: 10000)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--fetch-odds", action="store_true", help="Fetch Polymarket odds (live)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", type=str, default=None, help="Write results to file")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    parser.add_argument("--no-injuries", action="store_true", help="Skip injury Elo adjustments")
    parser.add_argument("--no-squad-value", action="store_true", help="Skip squad value & form Elo adjustments")
    parser.add_argument("--odds-snapshot", type=str, default=None,
                        help="Load odds from a saved snapshot file (instead of fetching live)")
    
    args = parser.parse_args()
    
    # Fetch or load market data
    market_probs = None
    odds_timestamp = None
    
    if args.odds_snapshot:
        # Load from saved snapshot — ensures reproducibility & pre-kickoff compliance
        try:
            with open(args.odds_snapshot, 'r') as f:
                snapshot = json.load(f)
            market_probs = snapshot.get("probabilities", snapshot)
            odds_timestamp = snapshot.get("timestamp", "unknown")
            if not args.quiet:
                print(f"📊 Loaded odds snapshot from {args.odds_snapshot}", file=sys.stderr)
                print(f"   Snapshot timestamp: {odds_timestamp}", file=sys.stderr)
                print(f"   ⚠ IMPORTANT: Verify this snapshot is from BEFORE kickoff!", file=sys.stderr)
        except Exception as e:
            print(f"⚠ Failed to load snapshot: {e}. Using Elo only.", file=sys.stderr)
    
    elif args.fetch_odds:
        try:
            from datetime import datetime, timezone
            from odds_client import PolymarketClient
            pm = PolymarketClient()
            probs = pm.get_wc_winner_probabilities()
            if probs:
                market_probs = probs
                odds_timestamp = datetime.now(timezone.utc).isoformat()
                
                if not args.quiet:
                    print(f"📊 Polymarket: {len(probs)} teams fetched (top: "
                          f"{sorted(probs.items(), key=lambda x: x[1], reverse=True)[0][0]} "
                          f"{sorted(probs.items(), key=lambda x: x[1], reverse=True)[0][1]*100:.1f}%)",
                          file=sys.stderr)
                    print(f"   Fetched at: {odds_timestamp}", file=sys.stderr)
                
                # Auto-save snapshot for audit trail
                import os
                snap_name = datetime.now(timezone.utc).strftime("polymarket_snapshot_%Y%m%d_%H%M.json")
                snap_path = os.path.join(os.path.dirname(__file__), "data", snap_name)
                os.makedirs(os.path.dirname(snap_path), exist_ok=True)
                with open(snap_path, 'w') as f:
                    json.dump({
                        "timestamp": odds_timestamp,
                        "source": "polymarket_gamma_api",
                        "note": "Auto-saved snapshot. Verify this was fetched BEFORE kickoff.",
                        "probabilities": probs
                    }, f, indent=2)
                if not args.quiet:
                    print(f"   💾 Snapshot saved to {snap_path}", file=sys.stderr)
            else:
                print("⚠ No Polymarket data available. Using Elo only.", file=sys.stderr)
        except Exception as e:
            print(f"⚠ Polymarket fetch failed: {e}. Using Elo only.", file=sys.stderr)
    
    # Normalize market_probs keys to ensure exact matching with GROUPS
    if market_probs:
        normalized_probs = {}
        for k, v in market_probs.items():
            k_lower = k.lower().strip()
            mapped = predictor.TEAM_NAME_MAPPING.get(k_lower, k)
            normalized_probs[mapped] = v
        market_probs = normalized_probs

    if not args.quiet:
        src = "Polymarket + Elo blend" if market_probs else "Elo ratings only"
        print(f"🏆 Starting {args.sims:,} tournament simulations ({src})...", file=sys.stderr)
    
    # Run Monte Carlo
    results = run_monte_carlo(
        n_sims=args.sims,
        market_probs=market_probs,
        seed=args.seed,
        verbose=not args.quiet,
        apply_injuries=not args.no_injuries,
        apply_squad_value=not args.no_squad_value
    )
    
    # Inject provenance metadata
    from datetime import datetime, timezone
    import subprocess
    try:
        commit_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.STDOUT).decode('utf-8').strip()
        is_dirty = subprocess.call(['git', 'diff', '--quiet']) != 0
        if is_dirty:
            commit_hash += " (dirty)"
    except Exception:
        commit_hash = "unknown"
        
    results["provenance"] = {
        "command": " ".join(sys.argv),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed if args.seed else "random",
        "commit": commit_hash,
    }
    
    # Output
    if args.json:
        output = json.dumps(results, indent=2, ensure_ascii=False)
    else:
        output = format_results(results)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        if not args.quiet:
            print(f"💾 Results saved to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Alert (stderr + WhatsApp if configured) when any Bonusfragen answer changed
    # vs the last run of THIS engine (separate scope from the vectorized engine — S11).
    from utils import recommendations_state as rec_state
    rec_state.alert_on_changes("bonusfragen:scalar",
                               rec_state.bonusfragen_recommendations(results))


if __name__ == "__main__":
    main()
