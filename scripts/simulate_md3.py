#!/usr/bin/env python3
"""Simulate the remaining group games (round 3 / MD3) and their qualification consequences.

Purpose-built, transparent Monte Carlo over the ENGINE's MD3 score grids (full stack: Elo + squad
VORP + injury + context + the validated MD3 ×0.87 trim; NO market blend). For each of N sims it
samples every round-3 scoreline, completes all 12 group tables on top of the real played results,
applies the actual 48-team rules (group order by Pts·GD·GF·drawing-of-lots; top 2 per group + the 8
best third-placed teams advance to the Round of 32), and tallies per team:

  P(win group) · P(top-2) · P(best-3rd advance) · P(advance overall) · P(eliminated) · final-position mix

This complements vectorized_mc (which runs the whole tournament but doesn't expose per-team
advancement). It is read-only and self-contained. Verified by construction: exactly 32 teams advance
every sim (12 winners + 12 runners-up + 8 thirds), asserted below.

    python3 scripts/simulate_md3.py [--sims 100000] [--seed 42] [--output ...]
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matchday_tips as mt
import scripts.group_standings as gs
from tournament_bonusfragen import GROUPS


def build():
    """Return team index maps, base (pts/gd/gf) from played games, and the 24 MD3 match grids."""
    teams = [t for ts in GROUPS.values() for t in ts]
    idx = {t: i for i, t in enumerate(teams)}
    grp = {t: g for g, ts in GROUPS.items() for t in ts}
    ls = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "data", "live_state.json")))
    tables = gs.compute_tables(ls)
    base = np.zeros((len(teams), 3))                 # pts, gd, gf
    for g, lst in tables.items():
        for r in lst:
            base[idx[r["team"]]] = [r["Pts"], r["GD"], r["GF"]]
    # MD3 grids from the canonical pipeline (analytic; no market)
    res = mt.run_matchday(3, n_simulations=0, seed=42, market_probs=None)
    matches = []
    for r in res:
        grid = r["grid"]
        cells = [(a, b, grid[a][b]) for a in grid for b in grid[a] if grid[a][b] > 0]
        sa = np.array([c[0] for c in cells]); sb = np.array([c[1] for c in cells])
        p = np.array([c[2] for c in cells]); p = p / p.sum()
        matches.append((idx[r["team_a"]], idx[r["team_b"]], sa, sb, p))
    return teams, idx, grp, base, matches


def simulate(sims, seed):
    teams, idx, grp, base, matches = build()
    rng = np.random.default_rng(seed)
    nT = len(teams)
    pts = np.tile(base[:, 0], (sims, 1)).astype(float)
    gd = np.tile(base[:, 1], (sims, 1)).astype(float)
    gf = np.tile(base[:, 2], (sims, 1)).astype(float)
    for ia, ib, sa, sb, p in matches:
        pick = rng.choice(len(p), size=sims, p=p)
        ga, gb = sa[pick], sb[pick]
        gf[:, ia] += ga; gf[:, ib] += gb
        gd[:, ia] += ga - gb; gd[:, ib] += gb - ga
        pts[:, ia] += np.where(ga > gb, 3, np.where(ga == gb, 1, 0))
        pts[:, ib] += np.where(gb > ga, 3, np.where(ga == gb, 1, 0))
    # composite ranking key: Pts ≫ GD ≫ GF ≫ random lots (the FIFA primary order)
    lots = rng.random((sims, nT))
    key = pts * 1e6 + (gd + 100.0) * 1e3 + gf * 10.0 + lots   # higher = better

    win = np.zeros(nT); top2 = np.zeros(nT); third_adv = np.zeros(nT)
    pos_counts = {t: [0, 0, 0, 0] for t in teams}             # 1st..4th within group
    third_keys = np.full((sims, 12), -1.0)
    third_team = np.full((sims, 12), -1, dtype=int)
    for gi, (g, ts) in enumerate(GROUPS.items()):
        ti = [idx[t] for t in ts]
        gk = key[:, ti]                                       # (sims,4)
        order = np.argsort(-gk, axis=1)                       # positions: order[:,0]=winner idx in ts
        winner = np.array(ti)[order[:, 0]]
        second = np.array(ti)[order[:, 1]]
        third = np.array(ti)[order[:, 2]]
        win[winner] += 0  # placeholder (counted below per sim via bincount)
        np.add.at(win, winner, 1)
        np.add.at(top2, winner, 1); np.add.at(top2, second, 1)
        for posj in range(4):
            tt = np.array(ti)[order[:, posj]]
            for t in ts:
                pos_counts[t][posj] += int(np.sum(tt == idx[t]))
        # capture this group's third for the cross-group best-8 race
        third_keys[:, gi] = key[np.arange(sims), third]
        third_team[:, gi] = third
    # best 8 thirds per sim
    best8 = np.argsort(-third_keys, axis=1)[:, :8]            # (sims,8) group columns
    adv_third_teams = np.take_along_axis(third_team, best8, axis=1)
    for col in range(8):
        np.add.at(third_adv, adv_third_teams[:, col], 1)

    advance = top2 + third_adv
    # invariant: exactly 32 advance per sim on average (12+12+8)
    assert abs(advance.sum() / sims - 32.0) < 1e-6, advance.sum() / sims

    rows = []
    for t in teams:
        i = idx[t]
        rows.append({
            "team": t, "group": grp[t],
            "P_win": win[i] / sims, "P_top2": top2[i] / sims,
            "P_3rd_adv": third_adv[i] / sims, "P_advance": advance[i] / sims,
            "P_out": 1.0 - advance[i] / sims,
            "pos": [c / sims for c in pos_counts[t]],
        })
    return rows


def render(rows, sims):
    by_group = {}
    for r in rows:
        by_group.setdefault(r["group"], []).append(r)
    L = [f"  SIMULATING THE NEXT GAMES — round-3 group completion ({sims:,} sims, pure model, no market)",
         "  P(win) / P(top-2) / P(3rd→adv) / P(ADVANCE) / P(out)   per team", ""]
    for g in sorted(by_group):
        lst = sorted(by_group[g], key=lambda r: -r["P_advance"])
        L.append(f"── Group {g} " + "─" * 40)
        for r in lst:
            bar = "█" * round(r["P_advance"] * 20)
            L.append(f"   {r['team']:<14} win {r['P_win']*100:5.1f}  top2 {r['P_top2']*100:5.1f}  "
                     f"3rd→ {r['P_3rd_adv']*100:4.1f}  ADV {r['P_advance']*100:5.1f}%  out {r['P_out']*100:5.1f}  {bar}")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=100000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    rows = simulate(args.sims, args.seed)
    txt = render(rows, args.sims)
    if args.json_out:
        json.dump(rows, open(args.json_out, "w"), ensure_ascii=False, indent=1)
    if args.output:
        open(args.output, "w", encoding="utf-8").write(txt + "\n")
        print(f"wrote {args.output}")
    else:
        print(txt)


if __name__ == "__main__":
    main()
