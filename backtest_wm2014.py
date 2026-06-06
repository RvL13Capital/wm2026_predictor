#!/usr/bin/env python3
"""
WM 2014 Backtest — Monte Carlo Tournament Simulation

Validates the predictor engine against the actual FIFA World Cup 2014 results.
Uses PRE-TOURNAMENT Elo ratings from eloratings.net (June 11, 2014).

Usage:
    python3 backtest_wm2014.py                  # Default 10,000 sims, seed=2014
    python3 backtest_wm2014.py --sims 50000     # More sims for precision
"""

import argparse
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import predictor

# ==============================================================================
# WM 2014 GROUPS (32 teams, 8 groups × 4 teams)
# ==============================================================================

WM2014_GROUPS = {
    "A": ["Brazil", "Croatia", "Mexico", "Cameroon"],
    "B": ["Spain", "Netherlands", "Chile", "Australia"],
    "C": ["Colombia", "Greece", "Ivory Coast", "Japan"],
    "D": ["Uruguay", "Costa Rica", "England", "Italy"],
    "E": ["Switzerland", "Ecuador", "France", "Honduras"],
    "F": ["Argentina", "Bosnia", "Iran", "Nigeria"],
    "G": ["Germany", "Portugal", "Ghana", "USA"],
    "H": ["Belgium", "Algeria", "Russia", "South Korea"],
}

# ==============================================================================
# ACTUAL WM 2014 RESULTS
# ==============================================================================

ACTUAL_GROUP_WINNERS = {
    "A": "Brazil",
    "B": "Netherlands",
    "C": "Colombia",
    "D": "Costa Rica",
    "E": "France",
    "F": "Argentina",
    "G": "Germany",
    "H": "Belgium",
}

ACTUAL_GROUP_RUNNERS_UP = {
    "A": "Mexico",
    "B": "Chile",
    "C": "Greece",
    "D": "Uruguay",
    "E": "Switzerland",
    "F": "Nigeria",
    "G": "USA",
    "H": "Algeria",
}

ACTUAL_QF_TEAMS = {
    "Brazil", "Colombia", "France", "Germany",
    "Netherlands", "Costa Rica", "Argentina", "Belgium",
}

ACTUAL_SF_TEAMS = {"Brazil", "Germany", "Netherlands", "Argentina"}

ACTUAL_CHAMPION = "Germany"
ACTUAL_RUNNER_UP = "Argentina"

# ==============================================================================
# PRE-WM 2014 ELO RATINGS (June 11, 2014 — before tournament start)
# Source: eloratings.net historical snapshot
# ==============================================================================

PRE_WM2014_ELO = {
    "Spain":        {"elo": 2087, "rank": 1},   # Defending champion
    "Argentina":    {"elo": 2063, "rank": 2},
    "Germany":      {"elo": 2023, "rank": 3},
    "Colombia":     {"elo": 2018, "rank": 4},
    "Chile":        {"elo": 1981, "rank": 5},
    "Brazil":       {"elo": 1979, "rank": 6},   # Host
    "Netherlands":  {"elo": 1961, "rank": 7},
    "France":       {"elo": 1956, "rank": 8},
    "USA":          {"elo": 1857, "rank": 9},
    "Switzerland":  {"elo": 1854, "rank": 10},
    "Italy":        {"elo": 1849, "rank": 11},
    "Russia":       {"elo": 1848, "rank": 12},
    "Ecuador":      {"elo": 1836, "rank": 13},
    "Greece":       {"elo": 1823, "rank": 14},
    "Croatia":      {"elo": 1818, "rank": 15},
    "Portugal":     {"elo": 1917, "rank": 16},
    "Mexico":       {"elo": 1814, "rank": 17},
    "Uruguay":      {"elo": 1898, "rank": 18},
    "Belgium":      {"elo": 1911, "rank": 19},
    "England":      {"elo": 1908, "rank": 20},  # ~1908 from archive
    "Japan":        {"elo": 1785, "rank": 21},
    "Bosnia":       {"elo": 1785, "rank": 22},   # Bosnia and Herzegovina
    "Ivory Coast":  {"elo": 1772, "rank": 23},
    "Nigeria":      {"elo": 1727, "rank": 24},
    "Iran":         {"elo": 1715, "rank": 25},
    "Costa Rica":   {"elo": 1711, "rank": 26},
    "Australia":    {"elo": 1708, "rank": 27},
    "Ghana":        {"elo": 1704, "rank": 28},
    "Honduras":     {"elo": 1668, "rank": 29},
    "South Korea":  {"elo": 1667, "rank": 30},
    "Algeria":      {"elo": 1625, "rank": 31},
    "Cameroon":     {"elo": 1606, "rank": 32},
}

