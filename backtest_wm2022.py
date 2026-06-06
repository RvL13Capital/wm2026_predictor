#!/usr/bin/env python3
"""
WM 2022 Backtest — Monte Carlo Tournament Simulation

Validates the predictor engine against the actual FIFA World Cup 2022 results.
Simulates the 32-team tournament N times using Elo-based Poisson model
and compares predictions against what actually happened.

Usage:
    python3 backtest_wm2022.py                  # Default 10,000 sims, seed=2022
    python3 backtest_wm2022.py --sims 50000     # More sims for precision
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
# WM 2022 GROUPS (32 teams, 8 groups × 4 teams)
# ==============================================================================

WM2022_GROUPS = {
    "A": ["Qatar", "Ecuador", "Senegal", "Netherlands"],
    "B": ["England", "Iran", "USA", "Wales"],
    "C": ["Argentina", "Saudi Arabia", "Mexico", "Poland"],
    "D": ["France", "Australia", "Denmark", "Tunisia"],
    "E": ["Spain", "Costa Rica", "Germany", "Japan"],
    "F": ["Belgium", "Canada", "Morocco", "Croatia"],
    "G": ["Brazil", "Serbia", "Switzerland", "Cameroon"],
    "H": ["Portugal", "Ghana", "Uruguay", "South Korea"],
}

# ==============================================================================
# ACTUAL WM 2022 RESULTS (ground truth)
# ==============================================================================

ACTUAL_GROUP_WINNERS = {
    "A": "Netherlands",
    "B": "England",
    "C": "Argentina",
    "D": "France",
    "E": "Japan",
    "F": "Morocco",
    "G": "Brazil",
    "H": "Portugal",
}

ACTUAL_GROUP_RUNNERS_UP = {
    "A": "Senegal",
    "B": "USA",
    "C": "Poland",
    "D": "Australia",
    "E": "Spain",
    "F": "Croatia",
    "G": "Switzerland",
    "H": "South Korea",
}

ACTUAL_QF_TEAMS = {
    "Netherlands", "Argentina", "Croatia", "Brazil",
    "England", "France", "Morocco", "Portugal",
}

ACTUAL_SF_TEAMS = {"Argentina", "Croatia", "France", "Morocco"}

ACTUAL_CHAMPION = "Argentina"
ACTUAL_RUNNER_UP = "France"

# ==============================================================================
# R16 BRACKET FOR WM 2022 (fixed, standard 32-team bracket)
# ==============================================================================
# 1A vs 2B, 1C vs 2D, 1E vs 2F, 1G vs 2H  (left half)
# 1B vs 2A, 1D vs 2C, 1F vs 2E, 1H vs 2G  (right half)

R16_BRACKET_2022 = [
    # Left half
    ("W_A", "R_B"),  # M49: 1A vs 2B
    ("W_C", "R_D"),  # M50: 1C vs 2D
    ("W_E", "R_F"),  # M51: 1E vs 2F
    ("W_G", "R_H"),  # M52: 1G vs 2H
    # Right half
    ("W_B", "R_A"),  # M53: 1B vs 2A
    ("W_D", "R_C"),  # M54: 1D vs 2C
    ("W_F", "R_E"),  # M55: 1F vs 2E
    ("W_H", "R_G"),  # M56: 1H vs 2G
]

# QF pairings (R16 winners, 0-indexed):
# QF1: W(M49) vs W(M50)  → idx 0 vs 1
# QF2: W(M51) vs W(M52)  → idx 2 vs 3
# QF3: W(M53) vs W(M54)  → idx 4 vs 5
# QF4: W(M55) vs W(M56)  → idx 6 vs 7
QF_BRACKET_2022 = [(0, 1), (2, 3), (4, 5), (6, 7)]

# SF pairings:
# SF1: W(QF1) vs W(QF2)  → idx 0 vs 1
# SF2: W(QF3) vs W(QF4)  → idx 2 vs 3
SF_BRACKET_2022 = [(0, 1), (2, 3)]

# ==============================================================================
# PRE-WM 2022 ELO RATINGS (November 2022, BEFORE tournament)
# ==============================================================================
# CRITICAL: Using post-WC Elo creates hindsight bias (e.g. Argentina's Elo
# rose +350 after winning WM 2022). These values approximate the actual
# pre-tournament Elo based on FIFA Rankings and historical data.
# Sources: eloratings.net November 2022 snapshot, FIFA Rankings October 2022

PRE_WM2022_ELO = {
    "Brazil":       {"elo": 2169, "rank": 1},   # #1 FIFA Ranking
    "Belgium":      {"elo": 2048, "rank": 2},   # #2 — Golden Generation peak
    "Argentina":    {"elo": 1773, "rank": 3},   # #3 — Copa America champ but lower Elo
    "France":       {"elo": 2048, "rank": 4},   # #4 — Defending champions
    "England":      {"elo": 1969, "rank": 5},   # #5
    "Spain":        {"elo": 1920, "rank": 7},   # #7 — Nations League winners
    "Netherlands":  {"elo": 1812, "rank": 8},   # #8 — Returning after missing 2018
    "Portugal":     {"elo": 1838, "rank": 9},   # #9
    "Denmark":      {"elo": 1816, "rank": 10},  # #10 — Euro 2020 SF
    "Germany":      {"elo": 1959, "rank": 11},  # #11 — Elo higher than FIFA rank
    "Croatia":      {"elo": 1748, "rank": 12},  # #12 — 2018 finalist
    "Mexico":       {"elo": 1741, "rank": 13},  # #13
    "Uruguay":      {"elo": 1757, "rank": 14},  # #14
    "Switzerland":  {"elo": 1649, "rank": 15},  # #15
    "USA":          {"elo": 1644, "rank": 16},  # #16
    "Senegal":      {"elo": 1625, "rank": 18},  # #18 — AFCON champion
    "Iran":         {"elo": 1601, "rank": 20},  # #20
    "Wales":        {"elo": 1618, "rank": 19},  # #19 — First WC since 1958
    "Serbia":       {"elo": 1715, "rank": 21},  # #21
    "Morocco":      {"elo": 1598, "rank": 22},  # #22 — Pre-breakout
    "Japan":        {"elo": 1559, "rank": 24},  # #24
    "Poland":       {"elo": 1678, "rank": 26},  # #26
    "South Korea":  {"elo": 1558, "rank": 28},  # #28
    "Tunisia":      {"elo": 1584, "rank": 30},  # #30
    "Costa Rica":   {"elo": 1548, "rank": 31},  # #31
    "Australia":    {"elo": 1529, "rank": 38},  # #38
    "Canada":       {"elo": 1544, "rank": 41},  # #41 — First WC since 1986
    "Cameroon":     {"elo": 1533, "rank": 43},  # #43
    "Ecuador":      {"elo": 1632, "rank": 44},  # #44 — Elo above FIFA rank
    "Saudi Arabia": {"elo": 1502, "rank": 51},  # #51
    "Ghana":        {"elo": 1542, "rank": 61},  # #61
    "Qatar":        {"elo": 1462, "rank": 50},  # #50 — Host, but weak
}


# ==============================================================================
# SIMULATION ENGINE (32-team format)
# ==============================================================================

def _inject_pre_wm2022_elo():
    """
    Temporarily override ALL team Elo values with pre-WM-2022 ratings.
    Returns dict of original values for restoration.
    """
    originals = {}
    for team, data in PRE_WM2022_ELO.items():
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
            # Was newly added, remove it
            if team in predictor.WORLD_CUP_2026_TEAMS:
                del predictor.WORLD_CUP_2026_TEAMS[team]
        else:
            predictor.WORLD_CUP_2026_TEAMS[team] = orig_data


def _build_group_grid_cache() -> dict:
    """
    Precompute probability grids for all WM 2022 group stage matches.
    Uses Elo-only (no market odds, no host advantage — Qatar was host but
    we skip that for simplicity since it doesn't affect validation much).
    """
    cache = {}

    for group_name, teams in WM2022_GROUPS.items():
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


def _sample_from_grid(flat: list, cum_weights: list, rng: random.Random) -> Tuple[int, int]:
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


def _get_ko_grid(team_a: str, team_b: str, phase: str, ko_cache: dict) -> Tuple[list, list]:
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


def _simulate_ko_match(team_a: str, team_b: str, phase: str,
                       ko_cache: dict, rng: random.Random) -> str:
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


def simulate_group(group_name: str, teams: List[str],
                   grid_cache: dict, rng: random.Random) -> List[dict]:
    """
    Simulate all 6 matches in a 4-team group.
    Returns list of dicts sorted by: points, goal_diff, goals_for, Elo (descending).
    """
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
                # Try reverse order
                key_rev = (team_b, team_a)
                if key_rev in grid_cache:
                    flat, cum_weights = grid_cache[key_rev]
                    gb, ga = _sample_from_grid(flat, cum_weights, rng)
                else:
                    ga, gb = 1, 0  # Fallback

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


def simulate_tournament(grid_cache: dict, ko_cache: dict,
                        rng: random.Random) -> dict:
    """
    Simulate the entire WM 2022 tournament once.
    32-team format: 8 groups × 4, top 2 advance, fixed R16 bracket.
    """
    # ── GROUP STAGE ──
    group_winners = {}
    group_runners_up = {}

    for group_name, teams in WM2022_GROUPS.items():
        standings = simulate_group(group_name, teams, grid_cache, rng)
        group_winners[group_name] = standings[0]["team"]
        group_runners_up[group_name] = standings[1]["team"]

    # ── ROUND OF 16 ──
    def resolve_slot(slot: str) -> str:
        if slot.startswith("W_"):
            return group_winners[slot[2:]]
        elif slot.startswith("R_"):
            return group_runners_up[slot[2:]]
        return "TBD"

    r16_winners = []
    for slot_a, slot_b in R16_BRACKET_2022:
        team_a = resolve_slot(slot_a)
        team_b = resolve_slot(slot_b)
        winner = _simulate_ko_match(team_a, team_b, "R16", ko_cache, rng)
        r16_winners.append(winner)

    # ── QUARTERFINALS ──
    qf_winners = []
    for idx_a, idx_b in QF_BRACKET_2022:
        team_a = r16_winners[idx_a]
        team_b = r16_winners[idx_b]
        winner = _simulate_ko_match(team_a, team_b, "QF", ko_cache, rng)
        qf_winners.append(winner)

    semifinalists = list(qf_winners)

    # ── SEMIFINALS ──
    sf_winners = []
    for idx_a, idx_b in SF_BRACKET_2022:
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

def run_backtest(n_sims: int = 10000, seed: int = 2022, verbose: bool = True) -> dict:
    """Run N full WM 2022 tournament simulations and aggregate results."""
    rng = random.Random(seed)

    # Inject pre-WM 2022 Elo values (removes hindsight bias)
    originals = _inject_pre_wm2022_elo()
    if verbose:
        print("  🕐 Using pre-WM 2022 Elo ratings (no hindsight bias)", file=sys.stderr)

    # Counters
    group_winner_counts = {g: Counter() for g in WM2022_GROUPS}
    group_runner_up_counts = {g: Counter() for g in WM2022_GROUPS}
    semifinal_counts = Counter()
    champion_counts = Counter()
    finalist_counts = Counter()
    qf_counts = Counter()  # Track QF teams via semifinalists + losers

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

        # Group winners / runners-up
        for group, winner in result["group_winners"].items():
            group_winner_counts[group][winner] += 1
        for group, runner_up in result["group_runners_up"].items():
            group_runner_up_counts[group][runner_up] += 1

        # Semifinalists
        for team in result["semifinalists"]:
            semifinal_counts[team] += 1

        # Finalists
        for team in result["finalists"]:
            finalist_counts[team] += 1

        # Champion
        champion_counts[result["champion"]] += 1

        # Progress
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
        "group_runner_up_counts": group_runner_up_counts,
        "semifinal_counts": semifinal_counts,
        "champion_counts": champion_counts,
        "finalist_counts": finalist_counts,
    }


def print_report(results: dict):
    """Print a comprehensive backtest report card."""
    n_sims = results["n_sims"]
    group_winner_counts = results["group_winner_counts"]
    champion_counts = results["champion_counts"]
    semifinal_counts = results["semifinal_counts"]

    print()
    print("═" * 70)
    print("  ⚽ WM 2022 BACKTEST — MODEL VALIDATION REPORT")
    print(f"  🎲 {n_sims:,} Monte-Carlo-Simulationen | Seed=2022")
    print("═" * 70)

    # ──────────────────────────────────────────────────────────────────────
    # 1. GROUP WINNER PREDICTIONS vs ACTUAL
    # ──────────────────────────────────────────────────────────────────────
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  1. GROUP WINNER PREDICTIONS vs ACTUAL                       │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    correct_groups = 0
    total_groups = 8

    for group in sorted(WM2022_GROUPS.keys()):
        counts = group_winner_counts[group]
        total = sum(counts.values())
        predicted = counts.most_common(1)[0][0]
        prob = counts.most_common(1)[0][1] / total * 100
        actual = ACTUAL_GROUP_WINNERS[group]
        match = predicted == actual
        icon = "✅" if match else "❌"
        if match:
            correct_groups += 1

        # Show actual team's probability if different from predicted
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

    # ──────────────────────────────────────────────────────────────────────
    # 2. CHAMPION PREDICTION (Top 5 probabilities)
    # ──────────────────────────────────────────────────────────────────────
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  2. CHAMPION PREDICTION (Top 5)                              │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    champ_sorted = champion_counts.most_common()
    predicted_champion = champ_sorted[0][0]
    champion_correct = predicted_champion == ACTUAL_CHAMPION

    for i, (team, count) in enumerate(champ_sorted[:5]):
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

    # ──────────────────────────────────────────────────────────────────────
    # 3. SEMIFINALIST OVERLAP
    # ──────────────────────────────────────────────────────────────────────
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  3. SEMIFINALIST PREDICTION                                  │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    sf_sorted = semifinal_counts.most_common()
    predicted_sf = set(t for t, _ in sf_sorted[:4])
    sf_overlap = predicted_sf & ACTUAL_SF_TEAMS
    sf_overlap_count = len(sf_overlap)

    for i, (team, count) in enumerate(sf_sorted[:8]):
        prob = count / n_sims * 100
        is_actual = team in ACTUAL_SF_TEAMS
        is_predicted = i < 4
        markers = []
        if is_predicted:
            markers.append("TIP")
        if is_actual:
            markers.append("ACTUAL ✅" if is_predicted else "ACTUAL ❌")
        marker_str = " ◀ " + ", ".join(markers) if markers else ""
        rank_marker = "★" if i < 4 else " "
        bar = "█" * int(prob / 3) + "░" * (20 - int(prob / 3))
        print(f"  │  {rank_marker} {team:<18s} {prob:5.1f}%  {bar}{marker_str:>0s}")

    # Show actual SF teams not in top 8 prediction
    for team in sorted(ACTUAL_SF_TEAMS):
        if team not in dict(sf_sorted[:8]):
            prob = semifinal_counts.get(team, 0) / n_sims * 100
            print(f"  │    {team:<18s} {prob:5.1f}%  (actual SF, not in top 8 predicted)")

    print(f"  │                                                               │")
    print(f"  │  Overlap: {sf_overlap_count}/4 actual semifinalists predicted"
          f"{'':>23s}│")
    if sf_overlap:
        print(f"  │  Matched: {', '.join(sorted(sf_overlap)):>48s}  │")
    missed = ACTUAL_SF_TEAMS - predicted_sf
    if missed:
        print(f"  │  Missed:  {', '.join(sorted(missed)):>48s}  │")
    print("  └───────────────────────────────────────────────────────────────┘")

    # ──────────────────────────────────────────────────────────────────────
    # 4. OVERALL ACCURACY SCORE
    # ──────────────────────────────────────────────────────────────────────
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  4. OVERALL ACCURACY SCORE                                   │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    # Scoring breakdown:
    # - Group winners: X/8 correct (weight: 40%)
    # - Champion: 1 if correct, 0 if wrong (weight: 30%)
    # - Semifinalists: X/4 overlap (weight: 30%)
    group_score = correct_groups / total_groups
    champion_score = 1.0 if champion_correct else 0.0
    sf_score = sf_overlap_count / 4.0

    # Weighted overall
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

    # Grade
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

    # ──────────────────────────────────────────────────────────────────────
    # 5. NOTABLE UPSETS (Elo model vs reality)
    # ──────────────────────────────────────────────────────────────────────
    print()
    print("  ┌───────────────────────────────────────────────────────────────┐")
    print("  │  5. NOTABLE UPSETS / SURPRISES                               │")
    print("  ├───────────────────────────────────────────────────────────────┤")

    upsets = []
    for group in sorted(WM2022_GROUPS.keys()):
        counts = group_winner_counts[group]
        total = sum(counts.values())
        actual = ACTUAL_GROUP_WINNERS[group]
        actual_prob = counts.get(actual, 0) / total * 100
        predicted = counts.most_common(1)[0][0]
        if predicted != actual:
            pred_prob = counts.most_common(1)[0][1] / total * 100
            upsets.append((group, predicted, pred_prob, actual, actual_prob))

    if upsets:
        for group, pred, pred_prob, actual, actual_prob in upsets:
            print(f"  │  🔥 Group {group}: Expected {pred} ({pred_prob:.0f}%),"
                  f" got {actual} ({actual_prob:.0f}%)")
    else:
        print(f"  │  No group winner upsets — model predicted all correctly!   │")

    # Surprise semifinalists
    surprise_sf = ACTUAL_SF_TEAMS - predicted_sf
    if surprise_sf:
        for team in sorted(surprise_sf):
            prob = semifinal_counts.get(team, 0) / n_sims * 100
            print(f"  │  🔥 {team} made SF (model gave {prob:.1f}% chance)")

    print("  └───────────────────────────────────────────────────────────────┘")
    print()


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="WM 2022 Backtest — Validate predictor against actual results"
    )
    parser.add_argument("--sims", type=int, default=10000,
                        help="Number of Monte Carlo simulations (default: 10000)")
    parser.add_argument("--seed", type=int, default=2022,
                        help="Random seed (default: 2022)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress progress output")
    args = parser.parse_args()

    verbose = not args.quiet

    if verbose:
        print()
        print("🏆 WM 2022 BACKTEST — Validating predictor engine")
        print(f"   Simulations: {args.sims:,} | Seed: {args.seed}")
        print()

    results = run_backtest(n_sims=args.sims, seed=args.seed, verbose=verbose)
    print_report(results)


if __name__ == "__main__":
    main()
