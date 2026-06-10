#!/usr/bin/env python3
"""
Compute consistent pre-tournament Elo for WC 2006–2022 from the full international match history,
so the calibration backtest can run uniformly across five World Cups (the repo's per-tournament
PRE_WM*_ELO dicts are hand-curated from different snapshots and the 2022 one is anomalously scaled).

Method: World Football Elo Ratings (eloratings.net) — run forward from 1872 over every international
match. K by competition (WC 60 / continental-final 50 / qualifier 40 / other 30 / friendly 20),
goal-difference multiplier, +100 home advantage (0 at neutral venues). Snapshot each team's rating
the day before each WC kicks off. A single linear rescale (fit on the tight 2014+2018 overlap with
the existing dicts) puts it on the eloratings scale, so the engine's bg/sf transfer unchanged.

DATA: needs the martj42 "International football results 1872–2024" dataset (Kaggle:
martj42/international-football-results-from-1872-to-2017 -> results.csv). NOT committed (licensed,
3.7MB). Pass its path. Validation reproduced the existing dicts to ~21 Elo MAE on 2014/2018.

Output: data/historical_elo_2006_2022.json   (the rescaled snapshots — small, committed)
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WC_START = {2006: "2006-06-09", 2010: "2010-06-11", 2014: "2014-06-12",
            2018: "2018-06-14", 2022: "2022-11-20"}


def k_factor(tournament):
    t = tournament.lower()
    if "world cup" in t and "qual" not in t:
        return 60
    if "qualif" in t:
        return 40
    if any(x in t for x in ["uefa euro", "copa am", "african cup", "afc asian", "gold cup",
                            "confederations", "nations league", "olympic"]) and "qualif" not in t:
        return 50
    if "friendly" in t:
        return 20
    return 30


def gd_mult(gd):
    return 1.0 if gd <= 1 else 1.5 if gd == 2 else 1.75 + (gd - 3) / 8.0


def compute_snapshots(results_csv):
    elo = {}
    def R(t):
        return elo.get(t, 1500.0)
    snap = {}
    for r in sorted(csv.DictReader(open(results_csv)), key=lambda r: r["date"]):
        d = r["date"]
        for y, wd in WC_START.items():
            if y not in snap and d >= wd:
                snap[y] = dict(elo)
        try:
            hs, as_ = int(r["home_score"]), int(r["away_score"])
        except (ValueError, TypeError):
            continue
        h, a = r["home_team"], r["away_team"]
        ha = 0 if r["neutral"].upper() == "TRUE" else 100
        we = 1.0 / (10 ** (-(R(h) + ha - R(a)) / 400) + 1)
        w = 1.0 if hs > as_ else 0.5 if hs == as_ else 0.0
        delta = k_factor(r["tournament"]) * gd_mult(abs(hs - as_)) * (w - we)
        elo[h] = R(h) + delta
        elo[a] = R(a) - delta
    return snap


def rescale(snap):
    """Linear-fit ref = a + b*mine on the tight 2014+2018 overlap with the existing eloratings dicts."""
    import backtest_wm2014 as w14, backtest_wm2018 as w18
    pts = []
    for y, ref in [(2014, w14.PRE_WM2014_ELO), (2018, w18.PRE_WM2018_ELO)]:
        for t, info in ref.items():
            if t in snap[y]:
                pts.append((snap[y][t], info["elo"]))
    n = len(pts); mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
    b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sum((p[0] - mx) ** 2 for p in pts)
    a = my - b * mx
    print(f"[elo] rescale ref ~= {a:.0f} + {b:.3f}*mine  (n={n} anchor pts)", file=sys.stderr)
    return {y: {t: round(a + b * e, 1) for t, e in s.items()} for y, s in snap.items()}


def main():
    results = sys.argv[1] if len(sys.argv) > 1 else "/tmp/intl/results.csv"
    if not os.path.exists(results):
        sys.exit(f"need martj42 results.csv (Kaggle) at {results} — see module docstring")
    resc = rescale(compute_snapshots(results))
    out = os.path.join(HERE, "data", "historical_elo_2006_2022.json")
    json.dump({str(y): resc[y] for y in sorted(resc)}, open(out, "w"), indent=0)
    print(f"[elo] wrote {out}  ({sorted(resc)} World Cups)", file=sys.stderr)


if __name__ == "__main__":
    main()
