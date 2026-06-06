#!/usr/bin/env python3
"""
WM 2018 Backtest — Monte Carlo Tournament Simulation

Validates the predictor engine against the actual FIFA World Cup 2018 results.
Uses PRE-TOURNAMENT Elo ratings from eloratings.net (June 13, 2018) to
avoid hindsight bias.

Usage:
    python3 backtest_wm2018.py                  # Default 10,000 sims, seed=2018
    python3 backtest_wm2018.py --sims 50000     # More sims for precision
"""

import argparse
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import predictor

# ==============================================================================
# WM 2018 GROUPS (32 teams, 8 groups × 4 teams)
# ==============================================================================

WM2018_GROUPS = {
    "A": ["Russia", "Saudi Arabia", "Egypt", "Uruguay"],
    "B": ["Portugal", "Spain", "Morocco", "Iran"],
    "C": ["France", "Australia", "Peru", "Denmark"],
    "D": ["Argentina", "Iceland", "Croatia", "Nigeria"],
    "E": ["Brazil", "Switzerland", "Costa Rica", "Serbia"],
    "F": ["Germany", "Mexico", "Sweden", "South Korea"],
    "G": ["Belgium", "Panama", "Tunisia", "England"],
    "H": ["Poland", "Senegal", "Colombia", "Japan"],
}

# ==============================================================================
# ACTUAL WM 2018 RESULTS (ground truth)
# ==============================================================================

ACTUAL_GROUP_WINNERS = {
    "A": "Uruguay",
    "B": "Spain",
    "C": "France",
    "D": "Croatia",
    "E": "Brazil",
    "F": "Sweden",
    "G": "Belgium",
    "H": "Colombia",
}

ACTUAL_GROUP_RUNNERS_UP = {
    "A": "Russia",
    "B": "Portugal",
    "C": "Denmark",
    "D": "Argentina",
    "E": "Switzerland",
    "F": "Mexico",
    "G": "England",
    "H": "Japan",
}

ACTUAL_QF_TEAMS = {
    "Uruguay", "France", "Brazil", "Belgium",
    "Russia", "Croatia", "Sweden", "England",
}

ACTUAL_SF_TEAMS = {"France", "Belgium", "Croatia", "England"}

ACTUAL_CHAMPION = "France"
ACTUAL_RUNNER_UP = "Croatia"

# ==============================================================================
# PRE-WM 2018 ELO RATINGS (June 13, 2018 — day before tournament start)
# Source: eloratings.net historical snapshot
# ==============================================================================

PRE_WM2018_ELO = {
    "Brazil":       {"elo": 2141, "rank": 1},
    "Germany":      {"elo": 2076, "rank": 2},
    "Spain":        {"elo": 2043, "rank": 3},
    "France":       {"elo": 1986, "rank": 4},
    "Argentina":    {"elo": 1985, "rank": 5},
    "Portugal":     {"elo": 1967, "rank": 6},
    "England":      {"elo": 1947, "rank": 7},
    "Belgium":      {"elo": 1935, "rank": 8},
    "Colombia":     {"elo": 1927, "rank": 9},
    "Peru":         {"elo": 1915, "rank": 10},
    "Uruguay":      {"elo": 1892, "rank": 11},
    "Switzerland":  {"elo": 1888, "rank": 12},
    "Denmark":      {"elo": 1854, "rank": 13},
    "Croatia":      {"elo": 1853, "rank": 14},
    "Mexico":       {"elo": 1849, "rank": 15},
    "Poland":       {"elo": 1830, "rank": 16},
    "Sweden":       {"elo": 1793, "rank": 17},
    "Iran":         {"elo": 1790, "rank": 18},
    "Serbia":       {"elo": 1787, "rank": 19},
    "Iceland":      {"elo": 1764, "rank": 20},
    "Senegal":      {"elo": 1745, "rank": 21},
    "Australia":    {"elo": 1743, "rank": 22},
    "Costa Rica":   {"elo": 1742, "rank": 23},
    "Morocco":      {"elo": 1731, "rank": 24},
    "South Korea":  {"elo": 1713, "rank": 25},
    "Japan":        {"elo": 1684, "rank": 26},
    "Nigeria":      {"elo": 1681, "rank": 27},
    "Russia":       {"elo": 1676, "rank": 28},
    "Panama":       {"elo": 1657, "rank": 29},
    "Tunisia":      {"elo": 1652, "rank": 30},
    "Egypt":        {"elo": 1639, "rank": 31},
    "Saudi Arabia": {"elo": 1588, "rank": 32},
}

