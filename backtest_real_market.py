#!/usr/bin/env python3
"""Gate G2 — backtest the model against REAL historical closing odds (S16).

This is the decision gate for the betting track: unlike backtest_harness.py
(whose "market" is the engine's own Elo plus 5% vig — a feature ablation, not
market evidence; see validation/SHIN_EVALUATION.md Finding 3), this harness
compares the PURE model against actual bookmaker closing 1X2 prices.

PRE-REGISTERED VERDICT (IMPLEMENTATION_PLAN.md S16): real-money use of the
edge scanner is permitted ONLY if
  (a) model or 50/50 blend log-loss beats the de-vigged market close on
      >= 2 of 3 tournaments, AND
  (b) flat-stake ROI's 95% bootstrap CI excludes 0 (lower bound > 0).
Anything else => the scanner stays paper-only. A FAIL is a successful
outcome (loss prevention), not a setback.

DATA (not in the repo yet — supply before running):
  data/wc{2014,2018,2022}_odds.csv with columns
      team_a,team_b,odds_home,odds_draw,odds_away[,phase][,bookmaker]
  * 1X2 closing odds for the 90-MINUTE result (the standard market).
  * Team names: any spelling in predictor.TEAM_NAME_MAPPING; row orientation
    may be swapped vs the results file (handled).
  Sourcing order (plan S16): Kaggle international-odds datasets ->
  oddsportal archive export -> Betfair historical -> manual entry
  (192 matches, ~1 day).

SETTLEMENT NUANCE: data/wc{Y}_results.csv records KO games after extra time
(F9 convention). The 1X2 market settles on 90 minutes — and a KO game only
reaches ET if the 90' score was LEVEL, so the 90' outcome class is exactly
recoverable: KO + in the real-ET set (backtest_harness.went_to_extra_time_real)
=> draw; otherwise the recorded sign.

Model probabilities: PURE pre-tournament-Elo model under PRODUCTION constants
(phase-adjusted 90' grid; no market input — the comparison must not be
self-referential).
"""
import argparse
import csv
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import predictor
from predictor import (MatchModelConfig, ModelDistribution, generate_joint_grid,
                       apply_phase_adjustments, parse_match_phase)
from utils.math_utils import strip_vig_shin
from backtest_harness import went_to_extra_time_real
from backtest_wm2014 import PRE_WM2014_ELO
from backtest_wm2018 import PRE_WM2018_ELO
from backtest_wm2022 import PRE_WM2022_ELO

REPO = os.path.dirname(os.path.abspath(__file__))
ELO_TABLES = {2014: PRE_WM2014_ELO, 2018: PRE_WM2018_ELO, 2022: PRE_WM2022_ELO}
YEARS = (2014, 2018, 2022)


def _canon(name: str) -> str:
    return predictor.TEAM_NAME_MAPPING.get(name.strip().lower(), name.strip())


def model_1x2(elo_a: float, elo_b: float, phase_str: str):
    """Pure-model 90-minute 1X2 under production constants (phase-adjusted)."""
    la, lb = predictor.estimate_base_lambdas_from_elo("A", "B", elo_a, elo_b)
    phase = parse_match_phase(phase_str)
    rho_adj, la, lb = apply_phase_adjustments(-0.05, la, lb, phase)
    cfg = MatchModelConfig(dist_type=ModelDistribution.POISSON,
                           mu_a=la, mu_b=lb, rho=rho_adj, max_goals=10)
    grid = generate_joint_grid(cfg)
    p_h = p_d = p_a = 0.0
    for ga, inner in grid.items():
        for gb, p in inner.items():
            if ga > gb:
                p_h += p
            elif ga == gb:
                p_d += p
            else:
                p_a += p
    tot = p_h + p_d + p_a
    return p_h / tot, p_d / tot, p_a / tot


