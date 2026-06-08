#!/usr/bin/env python3
"""
Player-level Golden Boot (Torschützenkönig) prediction.

  expected_player_goals = (player's recent intl goals / team's recent intl goals)
                          × team's EXPECTED TOURNAMENT GOALS

The team term comes from the bonusfragen Monte Carlo (`team_expected_goals`), which already bakes in
both the team's scoring rate AND how deep it runs (more games -> more goals). The player term is each
player's share of his nation's recent goals. The two combine into expected tournament goals per player.

Player goals: martj42 `goalscorers.csv` (Kaggle, not committed — pass its path). HONEST CAVEATS:
  - goal SHARE is a form proxy — `goalscorers.csv` lists who scored, not who played, so there's no
    true per-90 rate; squad continuity is assumed.
  - the **Polymarket Golden Boot market is the sharper signal**; this is a structural estimate.
  - the Golden Boot is inherently high-variance (often a player who simply goes deep and gets hot).

    python3 goalscorer.py [goalscorers.csv] [--sims N] [--since YYYY-MM-DD]
"""
import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tournament_bonusfragen as tbf
import json
import ssl
import unicodedata
import urllib.request


def _norm(name):
    """Accent-insensitive lowercase key for matching market vs model player names."""
    return "".join(c for c in unicodedata.normalize("NFKD", name or "")
                   if not unicodedata.combining(c)).lower().strip()


def fetch_golden_boot():
    """Polymarket 'Golden Boot Winner' player outright -> {player: de-vigged P(win)}. {} if unavailable."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def getj(u):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        return json.loads(urllib.request.urlopen(req, context=ctx, timeout=40).read().decode())

    ev = []
    try:
        for off in range(0, 300, 100):
            pg = getj("https://gamma-api.polymarket.com/events?tag_slug=fifa-world-cup"
                      f"&closed=false&limit=100&offset={off}")
            if not pg:
                break
            ev += pg
    except Exception:
        return {}
    gb = next((e for e in ev if "golden boot" in (e.get("title") or "").lower()), None)
    if not gb:
        return {}
    raw = {}
    for m in gb.get("markets", []):
        name = (m.get("groupItemTitle") or "").strip()
        o, p = m.get("outcomes", "[]"), m.get("outcomePrices", "[]")
        try:
            if isinstance(o, str): o = json.loads(o)
            if isinstance(p, str): p = json.loads(p)
            ol = [str(x).lower() for x in o]
            if "yes" not in ol or len(o) != len(p):
                continue
            pr = float(p[ol.index("yes")])
        except (ValueError, TypeError, IndexError, json.JSONDecodeError):
            continue
        if name and pr > 0:
            raw[name] = pr
    tot = sum(raw.values())
    return {n: pr / tot for n, pr in raw.items()} if tot > 0 else raw

# engine team name -> martj42 goalscorers.csv name (only the mismatches)
TEAM_MAP = {
    "USA": "United States", "Czechia": "Czech Republic", "Bosnia": "Bosnia and Herzegovina",
}


def recent_goals(path, since):
    by = collections.defaultdict(collections.Counter)
    pens = collections.defaultdict(collections.Counter)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["date"] < since or r.get("own_goal", "").upper() == "TRUE":
            continue
        by[r["team"]][r["scorer"]] += 1
        if r.get("penalty", "").upper() == "TRUE":
            pens[r["team"]][r["scorer"]] += 1
    return by, pens


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gs = args[0] if args else "/tmp/intl/goalscorers.csv"
    sims = int(sys.argv[sys.argv.index("--sims") + 1]) if "--sims" in sys.argv else 1500
    since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "2023-01-01"
    if not os.path.exists(gs):
        sys.exit(f"need martj42 goalscorers.csv at {gs} — see module docstring")

    print(f"[gs] {sims}-sim tournament MC for team expected goals...", file=sys.stderr)
    teg = tbf.run_monte_carlo(n_sims=sims, verbose=False)["team_expected_goals"]
    by, pens = recent_goals(gs, since)

    teams2026 = [t for g in tbf.GROUPS.values() for t in g]
    rows, no_data = [], []
    for team in teams2026:
        mname = TEAM_MAP.get(team, team)
        scorers = by.get(mname, {})
        team_recent = sum(scorers.values())
        if team_recent == 0 or team not in teg:
            no_data.append(team)
            continue
        for player, goals in scorers.items():
            exp = (goals / team_recent) * teg[team]
            rows.append((exp, player, team, goals, pens[mname].get(player, 0)))
    rows.sort(reverse=True)
    import math

    # ── MARKET CORRECTION: blend toward the Polymarket Golden Boot outright (the sharp signal) ──
    # The deep Golden Boot market prices team depth, so pure-Elo artefacts (a focal scorer on an
    # Elo-overrated team) wash out. Model xGoals -> softmax win-prob so it's comparable to the market.
    W = 0.70
    player_team = {}
    for team in teams2026:
        for pl in by.get(TEAM_MAP.get(team, team), {}):
            player_team.setdefault(_norm(pl), (pl, team))
    xg = {_norm(pl): exp for exp, pl, team, goals, pk in rows}
    Z = sum(math.exp(v) for v in xg.values()) or 1.0
    p_model = {k: math.exp(v) / Z for k, v in xg.items()}

    market = fetch_golden_boot()
    p_market = {_norm(n): pr for n, pr in market.items()}
    have_market = bool(p_market)

    ranking = []
    for k, (disp, team) in player_team.items():
        pm, pmod = p_market.get(k, 0.0), p_model.get(k, 0.0)
        blend = (W * pm + (1 - W) * pmod) if have_market else pmod
        ranking.append((blend, disp, team, xg.get(k, 0.0), pm))
    s = sum(r[0] for r in ranking) or 1.0
    ranking = [(b / s, d, t, x, pm) for b, d, t, x, pm in ranking]
    ranking.sort(reverse=True)

    src = (f"{int(W*100)}% Polymarket Golden Boot market + {int((1-W)*100)}% structural model"
           if have_market else "structural model only (market unavailable)")
    print(f"\nGOLDEN BOOT — market-blended projection   [{src}]")
    print(f"{'#':>2}  {'player':<22} {'team':<13} {'blend%':>7} {'xGoals':>7} {'market%':>8}")
    print("  " + "-" * 64)
    for i, (b, disp, team, x, pm) in enumerate(ranking[:15], 1):
        print(f"{i:>2}  {disp:<22} {team:<13} {b*100:>6.1f}% {x:>7.2f} {pm*100:>7.1f}%")
    print(f"\n  >> projected Golden Boot: {ranking[0][1]} ({ranking[0][2]}) — {ranking[0][0]*100:.1f}% blended")
    if have_market:
        print("  market-corrected: the Golden Boot market prices team depth, so pure-Elo artefacts wash out.")
    else:
        print("  NB: structural estimate (market unavailable) — high-variance prop.")

    if "--json" in sys.argv:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "goldenboot.json")
        json.dump([{"rank": i, "player": d, "team": t, "prob": round(b, 4),
                    "xgoals": round(x, 2), "market_prob": round(pm, 4)}
                   for i, (b, d, t, x, pm) in enumerate(ranking[:15], 1)],
                  open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"[gs] wrote {out_path}", file=sys.stderr)
    if no_data:
        print(f"\n  (no recent scorers matched for: {', '.join(no_data)})", file=sys.stderr)


if __name__ == "__main__":
    main()