# ==============================================================================
# R16 BRACKET FOR WM 2018 (standard 32-team bracket)
# ==============================================================================
# 1A vs 2B, 1C vs 2D, 1E vs 2F, 1G vs 2H  (left half)
# 1B vs 2A, 1D vs 2C, 1F vs 2E, 1H vs 2G  (right half)

R16_BRACKET = [
    # Left half
    ("W_A", "R_B"),  # M49: 1A vs 2B → Uruguay vs Portugal
    ("W_C", "R_D"),  # M50: 1C vs 2D → France vs Argentina
    ("W_E", "R_F"),  # M51: 1E vs 2F → Brazil vs Mexico
    ("W_G", "R_H"),  # M52: 1G vs 2H → Belgium vs Japan
    # Right half
    ("W_B", "R_A"),  # M53: 1B vs 2A → Spain vs Russia
    ("W_D", "R_C"),  # M54: 1D vs 2C → Croatia vs Denmark
    ("W_F", "R_E"),  # M55: 1F vs 2E → Sweden vs Switzerland
    ("W_H", "R_G"),  # M56: 1H vs 2G → Colombia vs England
]

# QF pairings (R16 winners, 0-indexed):
QF_BRACKET = [(0, 1), (2, 3), (4, 5), (6, 7)]

# SF pairings:
SF_BRACKET = [(0, 1), (2, 3)]


# ==============================================================================
# SIMULATION ENGINE
# ==============================================================================

def _inject_pre_wm2018_elo():
    """Temporarily override ALL team Elo values with pre-WM-2018 ratings."""
    originals = {}
    for team, data in PRE_WM2018_ELO.items():
        if team in predictor.WORLD_CUP_2026_TEAMS:
            originals[team] = dict(predictor.WORLD_CUP_2026_TEAMS[team])
            predictor.WORLD_CUP_2026_TEAMS[team] = data
        else:
            originals[team] = None  # Mark as newly added
            predictor.WORLD_CUP_2026_TEAMS[team] = data
    return originals


def _restore_elo(originals: dict):
    """Restore original Elo values after backtest."""
    for team, orig_data in originals.items():
        if orig_data is None:
            if team in predictor.WORLD_CUP_2026_TEAMS:
                del predictor.WORLD_CUP_2026_TEAMS[team]
        else:
            predictor.WORLD_CUP_2026_TEAMS[team] = orig_data


def _build_group_grid_cache() -> dict:
    """Precompute probability grids for all WM 2018 group stage matches."""
    cache = {}
    for group_name, teams in WM2018_GROUPS.items():
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                team_a, team_b = teams[i], teams[j]
                key = (team_a, team_b)
                row = {"team_a": team_a, "team_b": team_b}
                result = predictor.predict_single_match(row)
                grid = result["grid"]

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

                cache[key] = (flat, cum_weights)
    return cache


def _sample_from_grid(flat, cum_weights, rng):
    """Fast binary-search sampling from precomputed cumulative weights."""
    r = rng.random()
    lo, hi = 0, len(cum_weights) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum_weights[mid] < r:
            lo = mid + 1
        else:
            hi = mid
    return flat[lo]


def _get_ko_grid(team_a, team_b, phase, ko_cache):
    """Get or compute KO match grid (cached by team pair + phase)."""
    key = (team_a, team_b, phase)
    if key in ko_cache:
        return ko_cache[key]

    row = {"team_a": team_a, "team_b": team_b, "phase": phase}
    result = predictor.predict_single_match(row)
    grid = result["grid"]

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