# Brazil as host gets home advantage
HOST_TEAMS_2014 = {"Brazil"}

# ==============================================================================
# R16 BRACKET (standard 32-team)
# ==============================================================================

R16_BRACKET = [
    ("W_A", "R_B"),  # Brazil vs Chile
    ("W_C", "R_D"),  # Colombia vs Uruguay
    ("W_E", "R_F"),  # France vs Nigeria
    ("W_G", "R_H"),  # Germany vs Algeria
    ("W_B", "R_A"),  # Netherlands vs Mexico
    ("W_D", "R_C"),  # Costa Rica vs Greece
    ("W_F", "R_E"),  # Argentina vs Switzerland
    ("W_H", "R_G"),  # Belgium vs USA
]

QF_BRACKET = [(0, 1), (2, 3), (4, 5), (6, 7)]
SF_BRACKET = [(0, 1), (2, 3)]


# ==============================================================================
# SIMULATION ENGINE
# ==============================================================================

def _inject_pre_wm2014_elo():
    originals = {}
    for team, data in PRE_WM2014_ELO.items():
        if team in predictor.WORLD_CUP_2026_TEAMS:
            originals[team] = dict(predictor.WORLD_CUP_2026_TEAMS[team])
            predictor.WORLD_CUP_2026_TEAMS[team] = data
        else:
            originals[team] = None
            predictor.WORLD_CUP_2026_TEAMS[team] = data
    return originals


def _restore_elo(originals):
    for team, orig_data in originals.items():
        if orig_data is None:
            if team in predictor.WORLD_CUP_2026_TEAMS:
                del predictor.WORLD_CUP_2026_TEAMS[team]
        else:
            predictor.WORLD_CUP_2026_TEAMS[team] = orig_data


def _build_group_grid_cache():
    cache = {}
    for group_name, teams in WM2014_GROUPS.items():
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
    flat, cum_weights = _get_ko_grid(team_a, team_b, phase, ko_cache)
    ga, gb = _sample_from_grid(flat, cum_weights, rng)
    if ga > gb:
        return team_a
    elif gb > ga:
        return team_b
    else:
        elo_a = predictor.WORLD_CUP_2026_TEAMS.get(team_a, {}).get("elo", 1700)
        elo_b = predictor.WORLD_CUP_2026_TEAMS.get(team_b, {}).get("elo", 1700)
        elo_diff = (elo_a - elo_b) / 800.0
        p_a_pens = 1.0 / (1.0 + 10 ** (-elo_diff))
        return team_a if rng.random() < p_a_pens else team_b


def simulate_group(group_name, teams, grid_cache, rng):
    standings = {}
    for team in teams:
        standings[team] = {"team": team, "pts": 0, "gf": 0, "ga": 0, "gd": 0}

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

    return sorted(
        standings.values(),
        key=lambda x: (x["pts"], x["gd"], x["gf"],
                       predictor.WORLD_CUP_2026_TEAMS.get(x["team"], {}).get("elo", 1500)),
        reverse=True
    )


def simulate_tournament(grid_cache, ko_cache, rng):
    group_winners = {}
    group_runners_up = {}
    for group_name, teams in WM2014_GROUPS.items():
        standings = simulate_group(group_name, teams, grid_cache, rng)
        group_winners[group_name] = standings[0]["team"]
        group_runners_up[group_name] = standings[1]["team"]

    def resolve_slot(slot):
        if slot.startswith("W_"): return group_winners[slot[2:]]
        elif slot.startswith("R_"): return group_runners_up[slot[2:]]
        return "TBD"

    r16_winners = []
    for slot_a, slot_b in R16_BRACKET:
        team_a, team_b = resolve_slot(slot_a), resolve_slot(slot_b)
        r16_winners.append(_simulate_ko_match(team_a, team_b, "R16", ko_cache, rng))

    qf_winners = []
    for idx_a, idx_b in QF_BRACKET:
        qf_winners.append(_simulate_ko_match(r16_winners[idx_a], r16_winners[idx_b], "QF", ko_cache, rng))

    semifinalists = list(qf_winners)

    sf_winners = []
    for idx_a, idx_b in SF_BRACKET:
        sf_winners.append(_simulate_ko_match(qf_winners[idx_a], qf_winners[idx_b], "SF", ko_cache, rng))

    champion = _simulate_ko_match(sf_winners[0], sf_winners[1], "FINAL", ko_cache, rng)

    return {
        "group_winners": group_winners,
        "group_runners_up": group_runners_up,
        "semifinalists": semifinalists,
        "champion": champion,
    }