def load_fold(year: int, odds_path: str, results_path: str,
              elo_table: dict, et_lookup) -> list:
    """Join odds to results. Returns rows:
    {teams, phase, odds (oh,od,oa), outcome in {0:H,1:D,2:A} on 90'}."""
    results = {}
    with open(results_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a, b = _canon(r["team_a"]), _canon(r["team_b"])
            results[(a, b)] = {
                "goals_a": int(r["goals_a"]), "goals_b": int(r["goals_b"]),
                "phase": (r.get("phase") or "GROUP").strip(),
            }

    rows, missing = [], []
    blank = invalid = 0
    with open(odds_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a, b = _canon(r["team_a"]), _canon(r["team_b"])
            raw = (r.get("odds_home"), r.get("odds_draw"), r.get("odds_away"))
            if any(x is None or str(x).strip() == "" for x in raw):
                blank += 1                  # template row not filled in yet — fine
                continue
            try:
                oh, od, oa = (float(x) for x in raw)
            except ValueError:
                invalid += 1
                continue
            if min(oh, od, oa) <= 1.0:
                invalid += 1                # decimal odds must exceed 1.0
                continue
            res = results.get((a, b))
            if res is None:
                res = results.get((b, a))
                if res is not None:   # odds row is the other orientation: swap H/A
                    a, b = b, a
                    oh, oa = oa, oh
            if res is None:
                missing.append(f"{r['team_a']} vs {r['team_b']}")
                continue
            phase = (r.get("phase") or res["phase"]).strip()
            is_ko = parse_match_phase(phase) not in (None, predictor.MatchPhase.GROUP)
            if is_ko and et_lookup(a, b, phase, year):
                outcome = 1                                   # 90' was level
            else:
                ga, gb = res["goals_a"], res["goals_b"]
                outcome = 0 if ga > gb else (1 if ga == gb else 2)
            elo_a = elo_table.get(a, {}).get("elo", 1500)
            elo_b = elo_table.get(b, {}).get("elo", 1500)
            rows.append({"year": year, "team_a": a, "team_b": b, "phase": phase,
                         "odds": (oh, od, oa), "outcome": outcome,
                         "elo_a": elo_a, "elo_b": elo_b})
    if missing:
        print(f"⚠ {year}: {len(missing)} odds rows had no matching result "
              f"(e.g. {missing[:3]}) — excluded.", file=sys.stderr)
    if blank:
        print(f"ℹ {year}: {blank} template rows still without odds — skipped "
              f"(fill them in data/wc{year}_odds.csv).", file=sys.stderr)
    if invalid:
        print(f"⚠ {year}: {invalid} rows with unparseable/≤1.0 odds — skipped.", file=sys.stderr)
    return rows


def _logloss(p, k):
    return -math.log(max(p[k], 1e-12))


def _brier(p, k):
    return sum((p[i] - (1.0 if i == k else 0.0)) ** 2 for i in range(3))


def _rps(p, k):
    obs = [1.0 if i == k else 0.0 for i in range(3)]
    cp = co = rps = 0.0
    for i in range(2):
        cp += p[i]
        co += obs[i]
        rps += (cp - co) ** 2
    return rps / 2.0


def evaluate_fold(rows: list, threshold: float = 0.02, kelly_fraction: float = 0.25):
    """Score market / model / blend, simulate flat + fractional-Kelly betting
    at the recorded raw odds. Pure function of the joined rows."""
    metrics = {m: {"logloss": 0.0, "brier": 0.0, "rps": 0.0}
               for m in ("market", "model", "blend")}
    bet_returns = []          # flat 1-unit P&L per placed bet
    bankroll = 100.0          # fractional-Kelly compounding
    n = len(rows)

    for row in rows:
        oh, od, oa = row["odds"]
        (mh, md, ma), _z = strip_vig_shin(1.0 / oh, 1.0 / od, 1.0 / oa)
        ph, pd, pa = model_1x2(row["elo_a"], row["elo_b"], row["phase"])
        bl = [(mh + ph) / 2.0, (md + pd) / 2.0, (ma + pa) / 2.0]
        s = sum(bl)
        bl = [x / s for x in bl]

        k = row["outcome"]
        for name, p in (("market", (mh, md, ma)), ("model", (ph, pd, pa)), ("blend", bl)):
            metrics[name]["logloss"] += _logloss(p, k)
            metrics[name]["brier"] += _brier(p, k)
            metrics[name]["rps"] += _rps(p, k)

        # Betting at the raw closing prices, flagged by model EV
        odds3, pmod3 = (oh, od, oa), (ph, pd, pa)
        for i in range(3):
            ev = pmod3[i] * odds3[i] - 1.0
            if ev > threshold:
                won = (i == k)
                bet_returns.append(odds3[i] - 1.0 if won else -1.0)
                b = odds3[i] - 1.0
                f = max(0.0, (b * pmod3[i] - (1.0 - pmod3[i])) / b) * kelly_fraction
                stake = f * bankroll
                bankroll += stake * (odds3[i] - 1.0) if won else -stake

    for m in metrics:
        for key in metrics[m]:
            metrics[m][key] /= max(n, 1)
    flat_roi = (sum(bet_returns) / len(bet_returns)) if bet_returns else 0.0
    return {"n": n, "metrics": metrics, "bet_returns": bet_returns,
            "flat_roi": flat_roi, "n_bets": len(bet_returns),
            "kelly_final_bankroll": bankroll}


def bootstrap_roi_ci(bet_returns: list, n_boot: int = 10000, seed: int = 7):
    if not bet_returns:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(bet_returns)
    means = sorted(sum(bet_returns[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]


def gate_verdict(fold_results: dict, all_bet_returns: list):
    """Apply the pre-registered G2 criteria. Returns (passed, reasons)."""
    folds_beating = 0
    for year, res in fold_results.items():
        mkt = res["metrics"]["market"]["logloss"]
        best = min(res["metrics"]["model"]["logloss"], res["metrics"]["blend"]["logloss"])
        if best < mkt:
            folds_beating += 1
    lo, hi = bootstrap_roi_ci(all_bet_returns)
    cond_a = folds_beating >= 2
    cond_b = lo > 0.0
    reasons = [
        f"(a) model/blend log-loss beats market close on {folds_beating}/{len(fold_results)} folds "
        f"(need >= 2): {'MET' if cond_a else 'NOT MET'}",
        f"(b) flat-stake ROI 95% CI [{lo:+.4f}, {hi:+.4f}] excludes 0: "
        f"{'MET' if cond_b else 'NOT MET'}",
    ]
    return cond_a and cond_b, reasons, (lo, hi)


def main():
    ap = argparse.ArgumentParser(description="Gate G2 — model vs real closing odds")
    ap.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    ap.add_argument("--threshold", type=float, default=0.02, help="Model EV threshold to place a flat bet")
    ap.add_argument("--kelly", type=float, default=0.25)
    ap.add_argument("--output", type=str, default=os.path.join(REPO, "validation", "backtest_real_market.txt"))
    args = ap.parse_args()

    # Load whatever data exists; a year is "awaiting" if its odds file is
    # missing OR present but has no completed rows yet (the committed files
    # start as fixture templates with blank odds — see data/ODDS_DATA_README.md).
    fold_rows, awaiting = {}, []
    for y in args.years:
        path = os.path.join(REPO, "data", f"wc{y}_odds.csv")
        if not os.path.exists(path):
            awaiting.append((y, "file missing"))
            continue
        loaded = load_fold(y, path, os.path.join(REPO, "data", f"wc{y}_results.csv"),
                           ELO_TABLES.get(y, {}), went_to_extra_time_real)
        if not loaded:
            awaiting.append((y, "template present, no completed odds rows yet"))
            continue
        fold_rows[y] = loaded

    if not fold_rows:
        print("=" * 72)
        print("⏳ GATE G2 — AWAITING DATA")
        print("=" * 72)
        for y, why in awaiting:
            print(f"  {y}: {why}  →  data/wc{y}_odds.csv")
        print("\nFill the closing 1X2 odds into the template CSVs (three numbers per")
        print("row); see data/ODDS_DATA_README.md for sources and definitions, then")
        print("re-run. Partial fills are fine — completed rows are used, blank rows")
        print("are skipped, and a single year runs with e.g. --years 2022.")
        sys.exit(2)

    out = []

    def emit(s=""):
        out.append(s)
        print(s)

    emit("=" * 76)
    emit("GATE G2 — MODEL vs REAL CLOSING ODDS (pre-registered verdict, plan S16)")
    emit("=" * 76)
    if awaiting:
        emit("⚠ PARTIAL RUN — still awaiting: "
             + ", ".join(f"{y} ({why})" for y, why in awaiting))
        emit("  Criterion (a) needs >= 2 folds beating the close; treat a partial")
        emit("  run as a parsing sanity check, not the gate.")

    fold_results, all_returns = {}, []
    for y, rows in fold_rows.items():
        res = evaluate_fold(rows, threshold=args.threshold, kelly_fraction=args.kelly)
        fold_results[y] = res
        all_returns.extend(res["bet_returns"])
        m = res["metrics"]
        emit(f"\nWC{y} ({res['n']} matches, {res['n_bets']} flat bets):")
        emit(f"  {'':<8} {'log-loss':>9} {'Brier':>8} {'RPS':>8}")
        for name in ("market", "model", "blend"):
            emit(f"  {name:<8} {m[name]['logloss']:>9.4f} {m[name]['brier']:>8.4f} {m[name]['rps']:>8.4f}")
        emit(f"  flat ROI {res['flat_roi']:+.4f}/bet · ¼-Kelly bankroll 100 → {res['kelly_final_bankroll']:.1f}")

    passed, reasons, (lo, hi) = gate_verdict(fold_results, all_returns)
    emit("\n" + "-" * 76)
    emit(f"AGGREGATE: {len(all_returns)} flat bets, ROI {sum(all_returns)/max(len(all_returns),1):+.4f}/bet, "
         f"95% CI [{lo:+.4f}, {hi:+.4f}]")
    for r in reasons:
        emit("  " + r)
    emit("")
    emit(f"G2 VERDICT: {'✅ PASSED — real-money use may be considered (re-run before acting).' if passed else '❌ NOT PASSED — the edge scanner stays PAPER-ONLY.'}")
    emit("(A NOT-PASSED verdict is a successful outcome: loss prevention.)")
    emit("=" * 76)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"\n💾 wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
