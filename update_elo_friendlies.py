#!/usr/bin/env python3
"""
Apply the June-2026 pre-World-Cup warm-up friendlies to the team Elo ratings, then write the
updated ratings for the 48 WC2026 teams to data/elo_2026_post_friendlies.json (consumed by
make_bracket_html.py when WM2026_USE_FRIENDLY_ELO=1).

Method = eloratings.net friendly update:
    E_a   = 1 / (1 + 10^((elo_b - elo_a)/400))          # neutral venue (no home bonus)
    Δ_a   = K · G · (S_a − E_a),  Δ_b = −Δ_a             # zero-sum
    K     = 20                                            # friendly weight (competitive is 40-60)
    G     = 1 (|gd|≤1), 1.5 (|gd|=2), (11+|gd|)/8 (|gd|≥3)   # goal-difference multiplier

Honesty notes:
  • These results are POST knowledge-cutoff (June 2026); sourced from match-result listings and
    cross-checked on the majors. Treat as verified-on-the-overlap, not authoritative.
  • Friendlies are deliberately low-weight (K=20 ⇒ ±5-18 Elo), so the bracket barely moves — that
    is the correct, honest magnitude, not a bug.
  • Non-WC sparring partners (Ireland, Chile, Serbia, …) only provide an OPPONENT rating for the
    expected-score term; their post-match Elo is not exported. Those ratings are ROUGH June-2026
    estimates (eloratings.net order of magnitude), flagged below.
  • Venue treated as neutral for every match (most warm-ups are on neutral/host ground); this is a
    simplification, not the per-match truth.
"""
import os, sys, csv, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictor

K = 20.0
CSV = "data/warmup_friendlies_2026.csv"
OUT = "data/elo_2026_post_friendlies.json"

# Rough June-2026 Elo for the non-WC sparring partners (opponent term only; NOT exported).
NON_WC_ELO = {
    "Republic of Ireland": 1680, "Peru": 1730, "Chile": 1820, "Bolivia": 1620,
    "El Salvador": 1490, "Venezuela": 1720, "Guatemala": 1500, "Serbia": 1850,
    "Nicaragua": 1410, "Dominican Republic": 1410, "Greece": 1780, "Madagascar": 1490,
    "Wales": 1790, "North Macedonia": 1700, "Trinidad and Tobago": 1450, "Iceland": 1690,
    "Kosovo": 1640, "Poland": 1820, "Ukraine": 1840, "Finland": 1660, "Gambia": 1500,
    "Andorra": 1180, "Russia": 1730, "Burundi": 1420, "Aruba": 1130, "Honduras": 1560,
}


# CSV spellings the shared mapping doesn't cover
LOCAL_ALIAS = {"united states": "USA", "congo dr": "DR Congo", "curacao": "Curaçao"}


def canon(name):
    """Resolve a CSV team name to its canonical key (WC dict or NON_WC_ELO)."""
    n = name.strip()
    if n in predictor.WORLD_CUP_2026_TEAMS or n in NON_WC_ELO:
        return n
    lo = n.lower()
    if lo in LOCAL_ALIAS:
        return LOCAL_ALIAS[lo]
    return predictor.TEAM_NAME_MAPPING.get(lo, n)


def gd_mult(gd):
    gd = abs(gd)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8.0


def main():
    elo = {t: float(d["elo"]) for t, d in predictor.WORLD_CUP_2026_TEAMS.items()}
    non_wc = dict(NON_WC_ELO)

    def get(t):
        if t in elo:
            return elo[t]
        if t in non_wc:
            return non_wc[t]
        return None

    def put(t, v):
        if t in elo:
            elo[t] = v
        elif t in non_wc:
            non_wc[t] = v

    base = dict(elo)                       # snapshot pre-friendly WC ratings
    games, skipped, unknown = [], [], set()
    for r in csv.DictReader(open(CSV)):
        a, b = canon(r["team_a"]), canon(r["team_b"])
        ea, eb = get(a), get(b)
        if ea is None or eb is None:
            for nm, e in ((a, ea), (b, eb)):
                if e is None:
                    unknown.add(nm)
            skipped.append((r["team_a"], r["team_b"]))
            continue
        ga, gb = int(r["goals_a"]), int(r["goals_b"])
        exp_a = 1.0 / (1.0 + 10 ** ((eb - ea) / 400.0))
        s_a = 1.0 if ga > gb else (0.5 if ga == gb else 0.0)
        delta = K * gd_mult(ga - gb) * (s_a - exp_a)
        put(a, ea + delta)
        put(b, eb - delta)
        games.append((a, b, ga, gb, delta))

    # report
    print("=" * 78)
    print(f"JUNE-2026 WARM-UP FRIENDLIES → Elo update  (K={K:.0f}, neutral venue)  ·  {len(games)} matches")
    print("=" * 78)
    if unknown:
        print("⚠ unmapped teams (matches skipped):", ", ".join(sorted(unknown)))
        for a, b in skipped:
            print(f"    skipped: {a} vs {b}")
        print()

    moved = sorted(((t, base[t], elo[t]) for t in elo if abs(elo[t] - base[t]) > 1e-6),
                   key=lambda x: abs(x[2] - x[1]), reverse=True)
    print(f"WC2026 teams that moved ({len(moved)} of {len(elo)}):\n")
    print(f"  {'team':<14}{'before':>8}{'after':>8}{'Δ':>8}   form")
    for t, b0, b1 in moved:
        gl = [g for g in games if g[0] == t or g[1] == t]
        form = " ".join(
            (f"{('W' if (g[4] > 0 and g[0] == t) or (g[4] < 0 and g[1] == t) else ('D' if abs(g[4]) < 1e-9 else 'L'))}"
             f"{g[2] if g[0]==t else g[3]}-{g[3] if g[0]==t else g[2]}"
             f"{'(' + (g[1] if g[0]==t else g[0]) + ')'}")
            for g in gl)
        print(f"  {t:<14}{b0:>8.0f}{b1:>8.1f}{b1-b0:>+8.1f}   {form}")

    # biggest risers/fallers headline
    if moved:
        up = [m for m in moved if m[2] > m[1]][:3]
        dn = [m for m in moved if m[2] < m[1]][:3]
        print("\n  ▲ risers:", ", ".join(f"{t} {b1-b0:+.0f}" for t, b0, b1 in up))
        print("  ▼ fallers:", ", ".join(f"{t} {b1-b0:+.0f}" for t, b0, b1 in dn))

    # export updated WC ratings (preserve rank field; rank re-sorted by new elo)
    ranked = sorted(elo, key=lambda t: elo[t], reverse=True)
    out = {t: {"elo": round(elo[t], 1), "rank": i + 1} for i, t in enumerate(ranked)}
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n💾 wrote {OUT}  ({len(out)} teams)")
    print(f"   regenerate bracket with: WM2026_USE_FRIENDLY_ELO=1 python3 make_bracket_html.py")


if __name__ == "__main__":
    main()