def _simulate_ko_match(team_a, team_b, phase, ko_cache, rng):
    """Simulate a KO match. Returns winner."""
    flat, cum_weights = _get_ko_grid(team_a, team_b, phase, ko_cache)
    ga, gb = _sample_from_grid(flat, cum_weights, rng)

    if ga > gb:
        return team_a
    elif gb > ga:
        return team_b
    else:
        # Draw → penalty shootout (Elo-weighted coin flip)
        elo_a = predictor.WORLD_CUP_2026_TEAMS.get(team_a, {}).get("elo", 1700)
        elo_b = predictor.WORLD_CUP_2026_TEAMS.get(team_b, {}).get("elo", 1700)
        elo_diff = (elo_a - elo_b) / 800.0
        p_a_pens = 1.0 / (1.0 + 10 ** (-elo_diff))
        return team_a if rng.random() < p_a_pens else team_b


def simulate_group(group_name, teams, grid_cache, rng):
    """Simulate all 6 matches in a 4-team group."""
    standings = {}
    for team in teams:
        standings[team] = {
            "team": team, "group": group_name,
            "pts": 0, "gf": 0, "ga": 0, "gd": 0,
        }

    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            team_a, team_b = teams[i], teams[j]
            key = (team_a, team_b)
            if key in grid_cache:
                flat, cum_weights = grid_cache[key]
                ga, gb = _sample_from_grid(flat, cum_weights, rng)
            else:
                key_rev = (team_b, team_a)
                if key_rev in grid_cache:
                    flat, cum_weights = grid_cache[key_rev]
                    gb, ga = _sample_from_grid(flat, cum_weights, rng)
                else:
                    ga, gb = 1, 0

            standings[team_a]["gf"] += ga
            standings[team_a]["ga"] += gb
            standings[team_b]["gf"] += gb
            standings[team_b]["ga"] += ga

            if ga > gb:
                standings[team_a]["pts"] += 3
            elif ga == gb:
                standings[team_a]["pts"] += 1
                standings[team_b]["pts"] += 1
            else:
                standings[team_b]["pts"] += 3

    for team in standings:
        standings[team]["gd"] = standings[team]["gf"] - standings[team]["ga"]

    sorted_standings = sorted(
        standings.values(),
        key=lambda x: (
            x["pts"], x["gd"], x["gf"],
            predictor.WORLD_CUP_2026_TEAMS.get(x["team"], {}).get("elo", 1500)
        ),
        reverse=True
    )
    return sorted_standings


def simulate_tournament(grid_cache, ko_cache, rng):
    """Simulate the entire WM 2018 tournament once."""
    # ── GROUP STAGE ──
    group_winners = {}
    group_runners_up = {}

    for group_name, teams in WM2018_GROUPS.items():
        standings = simulate_group(group_name, teams, grid_cache, rng)
        group_winners[group_name] = standings[0]["team"]
        group_runners_up[group_name] = standings[1]["team"]

    # ── ROUND OF 16 ──
    def resolve_slot(slot):
        if slot.startswith("W_"):
            return group_winners[slot[2:]]
        elif slot.startswith("R_"):
            return group_runners_up[slot[2:]]
        return "TBD"

    r16_winners = []
    for slot_a, slot_b in R16_BRACKET:
        team_a = resolve_slot(slot_a)
        team_b = resolve_slot(slot_b)
        winner = _simulate_ko_match(team_a, team_b, "R16", ko_cache, rng)
        r16_winners.append(winner)

    # ── QUARTERFINALS ──
    qf_winners = []
    for idx_a, idx_b in QF_BRACKET:
        team_a = r16_winners[idx_a]
        team_b = r16_winners[idx_b]
        winner = _simulate_ko_match(team_a, team_b, "QF", ko_cache, rng)
        qf_winners.append(winner)

    semifinalists = list(qf_winners)

    # ── SEMIFINALS ──
    sf_winners = []
    for idx_a, idx_b in SF_BRACKET:
        team_a = qf_winners[idx_a]
        team_b = qf_winners[idx_b]
        winner = _simulate_ko_match(team_a, team_b, "SF", ko_cache, rng)
        sf_winners.append(winner)

    # ── FINAL ──
    champion = _simulate_ko_match(sf_winners[0], sf_winners[1], "FINAL", ko_cache, rng)

    return {
        "group_winners": group_winners,
        "group_runners_up": group_runners_up,
        "semifinalists": semifinalists,
        "finalists": list(sf_winners),
        "champion": champion,
    }


