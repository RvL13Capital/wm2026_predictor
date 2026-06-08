#!/usr/bin/env python3
"""
Evaluate the model's λ (expected goals) against realized NON-PENALTY xG — a far
lower-variance target than the single scoreline.

Part 1 — Base λ (Elo→λ, no context) vs npxG, WC2018 + WC2022 (128 matches / 256 team-rows):
         does the core engine predict realized chance quality, and the npxG *margin*?
Part 2 — Context layer on WC2022 (conditions from data/wc2022_full.csv): does adding
         travel/host/etc. move λ *closer* to realized npxG? (Altitude/heat barely fire in
         Russia/Qatar — this tests the components that do: travel + host.)

npxG from data/wc{2018,2022}_xg.csv (built by build_xg_data.py from StatsBomb open data).
"""
import os, sys, csv, math
import statistics as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictor
import backtest
from backtest_wm2018 import PRE_WM2018_ELO
from backtest_wm2022 import PRE_WM2022_ELO

ELO = {2018: PRE_WM2018_ELO, 2022: PRE_WM2022_ELO}


def load_xg(year):
    return list(csv.DictReader(open(f"data/wc{year}_xg.csv")))


def pearson(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs); syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0


def main():
    out = []
    def emit(s=""):
        out.append(s); print(s)

    emit("=" * 78)
    emit("λ vs NON-PENALTY xG — lower-variance validation (StatsBomb open data)")
    emit("=" * 78)

    # ---- Part 1: base λ vs npxG ----
    lam_pred, npxg_real = [], []
    margin_pred, margin_real = [], []
    missing = set()
    for year in (2018, 2022):
        elo = ELO[year]
        for r in load_xg(year):
            a, b = r["team_a"], r["team_b"]
            if a not in elo or b not in elo:
                missing.add((year, a if a not in elo else b)); continue
            la, lb = predictor.estimate_base_lambdas_from_elo(a, b, float(elo[a]["elo"]), float(elo[b]["elo"]))
            xa, xb = float(r["npxg_a"]), float(r["npxg_b"])
            lam_pred += [la, lb]; npxg_real += [xa, xb]
            margin_pred.append(la - lb); margin_real.append(xa - xb)
    if missing:
        emit(f"  ⚠ skipped (no Elo): {sorted(missing)}")

    n = len(lam_pred)
    mae = sum(abs(p - q) for p, q in zip(lam_pred, npxg_real)) / n
    bias = sum(p - q for p, q in zip(lam_pred, npxg_real)) / n
    rmse = math.sqrt(sum((p - q) ** 2 for p, q in zip(lam_pred, npxg_real)) / n)
    r_team = pearson(lam_pred, npxg_real)
    r_margin = pearson(margin_pred, margin_real)
    mean_npxg = sum(npxg_real) / n
    mae_const = sum(abs(mean_npxg - q) for q in npxg_real) / n      # naive "everyone = average" baseline
    skill = 1 - mae / mae_const

    emit("")
    emit(f"PART 1 — base Elo→λ vs realized npxG  ({n} team-match observations, 2018+2022)")
    emit(f"  Pearson r (per-team λ vs npxG)     : {r_team:+.3f}")
    emit(f"  Pearson r (npxG MARGIN λa-λb)      : {r_margin:+.3f}   ← outcome-relevant")
    emit(f"  MAE (λ vs npxG)                    : {mae:.3f} goals")
    emit(f"  vs naive constant-mean MAE         : {mae_const:.3f}  → skill score {skill:+.1%}")
    emit(f"  bias (λ − npxG)                    : {bias:+.3f}  (λ models total goals incl. penalties;")
    emit(f"                                        npxG excludes them, so a small + offset is expected)")
    emit(f"  RMSE                               : {rmse:.3f}")

    # ---- Part 2: context effect on 2022 ----
    emit("")
    emit("PART 2 — does the CONTEXT layer move λ closer to npxG?  (WC2022, conditions from wc2022_full.csv)")
    xg22 = {}
    for r in load_xg(2022):
        xg22[frozenset((r["team_a"], r["team_b"]))] = {r["team_a"]: float(r["npxg_a"]), r["team_b"]: float(r["npxg_b"])}
    rows = backtest.load_match_data("data/wc2022_full.csv")
    elo = ELO[2022]
    err_core, err_ctx = [], []          # per-team |λ − npxG|
    me_core, me_ctx, m_real = [], [], []  # margin (λa−λb) vs (npxg_a−npxg_b) — bias-invariant
    used = 0
    for row in rows:
        a, b = row["team_a"], row["team_b"]
        key = frozenset((a, b))
        if key not in xg22 or a not in elo or b not in elo:
            continue
        la0, lb0 = predictor.estimate_base_lambdas_from_elo(a, b, float(elo[a]["elo"]), float(elo[b]["elo"]))
        ca, cb = backtest.make_context(row, "a"), backtest.make_context(row, "b")
        la1, lb1 = predictor.get_adjusted_lambdas(la0, lb0, ca, cb)
        xa, xb = xg22[key][a], xg22[key][b]
        err_core += [abs(la0 - xa), abs(lb0 - xb)]
        err_ctx += [abs(la1 - xa), abs(lb1 - xb)]
        mr = xa - xb
        me_core.append(abs((la0 - lb0) - mr)); me_ctx.append(abs((la1 - lb1) - mr)); m_real.append(mr)
        used += 1
    mae_core = sum(err_core) / len(err_core); mae_ctx = sum(err_ctx) / len(err_ctx)
    diffs = [c - k for c, k in zip(err_ctx, err_core)]
    md = sum(diffs) / len(diffs); se = st.pstdev(diffs) / math.sqrt(len(diffs))
    emit(f"  matches used: {used}  ({len(err_core)} team-rows)")
    emit(f"  (a) per-team:  MAE core {mae_core:.3f} → context {mae_ctx:.3f}  "
         f"(Δ {mae_ctx - mae_core:+.3f}, t={md/se if se else 0:+.2f})")
    # (b) bias-invariant margin — removes the per-team over-scaling confound
    mmc = sum(me_core) / len(me_core); mmx = sum(me_ctx) / len(me_ctx)
    dm = [x - c for x, c in zip(me_ctx, me_core)]; mdm = sum(dm) / len(dm); sem = st.pstdev(dm) / math.sqrt(len(dm))
    emit(f"  (b) MARGIN:    MAE core {mmc:.3f} → context {mmx:.3f}  "
         f"(Δ {mmx - mmc:+.3f}, t={mdm/sem if sem else 0:+.2f})  ← bias-invariant, outcome-relevant")
    emit("")
    emit("  READ: the per-team improvement (a) is NOT real context skill — it is context pulling the")
    emit("  over-scaled λ (Part-1 bias +0.31) down toward npxG. On the bias-invariant margin (b) the")
    emit("  effect vanishes into noise (t≈-0.5), and context slightly lowers the npxG-margin")
    emit("  correlation. Context adds no detectable outcome signal here once the confound is removed.")
    emit("")
    emit("  NOTE: Russia 2018 / Qatar 2022 are low-altitude, climate-mild (Qatar AC + winter),")
    emit("  near-zero inter-match travel — so altitude/heat barely fire here; this mainly tests")
    emit("  the travel + host components. Altitude/heat (the 2026-relevant curves) need extreme-")
    emit("  condition data with xG, which StatsBomb open data does not cover (no 2014, no quals).")
    emit("=" * 78)

    with open("validation/backtest_xg_calibration.txt", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n💾 Report written to validation/backtest_xg_calibration.txt", file=sys.stderr)


if __name__ == "__main__":
    main()
