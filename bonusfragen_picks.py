#!/usr/bin/env python3
"""
WM2026 BONUSFRAGEN pick sheet — Normal (favorite) vs Dark Horse (contrarian), side by side.

Both come from the same Monte-Carlo probabilities (tournament_bonusfragen.run_monte_carlo).
- Normal      = argmax probability. Maximizes expected points. But in a pool, if the field
                also picks the favorite, being right gains you no ground.
- Dark horse  = best CREDIBLE pick outside the consensus top-2. You give up some win
                probability, but if it hits you jump a field that mostly backed the favorite.
                (Pool-differentiation play, not expected-points play.)

The user decides per question which to take. Probabilities are the model's; recall the model
has no demonstrated points edge over Elo ranking — its real use is exactly this: sizing which
longshots are credible enough to be worth a contrarian bet.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tournament_bonusfragen as t

N_SIMS = 20000
SEED = 42
CLOSE_GROUP_MARGIN = 0.12   # favorite within this of #2 → "live" group worth a dark horse


def main():
    res = t.run_monte_carlo(n_sims=N_SIMS, seed=SEED, verbose=False)
    out = []
    def emit(s=""):
        out.append(s); print(s)

    emit("=" * 76)
    emit(f"WM2026 BONUSFRAGEN — NORMAL vs DARK HORSE   ({N_SIMS:,} sims, seed {SEED})")
    emit("  Normal = favorite (max expected points).  Dark horse = best credible")
    emit("  contrarian outside the top-2 (pool differentiation if it hits).")
    emit("=" * 76)

    # ---- WELTMEISTER (champion) ----
    champ = sorted(res["champion"]["all"].items(), key=lambda x: x[1], reverse=True)
    normal = champ[0]
    dark = champ[2] if len(champ) > 2 else champ[-1]   # best outside the consensus top-2
    emit("\n■ WELTMEISTER (champion)")
    emit(f"   NORMAL     : {normal[0]:<14} {normal[1]*100:4.1f}%")
    emit(f"   DARK HORSE : {dark[0]:<14} {dark[1]*100:4.1f}%   "
         f"(give up {(normal[1]-dark[1])*100:.0f} pts of win prob; far less crowded)")
    emit("   field: " + " | ".join(f"{tm} {p*100:.0f}%" for tm, p in champ[:7]))

    # ---- FINALE (finalists / reach the final) — use semifinal probs as proxy for deep runs ----
    sf = sorted(res["semifinalists"]["probabilities"].items(), key=lambda x: x[1], reverse=True)
    top4 = sf[:4]
    emit("\n■ HALBFINALISTEN (pick 4)")
    emit(f"   NORMAL     : {', '.join(f'{tm} ({p*100:.0f}%)' for tm, p in top4)}")
    if len(sf) >= 6:
        weakest = top4[-1]
        dh = sf[4]   # best team just outside the top 4
        emit(f"   DARK HORSE : swap {weakest[0]} ({weakest[1]*100:.0f}%)  →  "
             f"{dh[0]} ({dh[1]*100:.0f}%)   (under-picked deep run)")
    emit("   next up: " + " | ".join(f"{tm} {p*100:.0f}%" for tm, p in sf[4:8]))

    # ---- TOP-SCORER TEAM (if available) ----
    ts = res.get("top_scorer_team")
    if isinstance(ts, dict) and ts.get("all"):
        tss = sorted(ts["all"].items(), key=lambda x: x[1], reverse=True)
        emit("\n■ TORSCHÜTZENKÖNIG-TEAM")
        emit(f"   NORMAL     : {tss[0][0]} ({tss[0][1]*100:.0f}%)")
        if len(tss) > 2:
            emit(f"   DARK HORSE : {tss[2][0]} ({tss[2][1]*100:.0f}%)")

    # ---- GRUPPENSIEGER (group winners): favorite always; dark horse only in live groups ----
    emit("\n■ GRUPPENSIEGER (per group — dark horse only where it's a real call)")
    gw = res["group_winners"]
    for g in sorted(gw.keys()):
        allp = sorted(gw[g]["all"].items(), key=lambda x: x[1], reverse=True)
        fav = allp[0]
        second = allp[1] if len(allp) > 1 else None
        if second and (fav[1] - second[1]) < CLOSE_GROUP_MARGIN:
            emit(f"   {g}: NORMAL {fav[0]} {fav[1]*100:.0f}%   |   DARK HORSE {second[0]} {second[1]*100:.0f}%   ← live")
        else:
            emit(f"   {g}: {fav[0]} {fav[1]*100:.0f}%  (safe — take the favorite)")

    emit("\n" + "=" * 76)
    emit("HOW TO USE: take NORMAL everywhere if you just want max expected points. Take a")
    emit("DARK HORSE on the champion (highest-leverage, season-ending question) and any 'live'")
    emit("group if you're chasing the field and need separation. Mix per your standing.")
    emit("=" * 76)

    with open("data/bonusfragen_picks_normal_vs_darkhorse.txt", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n💾 Saved to data/bonusfragen_picks_normal_vs_darkhorse.txt", file=sys.stderr)


if __name__ == "__main__":
    main()
