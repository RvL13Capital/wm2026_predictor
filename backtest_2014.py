#!/usr/bin/env python3
"""
2014 World Cup backtest — model tips vs the actual results, from pre-2014 (June 2014) Elo,
no lookahead. Shows the EV-optimal tip (what you'd actually submit to a Kicktipp pool) for
each of the 64 real fixtures next to the actual score, and compares aggregate Kicktipp points
(4/3/2) against the draw-heavy most-likely-score prediction. Output: validation/backtest_2014.txt
"""
import os, sys, csv
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictor
import backtest_wm2014 as w14
from make_bracket_html import modal

ELO = w14.PRE_WM2014_ELO


def elo(t):
    return ELO.get(t, {}).get("elo", 1500)


def grid(a, b):
    return predictor.predict_single_match({"team_a": a, "team_b": b, "elo_a": elo(a), "elo_b": elo(b)})["grid"]


def ev_tip(g):
    tips, _, _ = predictor.solve_optimal_tip_from_grid(g, max_tip=6, pts_exact=4, pts_diff=3, pts_tend=2)
    return tips[0][0]


def main():
    t2g = {t: gg for gg, ts in w14.WM2014_GROUPS.items() for t in ts}
    rows = list(csv.DictReader(open("data/wc2014_results.csv")))
    out = []
    def emit(s=""):
        out.append(s); print(s)

    emit("=" * 72)
    emit("WORLD CUP 2014 BACKTEST — EV-optimal tip vs ACTUAL  (pre-2014 Elo, no lookahead)")
    emit("=" * 72)

    groups, ko = defaultdict(list), []
    agg = {"ev": [0, {4: 0, 3: 0, 2: 0, 0: 0}, 0], "modal": [0, {4: 0, 3: 0, 2: 0, 0: 0}, 0]}
    for r in rows:
        a, b = r["team_a"], r["team_b"]; ga, gb = int(r["goals_a"]), int(r["goals_b"])
        g = grid(a, b); tx, ty = ev_tip(g); mx, my = modal(g)
        for key, (px, py) in (("ev", (tx, ty)), ("modal", (mx, my))):
            p = predictor.get_points(px, py, ga, gb)
            agg[key][0] += p; agg[key][1][p] += 1
            if predictor.sign(px - py) == predictor.sign(ga - gb): agg[key][2] += 1
        pts = predictor.get_points(tx, ty, ga, gb)
        mk = "✓" if pts == 4 else ("≈" if pts >= 2 else "✗")
        rec = (a, tx, ty, b, ga, gb, pts, mk)
        (groups[t2g[a]].append(rec) if r["phase"] == "GROUP" else ko.append((r["phase"],) + rec))

    for gn in sorted(groups):
        emit(f"\nGROUP {gn}")
        for a, tx, ty, b, ga, gb, pts, mk in groups[gn]:
            emit(f"  {mk} {a:<12} {tx}-{ty}  vs actual {ga}-{gb}  {b:<12} ({pts} pt{'s' if pts != 1 else ''})")
    emit("\nKNOCKOUT  (model's tip for the actual fixture)")
    for ph, a, tx, ty, b, ga, gb, pts, mk in ko:
        emit(f"  {mk} [{ph:<5}] {a:<12} {tx}-{ty}  vs actual {ga}-{gb}  {b:<12} ({pts})")

    e, m = agg["ev"], agg["modal"]
    emit("\n" + "-" * 72)
    emit(f"EV-optimal tips   : {e[0]:>3} pts  | exact {e[1][4]}  diff {e[1][3]}  tend {e[1][2]}  miss {e[1][0]}  | direction {100*e[2]/64:.0f}%")
    emit(f"Most-likely score : {m[0]:>3} pts  | exact {m[1][4]}  diff {m[1][3]}  tend {m[1][2]}  miss {m[1][0]}  | direction {100*m[2]/64:.0f}%")
    emit("Outcome accuracy  : champion MISS (Spain → Germany) · group winners 6/8 · semifinalists 2/4")
    emit("=" * 72)

    os.makedirs("validation", exist_ok=True)
    with open("validation/backtest_2014.txt", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n💾 wrote validation/backtest_2014.txt", file=sys.stderr)


if __name__ == "__main__":
    main()
