#!/usr/bin/env python3
"""
F9 follow-up — CALIBRATION (Brier / RPS / log-loss) and HONEST ρ/α TUNING.

Companion to backtest_kicktipp_folds.py. Same 192 real matches (2014+2018+2022),
same pre-tournament Elo, same shootout-excluded convention.

The points backtest showed Dixon-Coles + Negative Binomial never change the EV-optimal
4/3/2 tip, so they yield 0 point difference. Points cannot see *calibration*, though.
This harness answers the two open questions:

  (2) Are DC + NB better CALIBRATED than independent Poisson, even though the tip is
      unchanged?  → 1x2 Brier, Ranked Probability Score (RPS, the standard order-aware
      football metric), 1x2 log-loss, and full exact-scoreline log-loss. Lower = better.

  (3) Does ANY (ρ, α) beat baseline?  → a ρ×α grid search, reported two ways:
        • in-sample (all 192) — an OVERFIT ceiling, shown only as an upper bound;
        • leave-one-tournament-out CV (LOTO) — fit on two World Cups, evaluate on the
          held-out one, rotate. This is the honest "does tuning generalize" answer.
"""
import os
import sys
import math

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import predictor
from predictor import MatchModelConfig, ModelDistribution, generate_joint_grid
from backtest_kicktipp_folds import ELO_TABLES, RESULTS_CSV, load_results, _elo, MAX_GOALS, MAX_TIP

YEARS = (2014, 2018, 2022)
RHOS = [0.0, -0.02, -0.05, -0.08, -0.10, -0.15]
ALPHAS = [0.0, 0.02, 0.05, 0.10, 0.15, 0.20]
BASELINE = (0.0, 0.0)
PROJECT = (-0.05, 0.05)
EPS = 1e-12


def build_grid(elo_a, elo_b, rho, alpha):
    la, lb = predictor.estimate_base_lambdas_from_elo("A", "B", elo_a, elo_b)
    cfg = MatchModelConfig(
        dist_type=ModelDistribution.NEGATIVE_BINOMIAL if alpha > 0 else ModelDistribution.POISSON,
        mu_a=la, mu_b=lb, alpha_a=alpha, alpha_b=alpha, rho=rho,
        max_goals=MAX_GOALS, max_tip=MAX_TIP,
    )
    return generate_joint_grid(cfg)


def match_metrics(grid, ga, gb):
    """Return (points, brier, rps, logloss_1x2, logloss_exact) for one match."""
    total = 0.0
    for a in grid:
        for b in grid[a]:
            v = grid[a][b]
            if v > 0:
                total += v
    if total <= 0:
        total = 1.0
    ph = pd = pa = 0.0
    for a in grid:
        for b in grid[a]:
            p = max(grid[a][b], 0.0) / total
            if a > b:
                ph += p
            elif a == b:
                pd += p
            else:
                pa += p
    o = 0 if ga > gb else (1 if ga == gb else 2)   # H / D / A (ordered)
    preds = [ph, pd, pa]
    onehot = [1.0 if i == o else 0.0 for i in range(3)]
    brier = sum((preds[i] - onehot[i]) ** 2 for i in range(3))
    cp = co = rps = 0.0
    for i in range(2):                              # r-1 = 2 cumulative thresholds
        cp += preds[i]; co += onehot[i]
        rps += (cp - co) ** 2
    rps /= 2.0
    ll = -math.log(max(preds[o], EPS))
    pe = max(grid.get(ga, {}).get(gb, 0.0), 0.0) / total
    lle = -math.log(max(pe, EPS))
    tips, _, _ = predictor.solve_optimal_tip_from_grid(grid, max_tip=MAX_TIP, pts_exact=4, pts_diff=3, pts_tend=2)
    tip = tips[0][0]
    pts = predictor.get_points(tip[0], tip[1], ga, gb)
    return pts, brier, rps, ll, lle


def aggregate_table():
    """cell[(year, rho, alpha)] = dict(n, pts, brier, rps, ll, lle) summed over the fold."""
    cell = {}
    matches_by_year = {y: load_results(RESULTS_CSV[y]) for y in YEARS}
    for y in YEARS:
        table = ELO_TABLES[y]
        prepared = [(_elo(table, m["team_a"]), _elo(table, m["team_b"]), m["goals_a"], m["goals_b"])
                    for m in matches_by_year[y]]
        for rho in RHOS:
            for alpha in ALPHAS:
                acc = {"n": 0, "pts": 0.0, "brier": 0.0, "rps": 0.0, "ll": 0.0, "lle": 0.0}
                for ea, eb, ga, gb in prepared:
                    g = build_grid(ea, eb, rho, alpha)
                    pts, brier, rps, ll, lle = match_metrics(g, ga, gb)
                    acc["n"] += 1
                    acc["pts"] += pts
                    acc["brier"] += brier
                    acc["rps"] += rps
                    acc["ll"] += ll
                    acc["lle"] += lle
                cell[(y, rho, alpha)] = acc
    return cell


