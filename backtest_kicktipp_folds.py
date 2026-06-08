#!/usr/bin/env python3
"""
F9 — Honest out-of-sample Kicktipp backtest across THREE World Cups (2014, 2018, 2022).

WHY THIS EXISTS
---------------
The prior validation (validation/backtest_engine_real.md) conceded the optimized
engine *loses* on real WC2022 data (99 vs 104 Kicktipp pts) but defended keeping it
by appealing to a Monte-Carlo simulation. That argument is CIRCULAR: a MC sim that
samples outcomes from the model's OWN probability grids cannot validate that model —
it only measures self-consistency. R4 ("optimized beats baseline on historical data")
was therefore never honestly demonstrated.

This harness replaces that with a real out-of-sample test. For every actual match in
2014 + 2018 + 2022 (192 matches), each model emits its EV-optimal 4/3/2 tip using
ONLY pre-tournament (point-in-time) Elo — no lookahead — and is scored against the
real result.

SCORELINE CONVENTION
--------------------
Official result, standard Kicktipp: 90 min for group games; after-extra-time for
knockouts; penalty-shootout goals are NOT counted (a shootout game is scored as the
ET draw). All three datasets in data/wc20XX_results.csv follow this convention.

MODELS (both start from the SAME point-in-time Elo lambdas; the delta is purely the
engine's added probabilistic complexity, so this isolates whether that complexity pays)
  baseline   : independent Poisson            (rho=0,     alpha=0)
  optimized  : Dixon-Coles + Negative Binomial (rho=-0.05, alpha=0.05)

Both tip in group-mode (no penalty-inflated KO grid), so model and actuals use the
same shootout-excluded convention — apples to apples.

DATA PROVENANCE
---------------
- Pre-tournament Elo: PRE_WM20XX_ELO tables already in backtest_wm20XX.py (eloratings.net snapshots).
- Scorelines: data/wc{2014,2018,2022}_results.csv. 2014/2018 compiled from the public
  match record (knockout rounds and a sample of groups cross-checked against Wikipedia
  per-group pages; this pass corrected two transcription errors — 2014 third place was
  NED 3-0 BRA, and 2018 R16 was BEL 3-2 JPN). 2022 derived from data/wc2022_full.csv
  with the 5 shootout games converted from penalty-inflated to the ET draw.
"""
import os
import sys
import csv
from typing import Dict, List, Tuple

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import predictor
from predictor import MatchModelConfig, ModelDistribution
from backtest_wm2014 import PRE_WM2014_ELO
from backtest_wm2018 import PRE_WM2018_ELO
from backtest_wm2022 import PRE_WM2022_ELO

ELO_TABLES = {2014: PRE_WM2014_ELO, 2018: PRE_WM2018_ELO, 2022: PRE_WM2022_ELO}
RESULTS_CSV = {
    2014: "data/wc2014_results.csv",
    2018: "data/wc2018_results.csv",
    2022: "data/wc2022_results.csv",
}

MAX_GOALS = 12
MAX_TIP = 6
OPT_RHO = -0.05
OPT_ALPHA = 0.05


def load_results(path: str) -> List[dict]:
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out.append({
                "phase": row["phase"],
                "team_a": row["team_a"],
                "team_b": row["team_b"],
                "goals_a": int(row["goals_a"]),
                "goals_b": int(row["goals_b"]),
            })
    return out


def _elo(table: dict, team: str) -> float:
    if team not in table:
        raise KeyError(f"No pre-tournament Elo for {team!r} — team-name mismatch with the Elo table.")
    return float(table[team]["elo"])


def optimal_tip(elo_a: float, elo_b: float, optimized: bool) -> Tuple[int, int]:
    """EV-optimal 4/3/2 tip from point-in-time Elo lambdas."""
    la, lb = predictor.estimate_base_lambdas_from_elo("A", "B", elo_a, elo_b)
    config = MatchModelConfig(
        dist_type=ModelDistribution.NEGATIVE_BINOMIAL if optimized else ModelDistribution.POISSON,
        mu_a=la, mu_b=lb,
        alpha_a=OPT_ALPHA if optimized else 0.0,
        alpha_b=OPT_ALPHA if optimized else 0.0,
        rho=OPT_RHO if optimized else 0.0,
        max_goals=MAX_GOALS, max_tip=MAX_TIP,
    )
    tips, _, _ = predictor.solve_optimal_tip(config)
    return tips[0][0]


def _blank() -> dict:
    return {"pts": 0, "n": 0, "c4": 0, "c3": 0, "c2": 0, "c0": 0, "tend_hit": 0}


def _record(acc: dict, tip: Tuple[int, int], ga: int, gb: int):
    p = predictor.get_points(tip[0], tip[1], ga, gb)
    acc["pts"] += p
    acc["n"] += 1
    acc[{4: "c4", 3: "c3", 2: "c2", 0: "c0"}[p]] += 1
    if predictor.sign(tip[0] - tip[1]) == predictor.sign(ga - gb):
        acc["tend_hit"] += 1


def run_fold(year: int) -> Dict[str, dict]:
    table = ELO_TABLES[year]
    matches = load_results(RESULTS_CSV[year])
    base, opt = _blank(), _blank()
    for m in matches:
        ea, eb = _elo(table, m["team_a"]), _elo(table, m["team_b"])
        ga, gb = m["goals_a"], m["goals_b"]
        _record(base, optimal_tip(ea, eb, optimized=False), ga, gb)
        _record(opt, optimal_tip(ea, eb, optimized=True), ga, gb)
    return {"baseline": base, "optimized": opt}