# ==============================================================================
# MONTE CARLO & REPORT
# ==============================================================================

def run_backtest(n_sims=10000, seed=2018, verbose=True):
    """Run N full WM 2018 tournament simulations and aggregate results."""
    rng = random.Random(seed)

    # Inject pre-WM 2018 Elo values
    originals = _inject_pre_wm2018_elo()
    if verbose:
        print("  🕐 Using pre-WM 2018 Elo ratings (eloratings.net, June 13 2018)", file=sys.stderr)

    # Counters
    group_winner_counts = {g: Counter() for g in WM2018_GROUPS}
    semifinal_counts = Counter()
    champion_counts = Counter()

    # Precompute group match grids
    if verbose:
        print("  📊 Precomputing group match probability grids...", file=sys.stderr)

    t_cache = time.time()
    grid_cache = _build_group_grid_cache()
    ko_cache = {}

    if verbose:
        print(f"  ✅ Cache built in {time.time() - t_cache:.1f}s ({len(grid_cache)} grids)",
              file=sys.stderr)

    t0 = time.time()

    for i in range(n_sims):
        result = simulate_tournament(grid_cache, ko_cache, rng)

        for group, winner in result["group_winners"].items():
            group_winner_counts[group][winner] += 1

        for team in result["semifinalists"]:
            semifinal_counts[team] += 1

        champion_counts[result["champion"]] += 1

        if verbose and (i + 1) % max(1, n_sims // 10) == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (n_sims - i - 1) / rate if rate > 0 else 0
            print(f"  ⏳ {i+1:,}/{n_sims:,} simulations ({rate:.0f}/s, ETA {eta:.0f}s)",
                  end="\r", file=sys.stderr)

    if verbose:
        elapsed = time.time() - t0
        rate = n_sims / elapsed if elapsed > 0 else 0
        print(f"  ✅ {n_sims:,} simulations completed in {elapsed:.1f}s ({rate:.0f}/s)     ",
              file=sys.stderr)

    # Restore original Elo values
    _restore_elo(originals)

    return {
        "n_sims": n_sims,
        "group_winner_counts": group_winner_counts,
        "semifinal_counts": semifinal_counts,
        "champion_counts": champion_counts,
    }


def print_report(results):
    """Print a comprehensive backtest report card."""
    n_sims = results["n_sims"]
    group_winner_counts = results["group_winner_counts"]
    champion_counts = results["champion_counts"]
    semifinal_counts = results["semifinal_counts"]

    print()
    print("═" * 70)
    print("  ⚽ WM 2018 BACKTEST — MODEL VALIDATION REPORT")
    print(f"  🎲 {n_sims:,} Monte-Carlo-Simulationen | Pre-Tournament Elo")
    print(f"  📊 Source: eloratings.net, June 13, 2018")
    print("═" * 70)

    # ── 1. GROUP WINNERS ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  1. GROUP WINNER PREDICTIONS vs ACTUAL                       │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    correct_groups = 0
    total_groups = 8

    for group in sorted(WM2018_GROUPS.keys()):
        counts = group_winner_counts[group]
        total = sum(counts.values())
        predicted = counts.most_common(1)[0][0]
        prob = counts.most_common(1)[0][1] / total * 100
        actual = ACTUAL_GROUP_WINNERS[group]
        match = predicted == actual
        icon = "✅" if match else "❌"
        if match:
            correct_groups += 1

        actual_prob = counts.get(actual, 0) / total * 100
        if match:
            extra = ""
        else:
            extra = f"  (actual: {actual} {actual_prob:.1f}%)"

        print(f"  │  {icon} Gr.{group}: Predicted {predicted:<14s} {prob:5.1f}%"
              f"  | Actual: {actual:<14s}{extra:>0s}")

    pct_groups = correct_groups / total_groups * 100
    print(f"  │                                                               │")
    print(f"  │  Score: {correct_groups}/{total_groups} correct ({pct_groups:.0f}%)"
          f"{'':>35s}│")
    print("  └───────────────────────────────────────────────────────────────┘")

    # ── 2. CHAMPION ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  2. CHAMPION PREDICTION (Top 8)                              │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    champ_sorted = champion_counts.most_common()
    predicted_champion = champ_sorted[0][0]
    champion_correct = predicted_champion == ACTUAL_CHAMPION

    for i, (team, count) in enumerate(champ_sorted[:8]):
        prob = count / n_sims * 100
        is_actual = team == ACTUAL_CHAMPION
        marker = " ◀ ACTUAL ✅" if is_actual else ""
        rank_marker = "★" if i == 0 else " "
        bar = "█" * int(prob / 2) + "░" * (20 - int(prob / 2))
        print(f"  │  {rank_marker} {team:<18s} {prob:5.1f}%  {bar}{marker:>12s}  │")

    actual_champ_prob = champion_counts.get(ACTUAL_CHAMPION, 0) / n_sims * 100
    actual_champ_rank = next(
        (i + 1 for i, (t, _) in enumerate(champ_sorted) if t == ACTUAL_CHAMPION), -1
    )
    print(f"  │                                                               │")
    champ_icon = "✅" if champion_correct else "❌"
    print(f"  │  {champ_icon} Predicted: {predicted_champion:<14s}"
          f"| Actual: {ACTUAL_CHAMPION:<14s}({actual_champ_prob:.1f}%, rank #{actual_champ_rank})│")
    print("  └───────────────────────────────────────────────────────────────┘")

    # ── 3. SEMIFINALISTS ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  3. SEMIFINALIST PREDICTION                                  │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    sf_sorted = semifinal_counts.most_common()
    predicted_sf = set(t for t, _ in sf_sorted[:4])
    sf_overlap = predicted_sf & ACTUAL_SF_TEAMS
    sf_overlap_count = len(sf_overlap)

    # Show top 8 predicted
    shown_teams = set()
    for i, (team, count) in enumerate(sf_sorted[:8]):
        prob = count / n_sims * 100
        is_actual = team in ACTUAL_SF_TEAMS
        is_predicted = i < 4
        markers = []
        if is_predicted:
            markers.append("TIP")
        if is_actual:
            markers.append("ACTUAL ✅" if is_predicted else "ACTUAL")
        marker_str = " ◀ " + ", ".join(markers) if markers else ""
        rank_marker = "★" if i < 4 else " "
        bar = "█" * int(prob / 3) + "░" * (20 - int(prob / 3))
        print(f"  │  {rank_marker} {team:<18s} {prob:5.1f}%  {bar}{marker_str:>0s}")
        shown_teams.add(team)

    # Show actual SF teams not in top 8
    for team in sorted(ACTUAL_SF_TEAMS):
        if team not in shown_teams:
            prob = semifinal_counts.get(team, 0) / n_sims * 100
            print(f"  │    {team:<18s} {prob:5.1f}%  (actual SF, not in top 8)")

    print(f"  │                                                               │")
    print(f"  │  Overlap: {sf_overlap_count}/4 actual semifinalists predicted"
          f"{'':>23s}│")
    if sf_overlap:
        print(f"  │  Matched: {', '.join(sorted(sf_overlap)):>48s}  │")
    missed = ACTUAL_SF_TEAMS - predicted_sf
    if missed:
        print(f"  │  Missed:  {', '.join(sorted(missed)):>48s}  │")
    print("  └───────────────────────────────────────────────────────────────┘")

    # ── 4. OVERALL SCORE ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  4. OVERALL ACCURACY SCORE                                   │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    group_score = correct_groups / total_groups
    champion_score = 1.0 if champion_correct else 0.0
    sf_score = sf_overlap_count / 4.0

    overall = group_score * 0.40 + champion_score * 0.30 + sf_score * 0.30
    overall_pct = overall * 100

    print(f"  │                                                               │")
    print(f"  │  Group Winners:    {correct_groups}/{total_groups}"
          f"  ({group_score*100:5.1f}%) × 40% = {group_score*0.40*100:5.1f}%       │")
    print(f"  │  Champion:         {'✅' if champion_correct else '❌'}    "
          f"  ({champion_score*100:5.1f}%) × 30% = {champion_score*0.30*100:5.1f}%       │")
    print(f"  │  Semifinalists:    {sf_overlap_count}/4 "
          f"  ({sf_score*100:5.1f}%) × 30% = {sf_score*0.30*100:5.1f}%       │")
    print(f"  │{'─'*63}│")

    if overall_pct >= 80:
        grade = "A"
    elif overall_pct >= 65:
        grade = "B"
    elif overall_pct >= 50:
        grade = "C"
    elif overall_pct >= 35:
        grade = "D"
    else:
        grade = "F"

    bar = "█" * int(overall_pct / 2.5) + "░" * (40 - int(overall_pct / 2.5))
    print(f"  │  OVERALL: {overall_pct:5.1f}%  Grade: {grade}"
          f"{'':>37s}│")
    print(f"  │  {bar}  │")
    print(f"  │                                                               │")
    print("  └───────────────────────────────────────────────────────────────┘")

    # ── 5. UPSETS ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  5. NOTABLE UPSETS / SURPRISES                               │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    upsets = []
    for group in sorted(WM2018_GROUPS.keys()):
        counts = group_winner_counts[group]
        total = sum(counts.values())
        actual = ACTUAL_GROUP_WINNERS[group]
        predicted = counts.most_common(1)[0][0]
        if predicted != actual:
            pred_prob = counts.most_common(1)[0][1] / total * 100
            actual_prob = counts.get(actual, 0) / total * 100
            upsets.append((group, predicted, pred_prob, actual, actual_prob))

    if upsets:
        for group, pred, pred_prob, actual, actual_prob in upsets:
            print(f"  │  🔥 Group {group}: Expected {pred} ({pred_prob:.0f}%),"
                  f" got {actual} ({actual_prob:.0f}%)")
    else:
        print(f"  │  No group winner upsets — model predicted all correctly!   │")

    surprise_sf = ACTUAL_SF_TEAMS - predicted_sf
    if surprise_sf:
        for team in sorted(surprise_sf):
            prob = semifinal_counts.get(team, 0) / n_sims * 100
            print(f"  │  🔥 {team} made SF (model gave {prob:.1f}% chance)")

    print("  └───────────────────────────────────────────────────────────────┘")

    # ── 6. COMPARISON WITH WM 2022 BACKTEST ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  6. CROSS-TOURNAMENT COMPARISON                              │")
    print("  ├───────────────────────────────────────────────────────────────┤")
    print(f"  │  {'Metric':<25s} {'WM 2018':>10s}   {'WM 2022':>10s}      │")
    print(f"  │  {'─'*55}│")
    print(f"  │  {'Groups correct':<25s} {correct_groups}/8{'':<8s}   6/8{'':<8s}      │")
    print(f"  │  {'Champion correct':<25s} {'✅' if champion_correct else '❌':<10s}   ❌{'':<8s}      │")
    print(f"  │  {'SF overlap':<25s} {sf_overlap_count}/4{'':<8s}   1/4{'':<8s}      │")
    print(f"  │  {'Overall grade':<25s} {grade:<10s}   D{'':<8s}       │")
    print("  └───────────────────────────────────────────────────────────────┘")
    print()


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="WM 2018 Backtest — Validate predictor against actual results"
    )
    parser.add_argument("--sims", type=int, default=10000,
                        help="Number of Monte Carlo simulations (default: 10000)")
    parser.add_argument("--seed", type=int, default=2018,
                        help="Random seed (default: 2018)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress progress output")
    args = parser.parse_args()

    verbose = not args.quiet

    if verbose:
        print()
        print("🏆 WM 2018 BACKTEST — Validating predictor engine")
        print(f"   Simulations: {args.sims:,} | Seed: {args.seed}")
        print(f"   Elo Source: eloratings.net (June 13, 2018 — pre-tournament)")
        print()

    results = run_backtest(n_sims=args.sims, seed=args.seed, verbose=verbose)
    print_report(results)


if __name__ == "__main__":
    main()
