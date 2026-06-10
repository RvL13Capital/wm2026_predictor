#!/usr/bin/env python3
"""
How did GROUP-STAGE results actually distribute at WC 2014 + 2018 + 2022?
Looks at real goals (all three) and non-penalty xG (2018 + 2022 — no xG exists for 2014),
with a dedicated component for evenly-matched teams (small pre-tournament Elo gap), to see
what to realistically expect when two equal sides meet. Output: validation/group_result_distribution.txt
"""
import os, sys, csv
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_wm2014 as w14, backtest_wm2018 as w18, backtest_wm2022 as w22

ELO = {2014: w14.PRE_WM2014_ELO, 2018: w18.PRE_WM2018_ELO, 2022: w22.PRE_WM2022_ELO}
def elo(y, t): return ELO[y].get(t, {}).get("elo", 1500)

# real-goal group matches (all 3 years); xG group matches (2018/2022)
real, xg = [], []
for y in (2014, 2018, 2022):
    for r in csv.DictReader(open(f"data/wc{y}_results.csv")):
        if r["phase"] != "GROUP":
            continue
        a, b, ga, gb = r["team_a"], r["team_b"], int(r["goals_a"]), int(r["goals_b"])
        real.append({"y": y, "a": a, "b": b, "ga": ga, "gb": gb, "d": abs(elo(y, a) - elo(y, b))})
for y in (2018, 2022):
    for r in csv.DictReader(open(f"data/wc{y}_xg.csv")):
        if r["phase"] != "GROUP":
            continue
        a, b = r["team_a"], r["team_b"]
        xg.append({"y": y, "a": a, "b": b, "ga": int(r["goals_a"]), "gb": int(r["goals_b"]),
                   "xa": float(r["npxg_a"]), "xb": float(r["npxg_b"]), "d": abs(elo(y, a) - elo(y, b))})


def fav_scoreline(m):
    """scoreline oriented favourite-first; (X,X) for draws."""
    fav_a = elo(m["y"], m["a"]) >= elo(m["y"], m["b"])
    return (m["ga"], m["gb"]) if fav_a else (m["gb"], m["ga"])


def outcome_fav(ga, gb, fav_a):
    if ga == gb: return "draw"
    return "fav" if (ga > gb) == fav_a else "dog"


out = []
def emit(s=""):
    out.append(s); print(s)

emit("=" * 74)
emit("GROUP-STAGE RESULT DISTRIBUTION — WC 2014 + 2018 + 2022")
emit("=" * 74)

# ---- PART 1: real-goal distribution ----
n = len(real)
draws = sum(1 for m in real if m["ga"] == m["gb"])
favw = sum(1 for m in real if outcome_fav(m["ga"], m["gb"], elo(m["y"], m["a"]) >= elo(m["y"], m["b"])) == "fav")
dogw = n - draws - favw
totals = Counter(m["ga"] + m["gb"] for m in real)
scs = Counter(fav_scoreline(m) for m in real)
emit(f"\nPART 1 — real goals  (n={n} group matches)")
emit(f"  outcomes : favourite win {favw} ({100*favw/n:.0f}%) | draw {draws} ({100*draws/n:.0f}%) | underdog win {dogw} ({100*dogw/n:.0f}%)")
emit(f"  goals/match: mean {sum(m['ga']+m['gb'] for m in real)/n:.2f} | total-goal spread " +
     " ".join(f"{k}:{totals[k]}" for k in sorted(totals)))
emit("  most common scorelines (favourite-first):")
for (x, yv), c in scs.most_common(8):
    emit(f"     {x}-{yv}  {c:>3}  ({100*c/n:.0f}%)")

# ---- PART 2: xG vs real ----
nx = len(xg)
real_pg = sum(m["ga"] + m["gb"] for m in xg) / (2 * nx)
xg_pg = sum(m["xa"] + m["xb"] for m in xg) / (2 * nx)
# did the team that created more (npxG) actually win?
better_won = better_drew = better_lost = 0
for m in xg:
    if abs(m["xa"] - m["xb"]) < 1e-9:
        continue
    better_a = m["xa"] > m["xb"]
    res = "draw" if m["ga"] == m["gb"] else ("a" if m["ga"] > m["gb"] else "b")
    if res == "draw": better_drew += 1
    elif (res == "a") == better_a: better_won += 1
    else: better_lost += 1
tot = better_won + better_drew + better_lost
emit(f"\nPART 2 — xG vs real goals  (n={nx} group matches, 2018+2022; no xG for 2014)")
emit(f"  goals per team : real {real_pg:.2f}  vs  non-penalty xG {xg_pg:.2f}")
emit(f"  did the side that created more (npxG) actually win?")
emit(f"     yes {better_won} ({100*better_won/tot:.0f}%) | drew {better_drew} ({100*better_drew/tot:.0f}%) | "
     f"LOST {better_lost} ({100*better_lost/tot:.0f}%)  ← finishing luck / wastefulness")

# ---- PART 3: evenly-matched teams ----
emit(f"\nPART 3 — by pre-tournament Elo gap  (real goals, n={n})")
bands = [("even  (≤50)", 0, 50), ("slight (51-150)", 51, 150), ("clear (>150)", 151, 9999)]
emit(f"  {'band':<16}{'N':>4}{'fav win':>9}{'draw':>7}{'dog win':>9}{'goals/m':>9}")
for name, lo, hi in bands:
    sub = [m for m in real if lo <= m["d"] <= hi]
    if not sub: continue
    nn = len(sub)
    dr = sum(1 for m in sub if m["ga"] == m["gb"])
    fw = sum(1 for m in sub if outcome_fav(m["ga"], m["gb"], elo(m["y"], m["a"]) >= elo(m["y"], m["b"])) == "fav")
    dw = nn - dr - fw
    gpm = sum(m["ga"] + m["gb"] for m in sub) / nn
    emit(f"  {name:<16}{nn:>4}{100*fw/nn:>8.0f}%{100*dr/nn:>6.0f}%{100*dw/nn:>8.0f}%{gpm:>9.2f}")

even = [m for m in real if m["d"] <= 50]
even_xg = [m for m in xg if m["d"] <= 50]
emit(f"\n  EVENLY-MATCHED (Elo gap ≤ 50): {len(even)} real matches")
ev_sc = Counter(tuple(sorted((m['ga'], m['gb']), reverse=True)) for m in even)   # unordered scoreline
emit("    scorelines (unordered): " + " | ".join(f"{x}-{y}:{c}" for (x, y), c in ev_sc.most_common(6)))
emit(f"    draw rate {100*sum(1 for m in even if m['ga']==m['gb'])/len(even):.0f}%  ·  "
     f"goals/match {sum(m['ga']+m['gb'] for m in even)/len(even):.2f}")
if even_xg:
    nxe = len(even_xg)
    close_xg = sum(1 for m in even_xg if abs(m["xa"] - m["xb"]) < 0.5)
    emit(f"    xG (2018/2022 even games, n={nxe}): mean npxG/team {sum(m['xa']+m['xb'] for m in even_xg)/(2*nxe):.2f}  ·  "
         f"games where xG margin <0.5 (truly even on the day) {100*close_xg/nxe:.0f}%")

emit("\n" + "=" * 74)
os.makedirs("validation", exist_ok=True)
with open("validation/group_result_distribution.txt", "w") as f:
    f.write("\n".join(out) + "\n")
print("\n💾 wrote validation/group_result_distribution.txt", file=sys.stderr)
