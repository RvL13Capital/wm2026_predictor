#!/usr/bin/env python3
"""
Empirically test the MD3 game-theory regimes against the real 2014/2018/2022 group
stages — the same "let the data decide" discipline we used to kill the lambda retune.

Each historical MD3 match is bucketed by the FROZEN post-MD2 table, using STRICT,
tiebreak-free top-2 mathematics (32-team format: top 2 advance, no best-thirds), by
enumerating every outcome of the two remaining group matches:

  DEAD_RUBBER - both teams' top-2 fate already settled regardless of this match
  BISCOTTO    - a draw guarantees BOTH teams top-2 (and at least one isn't already safe)
  MUST_WIN    - a draw eliminates BOTH from top-2 (only a win gives either a chance)
  ASYMMETRIC  - exactly one team's fate is settled; the other plays for its life
  STANDARD    - the usual win-to-advance / draw-is-risky tension

For each bucket it compares ACTUAL outcomes against the BASE model's expectation
(Elo -> lambda at bg1.35/sf1600, NB alpha=0.06, rho=0 — the bracket's base, NO context,
NO MD3 modifier) on goals/game, draw rate, blowout rate (|margin|>=3), high-scoring
rate (total>=4), and reports the IMPLIED form multiplier (actual GPG / expected GPG)
next to the magnitude the production heuristic currently assumes.

Output: validation/md3_regime_backtest.txt
"""
import os, sys, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import predictor
from predictor import MatchModelConfig, ModelDistribution, generate_joint_grid, get_grid_val
import backtest_wm2014 as w14, backtest_wm2018 as w18, backtest_wm2022 as w22

GROUPS = {2014: w14.WM2014_GROUPS, 2018: w18.WM2018_GROUPS, 2022: w22.WM2022_GROUPS}
ELO    = {2014: w14.PRE_WM2014_ELO, 2018: w18.PRE_WM2018_ELO, 2022: w22.PRE_WM2022_ELO}
YEARS  = (2014, 2018, 2022)

# production heuristic's assumed symmetric form multiplier per regime (from _get_md3_mods)
ASSUMED_FORM = {"BISCOTTO": 0.60, "MUST_WIN": 1.25, "DEAD_RUBBER": 0.85,
                "ASYMMETRIC": 1.00, "STANDARD": 1.00}


# ---- strict top-2 regime classification (enumerate both remaining matches) ----
RES = ("home", "away", "draw")

def _apply(p, x, y, res):
    p = dict(p)
    if res == "home": p[x] += 3
    elif res == "away": p[y] += 3
    else: p[x] += 1; p[y] += 1
    return p

def classify(base_pts, a, b, c, d):
    """a,b = the MD3 match; c,d = the other MD3 match in the group."""
    teams = (a, b, c, d)
    finals = [_apply(_apply(base_pts, a, b, ab), c, d, cd) for ab in RES for cd in RES]
    draw_finals = [_apply(_apply(base_pts, a, b, "draw"), c, d, cd) for cd in RES]
    g2 = lambda p, t: sum(1 for o in teams if o != t and p[o] >= p[t]) <= 1   # guaranteed top-2
    p2 = lambda p, t: sum(1 for o in teams if o != t and p[o] >  p[t]) <= 1   # possibly top-2

    a_settled = all(g2(f, a) for f in finals) or all(not p2(f, a) for f in finals)
    b_settled = all(g2(f, b) for f in finals) or all(not p2(f, b) for f in finals)
    draw_locks = all(g2(f, a) and g2(f, b) for f in draw_finals)
    draw_kills = all((not p2(f, a)) and (not p2(f, b)) for f in draw_finals)

    if a_settled and b_settled: return "DEAD_RUBBER"
    if draw_locks:              return "BISCOTTO"
    if draw_kills:              return "MUST_WIN"
    if a_settled or b_settled:  return "ASYMMETRIC"
    return "STANDARD"


# ---- base-model expectation for one fixture ----
def base_expectation(year, a, b):
    ea = ELO[year].get(a, {}).get("elo", 1500)
    eb = ELO[year].get(b, {}).get("elo", 1500)
    diff = ea - eb
    la = 1.35 * 10 ** (diff / 1600.0)
    lb = 1.35 * 10 ** (-diff / 1600.0)
    grid = generate_joint_grid(MatchModelConfig(
        dist_type=ModelDistribution.NEGATIVE_BINOMIAL, mu_a=la, mu_b=lb,
        alpha_a=0.06, alpha_b=0.06, rho=0.0, max_goals=10))
    e_total = e_draw = e_blow = e_high = 0.0
    for x in grid:
        for y, p in grid[x].items():
            e_total += (x + y) * p
            if x == y: e_draw += p
            if abs(x - y) >= 3: e_blow += p
            if x + y >= 4: e_high += p
    return e_total, e_draw, e_blow, e_high


# ---- replay the group stages and collect MD3 matches ----
def md3_matches(year):
    rows = [r for r in csv.DictReader(open(f"data/wc{year}_results.csv")) if r["phase"] == "GROUP"]
    out = []
    for gname, teams in GROUPS[year].items():
        tset = set(teams)
        gms = [(r["team_a"], r["team_b"], int(r["goals_a"]), int(r["goals_b"]))
               for r in rows if r["team_a"] in tset and r["team_b"] in tset]
        assert len(gms) == 6, f"{year} group {gname}: expected 6 games, got {len(gms)}"
        md12, md3 = gms[:4], gms[4:]                      # CSV order = MD1,MD1,MD2,MD2,MD3,MD3
        pts = {t: 0 for t in teams}
        for ta, tb, ga, gb in md12:
            if ga > gb: pts[ta] += 3
            elif gb > ga: pts[tb] += 3
            else: pts[ta] += 1; pts[tb] += 1
        for ta, tb, ga, gb in md3:
            c, d = [t for t in teams if t not in (ta, tb)]
            out.append((year, gname, ta, tb, ga, gb, classify(pts, ta, tb, c, d)))
    return out


