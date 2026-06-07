#!/usr/bin/env python3
"""
Can recalibrating the goal model make the END RESULT more accurate — honestly, out of sample?

Grid-searches the Elo->lambda scale (baseline_goals, scale_factor) plus Dixon-Coles rho and
Negative-Binomial alpha, and measures exact-score + tendency accuracy of the MOST-LIKELY score
via leave-one-tournament-out CV across WC2014/2018/2022 (real results). Compares the current
defaults (1.35 / 1600 / rho -0.05 / alpha 0.05) to the LOTO-tuned config and the in-sample
ceiling. Also reports the lambda scale obtained by fitting directly to non-penalty xG (2018+2022).
Output: validation/recalibration.txt
"""
import os, sys, math, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictor
from predictor import MatchModelConfig, ModelDistribution, generate_joint_grid, sign, solve_optimal_tip_from_grid
from make_bracket_html import modal
import backtest_wm2014 as w14, backtest_wm2018 as w18, backtest_wm2022 as w22

YEARS = (2014, 2018, 2022)
ELO = {2014: w14.PRE_WM2014_ELO, 2018: w18.PRE_WM2018_ELO, 2022: w22.PRE_WM2022_ELO}
def elo(y, t): return ELO[y].get(t, {}).get("elo", 1500)

M = {y: [] for y in YEARS}
for y in YEARS:
    for r in csv.DictReader(open(f"data/wc{y}_results.csv")):
        M[y].append((elo(y, r["team_a"]) - elo(y, r["team_b"]), int(r["goals_a"]), int(r["goals_b"])))

MAXG = 8
def grid_for(diff, bg, sf, rho, alpha):
    la = bg * 10 ** (diff / sf); lb = bg * 10 ** (-diff / sf)
    cfg = MatchModelConfig(
        dist_type=ModelDistribution.NEGATIVE_BINOMIAL if alpha > 0 else ModelDistribution.POISSON,
        mu_a=la, mu_b=lb, alpha_a=alpha, alpha_b=alpha, rho=rho, max_goals=MAXG, max_tip=6)
    return generate_joint_grid(cfg)

BG = [1.15, 1.25, 1.35, 1.45]; SF = [1200, 1600, 2000, 2600]; RHO = [0.0, -0.06, -0.12]; ALPHA = [0.0, 0.06]
configs = [(bg, sf, r, al) for bg in BG for sf in SF for r in RHO for al in ALPHA]
DEFAULT = (1.35, 1600, -0.05, 0.05)
configs.append(DEFAULT)

# precompute modal exact/dir per (config, year)
cell = {}
for ci, cfg in enumerate(configs):
    for y in YEARS:
        ex = dr = 0
        for diff, ga, gb in M[y]:
            mx, my = modal(grid_for(diff, *cfg))
            if mx == ga and my == gb: ex += 1
            if sign(mx - my) == sign(ga - gb): dr += 1
        cell[(ci, y)] = (ex, dr, len(M[y]))

def agg(ci, years):
    ex = sum(cell[(ci, y)][0] for y in years); dr = sum(cell[(ci, y)][1] for y in years); n = sum(cell[(ci, y)][2] for y in years)
    return ex, dr, n

di = configs.index(DEFAULT)
N = sum(len(M[y]) for y in YEARS)

# in-sample best by exact
best_ci = max(range(len(configs)), key=lambda ci: agg(ci, YEARS)[0])
# LOTO tuned for exact
loto_ex = loto_dr = 0; picks = []
for h in YEARS:
    train = [y for y in YEARS if y != h]
    bci = max(range(len(configs)), key=lambda ci: agg(ci, train)[0] / agg(ci, train)[2])
    e, d, n = cell[(bci, h)]; loto_ex += e; loto_dr += d; picks.append((h, configs[bci]))

# EV-tip accuracy for a config (heavier; only for a couple of configs)
def evtip(cfg):
    ex = dr = 0
    for y in YEARS:
        for diff, ga, gb in M[y]:
            tips, _, _ = solve_optimal_tip_from_grid(grid_for(diff, *cfg), max_tip=6, pts_exact=4, pts_diff=3, pts_tend=2)
            tx, ty = tips[0][0]
            if tx == ga and ty == gb: ex += 1
            if sign(tx - ty) == sign(ga - gb): dr += 1
    return ex, dr

# fit lambda scale to npxG (2018+2022) via OLS on log(npxg) ~ elo_diff
xs, ys = [], []
for y in (2018, 2022):
    for r in csv.DictReader(open(f"data/wc{y}_xg.csv")):
        a, b = r["team_a"], r["team_b"]
        xs += [elo(y, a) - elo(y, b), elo(y, b) - elo(y, a)]
        ys += [math.log(max(float(r["npxg_a"]), 0.2)), math.log(max(float(r["npxg_b"]), 0.2))]
mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
b1 = sum((x - mx) * (yv - my) for x, yv in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
b0 = my - b1 * mx
bg_fit, sf_fit = math.exp(b0), math.log(10) / b1

out = []
def emit(s=""):
    out.append(s); print(s)

emit("=" * 76)
emit("λ RECALIBRATION — does it make the end result more accurate? (LOTO, 192 matches)")
emit("=" * 76)
de, dd, _ = agg(di, YEARS)
be, bd, _ = agg(best_ci, YEARS)
emit(f"\nMOST-LIKELY score accuracy (exact / tendency), out of {N} matches:")
emit(f"  current default  (bg1.35 sf1600 ρ-0.05 α0.05): exact {de} ({100*de/N:.0f}%)  tendency {100*dd/N:.0f}%")
emit(f"  LOTO-tuned (honest, out-of-sample)            : exact {loto_ex} ({100*loto_ex/N:.0f}%)  tendency {100*loto_dr/N:.0f}%")
emit(f"  in-sample BEST {configs[best_ci]} (overfit ceiling): exact {be} ({100*be/N:.0f}%)  tendency {100*bd/N:.0f}%")
emit("  LOTO held-out picks: " + " | ".join(f"{h}:bg{c[0]} sf{c[1]} ρ{c[2]} α{c[3]}" for h, c in picks))

emit(f"\nEV-optimal tip accuracy (for reference — the points-maximising submission):")
for label, cfg in [("default", DEFAULT), (f"best {configs[best_ci]}", configs[best_ci])]:
    ex, dr = evtip(cfg)
    emit(f"  {label:<28}: exact {ex} ({100*ex/N:.0f}%)  tendency {100*dr/N:.0f}%")

emit(f"\nλ scale fit directly to non-penalty xG (2018+2022):")
emit(f"  baseline_goals {bg_fit:.2f} (default 1.35) · scale_factor {sf_fit:.0f} (default 1600)")
emit(f"  → {'less' if sf_fit > 1600 else 'more'} favourite-stretch, {'lower' if bg_fit < 1.35 else 'higher'} base goals")

emit("\n" + "-" * 76)
gain = loto_ex - de
emit(f"VERDICT: out-of-sample exact-score change vs default: {gain:+d} matches ({100*gain/N:+.1f} pts).")
emit("Exact-score accuracy is capped by the flat result distribution + ~23% finishing luck;")
emit("recalibration mainly moves TENDENCY/calibration, not the exact scoreline.")
emit("=" * 76)

os.makedirs("validation", exist_ok=True)
with open("validation/recalibration.txt", "w") as f:
    f.write("\n".join(out) + "\n")
print("\n💾 wrote validation/recalibration.txt", file=sys.stderr)
