#!/usr/bin/env python3
"""
BONUSFRAGEN backtest — the half of a Kicktipp pool that F9 never tested.

Match tips proved model-insensitive (the EV-optimal 4/3/2 tip barely moves). Bonusfragen
are different: you pick the argmax-EV answer from the tournament Monte-Carlo (champion,
semifinalists, group winners) for big fixed payouts, and per-match λ errors compound
through the bracket. So THIS is where model quality should convert to Kicktipp points.

Test (the bonusfragen analog of F9): for 2014 + 2018 + 2022, take the MC simulation's
argmax picks vs a trivial highest-pre-Elo baseline, and score both against the ACTUAL
outcomes in representative Kicktipp bonus points. If the MC machinery doesn't beat naive
Elo ranking, it adds no bonus-point value either.

Probabilities + actuals + point-in-time Elo all come from backtest_wm{2014,2018,2022}.py.
Point values are ILLUSTRATIVE (pool-specific); the MC-vs-naive comparison is the result.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib

YEARS = (2014, 2018, 2022)
N_SIMS = 20000
PTS = {"champion": 16, "sf": 6, "group": 4}   # illustrative Kicktipp bonus weights


def elo_rank(elo, teams=None):
    pool = teams if teams is not None else list(elo.keys())
    return sorted(pool, key=lambda t: elo[t]["elo"], reverse=True)


def score(champ, sf_set, gw_map, actual_champ, actual_sf, actual_gw):
    champ_hit = 1 if champ == actual_champ else 0
    sf_hits = len(sf_set & actual_sf)
    gw_hits = sum(1 for g in actual_gw if gw_map.get(g) == actual_gw[g])
    pts = champ_hit * PTS["champion"] + sf_hits * PTS["sf"] + gw_hits * PTS["group"]
    return pts, champ_hit, sf_hits, gw_hits


def main():
    out = []
    def emit(s=""):
        out.append(s); print(s)

    emit("=" * 82)
    emit("BONUSFRAGEN BACKTEST — MC simulation vs naive highest-Elo, scored vs actual outcomes")
    emit(f"  {len(YEARS)} World Cups, {N_SIMS:,} sims each, point-in-time Elo. "
         f"Points (illustrative): champion {PTS['champion']}, SF {PTS['sf']}/team, group winner {PTS['group']}/group.")
    emit("=" * 82)

    tot = {"mc": 0, "naive": 0}
    n_groups_total = 0
    for year in YEARS:
        mod = importlib.import_module(f"backtest_wm{year}")
        elo = getattr(mod, f"PRE_WM{year}_ELO")
        groups = getattr(mod, f"WM{year}_GROUPS")
        a_champ = mod.ACTUAL_CHAMPION
        a_sf = set(mod.ACTUAL_SF_TEAMS)
        a_gw = mod.ACTUAL_GROUP_WINNERS
        n_groups_total += len(a_gw)

        res = mod.run_backtest(N_SIMS, seed=year, verbose=False)
        cc, sfc, gwc = res["champion_counts"], res["semifinal_counts"], res["group_winner_counts"]
        n = res["n_sims"]

        # MC argmax-EV picks
        mc_champ = cc.most_common(1)[0][0]
        mc_sf = {t for t, _ in sfc.most_common(4)}
        mc_gw = {g: gwc[g].most_common(1)[0][0] for g in groups}
        # Naive highest-Elo picks
        nv_champ = elo_rank(elo)[0]
        nv_sf = set(elo_rank(elo)[:4])
        nv_gw = {g: elo_rank(elo, groups[g])[0] for g in groups}

        mc = score(mc_champ, mc_sf, mc_gw, a_champ, a_sf, a_gw)
        nv = score(nv_champ, nv_sf, nv_gw, a_champ, a_sf, a_gw)
        tot["mc"] += mc[0]; tot["naive"] += nv[0]

        emit("")
        emit(f"WC{year}  (actual champion: {a_champ})")
        emit(f"  MC pick    champion={mc_champ} ({cc[mc_champ]/n*100:.0f}%)  "
             f"→ champ {'✓' if mc[1] else '✗'}, SF {mc[2]}/4, groups {mc[3]}/{len(a_gw)}  = {mc[0]} pts")
        emit(f"  Naive Elo  champion={nv_champ}  "
             f"→ champ {'✓' if nv[1] else '✗'}, SF {nv[2]}/4, groups {nv[3]}/{len(a_gw)}  = {nv[0]} pts")
        emit(f"  Δ (MC − naive): {mc[0] - nv[0]:+d} pts")

    emit("")
    emit("─" * 82)
    max_pts = len(YEARS) * PTS["champion"] + len(YEARS) * 4 * PTS["sf"] + n_groups_total * PTS["group"]
    emit(f"AGGREGATE bonus points ({len(YEARS)} tournaments, max possible {max_pts}):")
    emit(f"  MC simulation : {tot['mc']}")
    emit(f"  Naive Elo     : {tot['naive']}")
    emit(f"  Δ (MC − naive): {tot['mc'] - tot['naive']:+d}")
    emit("")
    if tot["mc"] > tot["naive"]:
        emit("→ The MC machinery converts to MORE bonus points than naive Elo ranking — the place")
        emit("  where model quality actually pays. (Then recalibrating λ is worth testing here.)")
    elif tot["mc"] == tot["naive"]:
        emit("→ MC ties naive Elo ranking on bonus points — like the match-tip result, the extra")
        emit("  machinery adds no measurable Kicktipp value over the trivial heuristic.")
    else:
        emit("→ MC scores FEWER bonus points than naive Elo ranking here — the simulation's argmax")
        emit("  picks are no better (worse, on this sample) than just picking the highest-Elo team.")
    emit("")
    emit("CAVEAT: 3 tournaments is a tiny sample, and champion is near-unpredictable (top pick is")
    emit("only 16–33% likely and the favorite lost all 3). Group winners carry most of the points")
    emit("and are where any signal lives. Point weights are illustrative.")
    emit("=" * 82)

    with open("validation/backtest_bonusfragen.txt", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n💾 Report written to validation/backtest_bonusfragen.txt", file=sys.stderr)


if __name__ == "__main__":
    main()