def main():
    out = []
    def emit(s=""):
        out.append(s); print(s)

    cell = aggregate_table()

    def agg(rho, alpha):
        a = {"n": 0, "pts": 0.0, "brier": 0.0, "rps": 0.0, "ll": 0.0, "lle": 0.0}
        for y in YEARS:
            c = cell[(y, rho, alpha)]
            for k in a:
                a[k] += c[k]
        return a

    emit("=" * 80)
    emit("F9 FOLLOW-UP — CALIBRATION & HONEST ρ/α TUNING  (192 matches: 2014+2018+2022)")
    emit("=" * 80)

    # ---- (2) Calibration: baseline vs project-optimized -------------------------
    emit("")
    emit("(2) CALIBRATION — baseline (Poisson) vs project-optimized (DC ρ=-0.05 + NB α=0.05)")
    emit("    Lower is better for every metric. Means over 192 matches.")
    emit("")
    b = agg(*BASELINE); p = agg(*PROJECT)
    emit(f"    {'metric':<26}{'baseline':>12}{'optimized':>12}{'Δ (opt−base)':>16}")
    for key, label in [("brier", "1x2 Brier"), ("rps", "1x2 RPS (order-aware)"),
                       ("ll", "1x2 log-loss"), ("lle", "exact-score log-loss")]:
        bm, pm = b[key] / b["n"], p[key] / p["n"]
        better = "  ✓ optimized better" if pm < bm - 1e-9 else ("  ✗ worse" if pm > bm + 1e-9 else "  = tie")
        emit(f"    {label:<26}{bm:>12.4f}{pm:>12.4f}{pm - bm:>+16.4f}{better}")
    emit(f"    {'Kicktipp points (total)':<26}{b['pts']:>12.0f}{p['pts']:>12.0f}{p['pts'] - b['pts']:>+16.0f}")

    # ---- (3a) In-sample grid (overfit ceiling) ----------------------------------
    emit("")
    emit("(3) ρ/α GRID SEARCH")
    emit("")
    emit("  (3a) IN-SAMPLE over all 192 matches — an OVERFIT ceiling, upper bound only.")
    emit("       Total Kicktipp points by (ρ, α):")
    header = "        ρ\\α  " + "".join(f"{a:>8.2f}" for a in ALPHAS)
    emit(header)
    for rho in RHOS:
        row = f"      {rho:>6.2f}  " + "".join(f"{agg(rho, a)['pts']:>8.0f}" for a in ALPHAS)
        emit(row)
    best_pts = max(((agg(r, a)["pts"], r, a) for r in RHOS for a in ALPHAS), key=lambda x: x[0])
    best_rps = min(((agg(r, a)["rps"] / agg(r, a)["n"], r, a) for r in RHOS for a in ALPHAS), key=lambda x: x[0])
    base_pts = agg(*BASELINE)["pts"]
    base_rps = agg(*BASELINE)["rps"] / agg(*BASELINE)["n"]
    emit("")
    emit(f"       best-by-POINTS : ρ={best_pts[1]:+.2f} α={best_pts[2]:.2f} → {best_pts[0]:.0f} pts "
         f"(baseline {base_pts:.0f}; gain {best_pts[0] - base_pts:+.0f})")
    emit(f"       best-by-RPS    : ρ={best_rps[1]:+.2f} α={best_rps[2]:.2f} → RPS {best_rps[0]:.4f} "
         f"(baseline {base_rps:.4f}; gain {best_rps[0] - base_rps:+.4f})")

    # ---- (3b) Honest leave-one-tournament-out CV --------------------------------
    emit("")
    emit("  (3b) LEAVE-ONE-TOURNAMENT-OUT CV — the honest out-of-sample tuning test.")
    emit("       Fit (ρ,α) on two World Cups, evaluate on the held-out one, rotate.")
    configs = [(r, a) for r in RHOS for a in ALPHAS]

    # Tune for POINTS
    loto_pts = 0.0
    pts_detail = []
    for held in YEARS:
        train = [y for y in YEARS if y != held]
        best_cfg = max(configs, key=lambda c: sum(cell[(y, c[0], c[1])]["pts"] for y in train))
        gained = cell[(held, best_cfg[0], best_cfg[1])]["pts"]
        loto_pts += gained
        pts_detail.append(f"hold {held}: train-best ρ={best_cfg[0]:+.2f} α={best_cfg[1]:.2f} → {gained:.0f} pts on {held}")
    base_total_pts = sum(cell[(y, 0.0, 0.0)]["pts"] for y in YEARS)
    for d in pts_detail:
        emit(f"       {d}")
    emit(f"       → tuned-for-points out-of-sample total: {loto_pts:.0f} pts  "
         f"(baseline {base_total_pts:.0f}; Δ {loto_pts - base_total_pts:+.0f})")

    # Tune for RPS
    emit("")
    loto_rps_sum = 0.0; loto_n = 0
    rps_detail = []
    for held in YEARS:
        train = [y for y in YEARS if y != held]
        def train_rps(c):
            s = sum(cell[(y, c[0], c[1])]["rps"] for y in train)
            n = sum(cell[(y, c[0], c[1])]["n"] for y in train)
            return s / n
        best_cfg = min(configs, key=train_rps)
        held_rps = cell[(held, best_cfg[0], best_cfg[1])]["rps"]
        held_n = cell[(held, best_cfg[0], best_cfg[1])]["n"]
        loto_rps_sum += held_rps; loto_n += held_n
        rps_detail.append(f"hold {held}: train-best ρ={best_cfg[0]:+.2f} α={best_cfg[1]:.2f} → RPS {held_rps/held_n:.4f} on {held}")
    base_mean_rps = sum(cell[(y, 0.0, 0.0)]["rps"] for y in YEARS) / sum(cell[(y, 0.0, 0.0)]["n"] for y in YEARS)
    for d in rps_detail:
        emit(f"       {d}")
    emit(f"       → tuned-for-RPS out-of-sample mean RPS: {loto_rps_sum/loto_n:.4f}  "
         f"(baseline {base_mean_rps:.4f}; Δ {loto_rps_sum/loto_n - base_mean_rps:+.4f})")

    emit("")
    emit("=" * 80)
    report = os.path.join("validation", "backtest_calibration_tuning.txt")
    with open(report, "w") as f:
        f.write("\n".join(out) + "\n")
    print(f"\n💾 Report written to {report}", file=sys.stderr)


if __name__ == "__main__":
    main()