# ==============================================================================
# MONTE CARLO & REPORT
# ==============================================================================

def run_backtest(n_sims=10000, seed=2014, verbose=True):
    rng = random.Random(seed)
    originals = _inject_pre_wm2014_elo()
    if verbose:
        print("  🕐 Using pre-WM 2014 Elo ratings (eloratings.net, June 11 2014)", file=sys.stderr)

    group_winner_counts = {g: Counter() for g in WM2014_GROUPS}
    semifinal_counts = Counter()
    champion_counts = Counter()

    if verbose:
        print("  📊 Precomputing group match probability grids...", file=sys.stderr)

    t_cache = time.time()
    grid_cache = _build_group_grid_cache()
    ko_cache = {}
    if verbose:
        print(f"  ✅ Cache built in {time.time() - t_cache:.1f}s ({len(grid_cache)} grids)", file=sys.stderr)

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
        print(f"  ✅ {n_sims:,} simulations completed in {elapsed:.1f}s ({n_sims/elapsed:.0f}/s)     ",
              file=sys.stderr)

    _restore_elo(originals)

    return {
        "n_sims": n_sims,
        "group_winner_counts": group_winner_counts,
        "semifinal_counts": semifinal_counts,
        "champion_counts": champion_counts,
    }


def print_report(results):
    n_sims = results["n_sims"]
    group_winner_counts = results["group_winner_counts"]
    champion_counts = results["champion_counts"]
    semifinal_counts = results["semifinal_counts"]

    print()
    print("═" * 70)
    print("  ⚽ WM 2014 BACKTEST — MODEL VALIDATION REPORT")
    print(f"  🎲 {n_sims:,} Monte-Carlo-Simulationen | Pre-Tournament Elo")
    print(f"  📊 Source: eloratings.net, June 11, 2014")
    print("═" * 70)

    # ── 1. GROUP WINNERS ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  1. GROUP WINNER PREDICTIONS vs ACTUAL                       │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    correct_groups = 0
    for group in sorted(WM2014_GROUPS.keys()):
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
        extra = "" if match else f"  (actual: {actual} {actual_prob:.1f}%)"
        print(f"  │  {icon} Gr.{group}: Predicted {predicted:<14s} {prob:5.1f}%"
              f"  | Actual: {actual:<14s}{extra:>0s}")

    pct = correct_groups / 8 * 100
    print(f"  │                                                               │")
    print(f"  │  Score: {correct_groups}/8 correct ({pct:.0f}%){'':>35s}│")
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

    actual_prob = champion_counts.get(ACTUAL_CHAMPION, 0) / n_sims * 100
    actual_rank = next((i+1 for i, (t,_) in enumerate(champ_sorted) if t == ACTUAL_CHAMPION), -1)
    champ_icon = "✅" if champion_correct else "❌"
    print(f"  │                                                               │")
    print(f"  │  {champ_icon} Predicted: {predicted_champion:<14s}"
          f"| Actual: {ACTUAL_CHAMPION:<14s}({actual_prob:.1f}%, rank #{actual_rank})│")
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

    shown = set()
    for i, (team, count) in enumerate(sf_sorted[:8]):
        prob = count / n_sims * 100
        is_actual = team in ACTUAL_SF_TEAMS
        is_predicted = i < 4
        markers = []
        if is_predicted: markers.append("TIP")
        if is_actual: markers.append("ACTUAL ✅" if is_predicted else "ACTUAL")
        marker_str = " ◀ " + ", ".join(markers) if markers else ""
        rank_marker = "★" if i < 4 else " "
        bar = "█" * int(prob / 3) + "░" * (20 - int(prob / 3))
        print(f"  │  {rank_marker} {team:<18s} {prob:5.1f}%  {bar}{marker_str:>0s}")
        shown.add(team)

    for team in sorted(ACTUAL_SF_TEAMS):
        if team not in shown:
            prob = semifinal_counts.get(team, 0) / n_sims * 100
            print(f"  │    {team:<18s} {prob:5.1f}%  (actual SF, not in top 8)")

    print(f"  │                                                               │")
    print(f"  │  Overlap: {sf_overlap_count}/4 actual semifinalists predicted{'':>23s}│")
    if sf_overlap:
        print(f"  │  Matched: {', '.join(sorted(sf_overlap)):>48s}  │")
    missed = ACTUAL_SF_TEAMS - predicted_sf
    if missed:
        print(f"  │  Missed:  {', '.join(sorted(missed)):>48s}  │")
    print("  └───────────────────────────────────────────────────────────────┘")

    # ── 4. OVERALL ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  4. OVERALL ACCURACY SCORE                                   │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    group_score = correct_groups / 8
    champion_score = 1.0 if champion_correct else 0.0
    sf_score = sf_overlap_count / 4.0
    overall = group_score * 0.40 + champion_score * 0.30 + sf_score * 0.30
    overall_pct = overall * 100

    print(f"  │                                                               │")
    print(f"  │  Group Winners:    {correct_groups}/8"
          f"  ({group_score*100:5.1f}%) × 40% = {group_score*0.40*100:5.1f}%       │")
    print(f"  │  Champion:         {'✅' if champion_correct else '❌'}    "
          f"  ({champion_score*100:5.1f}%) × 30% = {champion_score*0.30*100:5.1f}%       │")
    print(f"  │  Semifinalists:    {sf_overlap_count}/4 "
          f"  ({sf_score*100:5.1f}%) × 30% = {sf_score*0.30*100:5.1f}%       │")
    print(f"  │{'─'*63}│")

    if overall_pct >= 80: grade = "A"
    elif overall_pct >= 65: grade = "B"
    elif overall_pct >= 50: grade = "C"
    elif overall_pct >= 35: grade = "D"
    else: grade = "F"

    bar = "█" * int(overall_pct / 2.5) + "░" * (40 - int(overall_pct / 2.5))
    print(f"  │  OVERALL: {overall_pct:5.1f}%  Grade: {grade}{'':>37s}│")
    print(f"  │  {bar}  │")
    print("  └───────────────────────────────────────────────────────────────┘")

    # ── 5. UPSETS ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  5. NOTABLE UPSETS / SURPRISES                               │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    for group in sorted(WM2014_GROUPS.keys()):
        counts = group_winner_counts[group]
        total = sum(counts.values())
        actual = ACTUAL_GROUP_WINNERS[group]
        predicted = counts.most_common(1)[0][0]
        if predicted != actual:
            pred_prob = counts.most_common(1)[0][1] / total * 100
            actual_prob = counts.get(actual, 0) / total * 100
            print(f"  │  🔥 Group {group}: Expected {predicted} ({pred_prob:.0f}%),"
                  f" got {actual} ({actual_prob:.0f}%)")

    surprise_sf = ACTUAL_SF_TEAMS - predicted_sf
    for team in sorted(surprise_sf):
        prob = semifinal_counts.get(team, 0) / n_sims * 100
        print(f"  │  🔥 {team} made SF (model gave {prob:.1f}% chance)")

    if not surprise_sf and correct_groups == 8:
        print(f"  │  No major upsets — model captured the tournament well!       │")

    print("  └───────────────────────────────────────────────────────────────┘")

    # ── 6. CROSS-TOURNAMENT ──
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  6. CROSS-TOURNAMENT COMPARISON (all pre-tournament Elo)     │")
    print("  ├───────────────────────────────────────────────────────────────┤")
    print(f"  │  {'Metric':<22s} {'WM 2014':>8s}  {'WM 2018':>8s}  {'WM 2022':>8s}   │")
    print(f"  │  {'─'*55}│")
    print(f"  │  {'Groups correct':<22s} {correct_groups}/8{'':<6s}  5/8{'':<6s}  6/8{'':<6s}   │")
    print(f"  │  {'Champion correct':<22s} {'✅' if champion_correct else '❌':<8s}  ❌{'':<6s}  ❌{'':<6s}   │")
    print(f"  │  {'SF overlap':<22s} {sf_overlap_count}/4{'':<6s}  1/4{'':<6s}  1/4{'':<6s}   │")
    print(f"  │  {'Overall grade':<22s} {grade:<8s}  F{'':<6s}   D{'':<6s}   │")
    print("  └───────────────────────────────────────────────────────────────┘")
    print()


def main():
    parser = argparse.ArgumentParser(description="WM 2014 Backtest")
    parser.add_argument("--sims", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=2014)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet:
        print()
        print("🏆 WM 2014 BACKTEST — Validating predictor engine")
        print(f"   Simulations: {args.sims:,} | Seed: {args.seed}")
        print(f"   Elo Source: eloratings.net (June 11, 2014 — pre-tournament)")
        print()

    results = run_backtest(n_sims=args.sims, seed=args.seed, verbose=not args.quiet)
    print_report(results)


if __name__ == "__main__":
    main()
