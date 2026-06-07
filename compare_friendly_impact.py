#!/usr/bin/env python3
"""
What did the June-2026 warm-up friendlies actually change in the bracket?

Runs the canonical SAMPLED pipeline twice with the SAME RNG seed (so the only difference is the
Elo input): once on pre-friendly ratings, once on data/elo_2026_post_friendlies.json. Diffs the
group winners, semifinalists, finalists and champion. Output: validation/friendly_impact.txt
"""
import os, sys, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictor
import make_bracket_html as mb

# same goal model as the canonical bracket
predictor.CONSTANTS["elo_baseline_goals"] = 1.35
predictor.CONSTANTS["elo_scale_factor"] = 1600
_orig_psm = predictor.predict_single_match
predictor.predict_single_match = lambda row, *a, **k: _orig_psm(
    {**row, "rho": 0.0, "alpha_a": 0.06, "alpha_b": 0.06}, *a, **k)


def run():
    mb.MODE = "sample"
    mb.RNG = random.Random(2026)          # identical random sequence each run
    games = mb.group_games()
    table = mb.standings_from_games(games)
    third_team, qualified = mb.best_thirds(table)
    assigned = mb.assign_thirds(third_team, qualified)
    ko = mb.build_ko(table, assigned)
    sf_teams = sorted({m["a"] for m in ko["SF"]} | {m["b"] for m in ko["SF"]})
    finalists = sorted({ko["FINAL"][0]["a"], ko["FINAL"][0]["b"]})
    winners = {g: table[g][0][0] for g in table}
    return {"champ": ko["CHAMP"], "final": finalists, "sf": sf_teams,
            "gw": winners, "final_conf": ko["FINAL"][0]["conf"]}


base = {t: dict(d) for t, d in predictor.WORLD_CUP_2026_TEAMS.items()}
pre = run()

post_json = json.load(open("data/elo_2026_post_friendlies.json", encoding="utf-8"))
for t, d in post_json.items():
    if t in predictor.WORLD_CUP_2026_TEAMS:
        predictor.WORLD_CUP_2026_TEAMS[t]["elo"] = d["elo"]
post = run()

out = []
def emit(s=""):
    out.append(s); print(s)

emit("=" * 74)
emit("JUNE-2026 FRIENDLIES — impact on the canonical sampled bracket")
emit("=" * 74)
emit("(same RNG seed both runs — every difference below is caused by the Elo update)\n")

emit(f"Champion:   {pre['champ']:<14} → {post['champ']:<14} "
     f"{'(unchanged)' if pre['champ']==post['champ'] else '⟵ CHANGED'}")
emit(f"Finalists:  {', '.join(pre['final'])}")
emit(f"        →   {', '.join(post['final'])}  {'(unchanged)' if pre['final']==post['final'] else '⟵ CHANGED'}")

gain_sf = [t for t in post["sf"] if t not in pre["sf"]]
lost_sf = [t for t in pre["sf"] if t not in post["sf"]]
emit(f"\nSemifinalists pre : {', '.join(pre['sf'])}")
emit(f"Semifinalists post: {', '.join(post['sf'])}")
if gain_sf or lost_sf:
    emit(f"   in : {', '.join(gain_sf) or '—'}   |   out: {', '.join(lost_sf) or '—'}")
else:
    emit("   (final four unchanged)")

gw_changes = [(g, pre["gw"][g], post["gw"][g]) for g in sorted(pre["gw"]) if pre["gw"][g] != post["gw"][g]]
emit(f"\nGroup-winner changes ({len(gw_changes)} of {len(pre['gw'])} groups):")
if gw_changes:
    for g, a, b in gw_changes:
        emit(f"   Group {g}: {a} → {b}")
else:
    emit("   (none — every group winner unchanged)")

emit("\n" + "-" * 74)
emit("Biggest Elo moves driving any change:")
moved = sorted(((t, base[t]["elo"], predictor.WORLD_CUP_2026_TEAMS[t]["elo"]) for t in base
                if abs(predictor.WORLD_CUP_2026_TEAMS[t]["elo"] - base[t]["elo"]) > 1e-6),
               key=lambda x: abs(x[2] - x[1]), reverse=True)[:8]
for t, b0, b1 in moved:
    emit(f"   {t:<14}{b0:>7.0f} → {b1:>7.1f}  ({b1-b0:+.1f})")
emit("=" * 74)

os.makedirs("validation", exist_ok=True)
with open("validation/friendly_impact.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("\n💾 wrote validation/friendly_impact.txt", file=sys.stderr)
