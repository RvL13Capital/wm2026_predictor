#!/usr/bin/env python3
"""
Rigorous out-of-sample calibration suite for the 1X2 probabilities.

Reports the three standard proper scores on the 2014/2018/2022 group stage:
  - RPS (Ranked Probability Score) — the ordinal gold standard for football 1X2
    (it punishes predicting Away when the result is Home harder than predicting Draw).
  - Brier score (multiclass).
  - Log-loss.
Each is compared to a naive 1/3-1/3-1/3 baseline. Pure Python — no numpy — to match
the project's zero-dependency design.

Honest framing: the naive uniform baseline is WEAK. Beating it is necessary, not sufficient.
A true "strong baseline" (the closing bookmaker line) would need historical match odds we
don't hold for 2014-2022. RPS is the headline metric.

Output: stdout (and validation/calibration.txt)
"""
import os, sys, csv, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import predictor
import backtest_wm2014 as w14, backtest_wm2018 as w18, backtest_wm2022 as w22

ELO = {2014: w14.PRE_WM2014_ELO, 2018: w18.PRE_WM2018_ELO, 2022: w22.PRE_WM2022_ELO}


def rps_3way(probs, actual):
    """Ranked Probability Score, outcomes ordered (home, draw, away). Lower is better."""
    obs = [0.0, 0.0, 0.0]; obs[actual] = 1.0
    cp = co = total = 0.0
    for i in range(2):                       # cumulative over the first two categories
        cp += probs[i]; co += obs[i]; total += (cp - co) ** 2
    return total / 2.0


def brier_3way(probs, actual):
    obs = [0.0, 0.0, 0.0]; obs[actual] = 1.0
    return sum((probs[i] - obs[i]) ** 2 for i in range(3))


def logloss(probs, actual):
    return -math.log(max(probs[actual], 1e-15))


def evaluate():
    sums = {"rps": [0.0, 0.0], "brier": [0.0, 0.0], "ll": [0.0, 0.0]}   # [model, naive]
    n = 0
    u = (1 / 3, 1 / 3, 1 / 3)
    for y in (2014, 2018, 2022):
        path = f"data/wc{y}_results.csv"
        if not os.path.exists(path):
            continue
        for r in csv.DictReader(open(path)):
            if r.get("phase") != "GROUP":     # group-stage only (KO has no draw outcome)
                continue
            ga, gb = int(r["goals_a"]), int(r["goals_b"])
            actual = 0 if ga > gb else (1 if ga == gb else 2)
            row = {"team_a": r["team_a"], "team_b": r["team_b"], "phase": "GROUP",
                   "elo_a": ELO[y].get(r["team_a"], {}).get("elo", 1500),
                   "elo_b": ELO[y].get(r["team_b"], {}).get("elo", 1500)}
            res = predictor.predict_single_match(row)
            p = (res["p_home"], res["p_draw"], res["p_away"])
            for name, fn in (("rps", rps_3way), ("brier", brier_3way), ("ll", logloss)):
                sums[name][0] += fn(p, actual)
                sums[name][1] += fn(u, actual)
            n += 1

    out = []
    def emit(s=""): out.append(s); print(s)

    emit("=" * 64)
    emit(f"OUT-OF-SAMPLE CALIBRATION — {n} group matches (WC 2014/2018/2022)")
    emit("=" * 64)
    emit(f"{'metric':<10}{'model':>11}{'naive 1/3':>12}{'improvement':>14}")
    emit("-" * 47)
    for label, key in (("RPS", "rps"), ("Brier", "brier"), ("LogLoss", "ll")):
        m = sums[key][0] / n
        nv = sums[key][1] / n
        imp = (nv - m) / nv * 100 if nv > 0 else 0.0
        emit(f"{label:<10}{m:>11.4f}{nv:>12.4f}{imp:>13.1f}%")
    emit("-" * 47)
    emit("RPS is the headline (ordinal-aware). >5-8% over naive is solid for")
    emit("international football. NOTE: naive 1/3 is a weak baseline — a bookmaker")
    emit("close would be the real bar, but we lack historical 2014-22 match odds.")
    emit("=" * 64)

    os.makedirs("validation", exist_ok=True)
    with open("validation/calibration.txt", "w") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    evaluate()