def main():
    matches = [m for y in YEARS for m in md3_matches(y)]
    buckets = {}
    for (year, g, a, b, ga, gb, reg) in matches:
        et, ed, eb_, eh = base_expectation(year, a, b)
        rec = {"act_total": ga + gb, "act_draw": int(ga == gb), "act_blow": int(abs(ga - gb) >= 3),
               "act_high": int(ga + gb >= 4), "e_total": et, "e_draw": ed, "e_blow": eb_, "e_high": eh,
               "lbl": f"{year} {g}: {a} {ga}-{gb} {b}"}
        buckets.setdefault(reg, []).append(rec)

    out = []
    def emit(s=""): out.append(s); print(s)

    emit("=" * 92)
    emit(f"MD3 GAME-THEORY REGIME BACKTEST — {len(matches)} real MD3 matches (2014/2018/2022, 32-team)")
    emit("=" * 92)
    emit("Base = Elo->λ (bg1.35 sf1600) · NB α0.06 · ρ0 · no context · no MD3 modifier.")
    emit("'implied form' = actual GPG / expected GPG  (what the data says the λ multiplier SHOULD be).")
    emit("")
    hdr = f"{'regime':<12} {'N':>3} | {'GPG act/exp':>13} {'implied':>8} | {'draw act/exp':>13} | {'blow act/exp':>13} | {'hi act/exp':>13}"
    emit(hdr); emit("-" * len(hdr))

    order = ["BISCOTTO", "MUST_WIN", "DEAD_RUBBER", "ASYMMETRIC", "STANDARD"]
    for reg in order:
        recs = buckets.get(reg, [])
        n = len(recs)
        if n == 0:
            emit(f"{reg:<12} {0:>3} |  (none observed)")
            continue
        at = sum(r["act_total"] for r in recs) / n; et = sum(r["e_total"] for r in recs) / n
        ad = sum(r["act_draw"] for r in recs) / n;  ed = sum(r["e_draw"] for r in recs) / n
        ab = sum(r["act_blow"] for r in recs) / n;  eb_ = sum(r["e_blow"] for r in recs) / n
        ah = sum(r["act_high"] for r in recs) / n;  eh = sum(r["e_high"] for r in recs) / n
        implied = at / et if et > 0 else float("nan")
        emit(f"{reg:<12} {n:>3} | {at:>5.2f}/{et:<5.2f}{'':1} {implied:>7.2f}x | "
             f"{ad*100:>4.0f}%/{ed*100:<4.0f}% | {ab*100:>4.0f}%/{eb_*100:<4.0f}% | {ah*100:>4.0f}%/{eh*100:<4.0f}%")

    emit("")
    emit("ASSUMED (production _get_md3_mods) vs IMPLIED (data) symmetric form multiplier:")
    for reg in order:
        recs = buckets.get(reg, [])
        if not recs:
            emit(f"  {reg:<12} assumed {ASSUMED_FORM[reg]:.2f}x   implied   n/a (0 matches)"); continue
        at = sum(r["act_total"] for r in recs) / len(recs); et = sum(r["e_total"] for r in recs) / len(recs)
        imp = at / et if et > 0 else float("nan")
        verdict = ("MATCHES" if abs(imp - ASSUMED_FORM[reg]) < 0.10 else
                   "WEAKER than assumed" if (ASSUMED_FORM[reg] - 1) * (imp - 1) > 0 and abs(imp - 1) < abs(ASSUMED_FORM[reg] - 1) else
                   "WRONG DIRECTION" if (ASSUMED_FORM[reg] - 1) * (imp - 1) < 0 else "STRONGER than assumed")
        emit(f"  {reg:<12} assumed {ASSUMED_FORM[reg]:.2f}x   implied {imp:>5.2f}x   ({len(recs)} matches → {verdict})")

    # list the rare, high-conviction buckets match-by-match (tiny N — eyeball them)
    for reg in ("BISCOTTO", "MUST_WIN"):
        recs = buckets.get(reg, [])
        emit("")
        emit(f"{reg} matches (n={len(recs)}):")
        for r in recs:
            emit(f"   {r['lbl']:<34} total {r['act_total']} (exp {r['e_total']:.1f}){'  DRAW' if r['act_draw'] else ''}")

    emit("")
    emit("-" * 92)
    emit("CAVEAT: 48 MD3 matches / 5 buckets → tiny per-bucket N. Treat single-digit buckets as")
    emit("anecdote, not signal (same small-sample trap that overfit the λ grid). Buckets here use the")
    emit("STRICT top-2 lock; production _get_md3_mods uses looser point buckets, so it fires far more often.")
    emit("=" * 92)

    os.makedirs("validation", exist_ok=True)
    with open("validation/md3_regime_backtest.txt", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n💾 wrote validation/md3_regime_backtest.txt", file=sys.stderr)


if __name__ == "__main__":
    main()
