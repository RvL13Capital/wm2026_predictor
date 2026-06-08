#!/usr/bin/env python3
"""
2026-format MD3 stakes backtest on Euro 2020 + 2024 (24-team: 6 groups of 4, top-2 + best-4-of-6
thirds advance). This is the advancement math that mirrors 2026's best-8-of-12-thirds — unlike the
32-team World Cups we already backtested (top-2 only), where finishing 3rd is always elimination.

Two questions, both Elo-FREE (each tournament is its own baseline, so no dependency on sourcing
historical Euro Elo — the regime signal is in goals/draws relative to the tournament's own rate):

  (1) FLAT TRIM: does MD3 as a whole score below MD1-2 (the basis for the production 0.87x trim),
      and by how much, in the 24-team format? Pooled 48 MD3 vs 96 earlier matches — the robust line.
  (2) REGIME: within MD3, do mutual-comfort / dead-rubber games suppress goals & inflate draws more
      than win-or-bust games — enough to justify regime-specific modifiers over one flat trim?

Stakes are read off the frozen post-MD2 table. Because best-4-thirds safety depends on other groups,
we use a points heuristic tuned to the format (3 pts usually advances as a third), not strict
cross-group math — and flag the tiny per-bucket N. Output: validation/euro_md3_backtest.txt
"""
import csv
import os
import sys
from collections import defaultdict

TOURNAMENTS = [2020, 2024]
BLOWOUT = 3   # |goal margin| >= 3


def load(year):
    path = os.path.join(os.path.dirname(__file__), "..", "data", f"euro{year}_results.csv")
    return list(csv.DictReader(open(path)))


def standings_after(rows, group, upto_md):
    """pts/gd/gf per team in `group`, counting only matchdays <= upto_md."""
    tab = defaultdict(lambda: {"pts": 0, "gd": 0, "gf": 0})
    for r in rows:
        if r["group"] != group or int(r["matchday"]) > upto_md:
            continue
        ga, gb = int(r["goals_a"]), int(r["goals_b"])
        a, b = r["team_a"], r["team_b"]
        tab[a]["gf"] += ga; tab[a]["gd"] += ga - gb
        tab[b]["gf"] += gb; tab[b]["gd"] += gb - ga
        if ga > gb:
            tab[a]["pts"] += 3
        elif gb > ga:
            tab[b]["pts"] += 3
        else:
            tab[a]["pts"] += 1; tab[b]["pts"] += 1
    return tab


def _safe(pts, gd):
    """Best-4-thirds heuristic: >=4 pts is almost always through; 3 pts with gd>=0 usually makes
    the third-place cut. This 'a third can advance' softness is the whole point vs 32-team top-2."""
    return pts >= 4 or (pts == 3 and gd >= 0)


def _out(pts):
    """0 pts after two games never makes best-4-thirds."""
    return pts == 0


def regime(sa, sb):
    a_safe, b_safe = _safe(*sa), _safe(*sb)
    if _out(sa[0]) or _out(sb[0]):
        return "DEAD_RUBBER"           # >=1 team cannot advance
    if a_safe and b_safe:
        return "MUTUAL_COMFORT"        # both already through -> a draw suits both, low stakes
    if a_safe or b_safe:
        return "ONE_SAFE"              # one coasting, one fighting
    return "WIN_OR_BUST"               # both still need a result


def main():
    md3_goals, early_goals = [], []
    bucket = defaultdict(list)         # regime -> [(total_goals, is_draw, is_blowout), ...]
    for year in TOURNAMENTS:
        rows = load(year)
        for r in rows:
            tot = int(r["goals_a"]) + int(r["goals_b"])
            (md3_goals if int(r["matchday"]) == 3 else early_goals).append(tot)
        for r in rows:
            if int(r["matchday"]) != 3:
                continue
            tab = standings_after(rows, r["group"], 2)       # frozen post-MD2 table
            sa = (tab[r["team_a"]]["pts"], tab[r["team_a"]]["gd"])
            sb = (tab[r["team_b"]]["pts"], tab[r["team_b"]]["gd"])
            ga, gb = int(r["goals_a"]), int(r["goals_b"])
            bucket[regime(sa, sb)].append((ga + gb, ga == gb, abs(ga - gb) >= BLOWOUT))

    lines = []
    def emit(s=""):
        lines.append(s); print(s)

    early_gpg = sum(early_goals) / len(early_goals)
    md3_gpg = sum(md3_goals) / len(md3_goals)
    emit("=" * 72)
    emit("EURO 2020+2024 MD3 STAKES BACKTEST — 24-team format (best-4-of-6 thirds advance)")
    emit("=" * 72)
    emit("(1) FLAT TRIM CHECK — does MD3 suppress goals vs MD1-2?  [the robust line]")
    emit(f"  MD1-2 goals/game : {early_gpg:.3f}   (n={len(early_goals)})")
    emit(f"  MD3   goals/game : {md3_gpg:.3f}   (n={len(md3_goals)})")
    emit(f"  implied MD3 trim : {md3_gpg / early_gpg:.3f}x    (production uses a flat 0.87x)")
    emit("")
    emit("(2) REGIME BREAKDOWN within MD3 (baseline = MD3 average):")
    hdr = f"  {'regime':<15} {'N':>3} {'goals/gm':>9} {'vs MD3avg':>10} {'draw%':>7} {'blowout%':>9}"
    emit(hdr)
    emit("  " + "-" * (len(hdr) - 2))
    for reg in ["MUTUAL_COMFORT", "ONE_SAFE", "WIN_OR_BUST", "DEAD_RUBBER"]:
        b = bucket.get(reg, [])
        if not b:
            emit(f"  {reg:<15} {0:>3}        --")
            continue
        n = len(b)
        gpg = sum(x[0] for x in b) / n
        draw = sum(x[1] for x in b) / n * 100
        blow = sum(x[2] for x in b) / n * 100
        emit(f"  {reg:<15} {n:>3} {gpg:>9.2f} {gpg / md3_gpg:>9.2f}x {draw:>6.0f}% {blow:>8.0f}%")
    emit("")
    emit("CAVEAT: 24 MD3 matches across 4 buckets => single-digit N per regime. Treat the regime")
    emit("rows as DIRECTIONAL only; best-4-thirds safety is a points heuristic, not strict")
    emit("cross-group math. The FLAT TRIM line (n=48 vs 96) is the load-bearing result.")
    emit("=" * 72)

    path = os.path.join(os.path.dirname(__file__), "euro_md3_backtest.txt")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n💾 wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