def context_probe_2022() -> dict:
    """Isolated check of the CONTEXT layer (travel/weather/host) on real data, using the
    48 WC2022 GROUP matches only — the subset where context data exists and there is no
    KO penalty-inflation confound. Compares optimized-core vs optimized-core+context,
    both scored on the 90-minute result. (This is where the original F9 found context
    *cost* points.)"""
    table = PRE_WM2022_ELO
    ctx_rows = {}
    with open("data/wc2022_full.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("phase") == "GROUP":
                ctx_rows[(row["team_a"], row["team_b"])] = row
    core, ctx = _blank(), _blank()
    for (ta, tb), row in ctx_rows.items():
        ea, eb = _elo(table, ta), _elo(table, tb)
        ga, gb = int(row["goals_a"]), int(row["goals_b"])
        _record(core, optimal_tip(ea, eb, optimized=True), ga, gb)
        full = dict(row)
        full["elo_a"], full["elo_b"] = ea, eb
        res = predictor.predict_single_match(full)
        t = res["optimal_tip"].split(":")
        _record(ctx, (int(t[0]), int(t[1])), ga, gb)
    return {"core": core, "core+context": ctx}


def _fmt(label: str, a: dict) -> str:
    avg = a["pts"] / a["n"] if a["n"] else 0.0
    tend = 100 * a["tend_hit"] / a["n"] if a["n"] else 0.0
    return (f"  {label:<28}: {a['pts']:>4} pts  (avg {avg:.3f}/match, tendency {tend:.0f}%)  "
            f"[exact:{a['c4']:>2} diff:{a['c3']:>2} tend:{a['c2']:>2} miss:{a['c0']:>2}]")


def main():
    out = []
    def emit(s=""):
        out.append(s)
        print(s)

    emit("=" * 78)
    emit("F9 — OUT-OF-SAMPLE KICKTIPP BACKTEST (2014 + 2018 + 2022, point-in-time Elo)")
    emit("=" * 78)
    emit("Baseline = independent Poisson.  Optimized = Dixon-Coles + Negative Binomial.")
    emit("Both from identical pre-tournament Elo lambdas; scored 4/3/2 vs real results.")
    emit("")

    agg = {"baseline": _blank(), "optimized": _blank()}
    for year in (2014, 2018, 2022):
        fold = run_fold(year)
        emit(f"WC{year}  ({fold['baseline']['n']} matches)")
        emit(_fmt("Baseline (indep Poisson)", fold["baseline"]))
        emit(_fmt("Optimized (DC + NegBin)", fold["optimized"]))
        d = fold["optimized"]["pts"] - fold["baseline"]["pts"]
        emit(f"  {'Δ (optimized − baseline)':<28}: {d:+d} pts")
        emit("")
        for k in agg:
            for f in agg[k]:
                agg[k][f] += fold[k][f]

    emit("─" * 78)
    emit(f"AGGREGATE  ({agg['baseline']['n']} matches across 3 World Cups)")
    emit(_fmt("Baseline (indep Poisson)", agg["baseline"]))
    emit(_fmt("Optimized (DC + NegBin)", agg["optimized"]))
    delta = agg["optimized"]["pts"] - agg["baseline"]["pts"]
    emit(f"  {'Δ (optimized − baseline)':<28}: {delta:+d} pts "
         f"({delta / agg['baseline']['n']:+.3f}/match)")
    emit("")
    if delta > 0:
        emit(f"VERDICT: Optimized beats baseline by {delta} pts out-of-sample over 3 tournaments.")
        emit("         R4 acceptance criterion is MET on real historical data.")
    elif delta == 0:
        emit("VERDICT: Optimized exactly ties baseline out-of-sample. The added probabilistic")
        emit("         complexity yields NO measurable Kicktipp edge — R4 NOT met.")
    else:
        emit(f"VERDICT: Optimized LOSES to baseline by {abs(delta)} pts out-of-sample over 3")
        emit("         tournaments. On this real-data evidence the added probabilistic complexity")
        emit("         is NOT justified by Kicktipp points — R4 acceptance criterion NOT met.")
    emit("")

    emit("─" * 78)
    emit("SECONDARY — CONTEXT LAYER probe (WC2022 group matches only, 90-min results)")
    probe = context_probe_2022()
    emit(_fmt("Optimized core (no context)", probe["core"]))
    emit(_fmt("+ context (travel/wx/host)", probe["core+context"]))
    cd = probe["core+context"]["pts"] - probe["core"]["pts"]
    emit(f"  {'Δ (context − core)':<28}: {cd:+d} pts")
    emit("")
    emit("NOTE: A 192-match backtest is still a small sample; single-tournament swings are")
    emit("      noisy. This measures Kicktipp-point yield only, not probabilistic calibration")
    emit("      (Brier/log-loss), which a points metric cannot capture.")
    emit("=" * 78)

    report_path = os.path.join("validation", "backtest_folds_2014_2018_2022.txt")
    with open(report_path, "w") as f:
        f.write("\n".join(out) + "\n")
    print(f"\n💾 Report written to {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
