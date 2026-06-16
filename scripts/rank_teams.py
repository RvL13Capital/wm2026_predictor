#!/usr/bin/env python3
"""Team & Player evaluation/ranking from the games played so far (read-only, S20-adjacent).

Fuses, for every team, four honest signals into one power ranking:

  1. Pre-tournament rating  = predictor Elo (post-friendlies overlay) + squad-value VORP
                              + injury Elo (the exact stack matchday_tips/the engines use).
  2. Observed form          = a World-Football-Elo update from each PLAYED match in
                              live_state.json — goal-difference-weighted, World-Cup K=60,
                              with host home-advantage + a small altitude nudge folded into
                              the EXPECTATION so beating a minnow at home/altitude is scored
                              for what it is (this is the "context of the games" term).
  3. Performance vs xExp     = (actual result − rating-expected result), surfaced per match
                              so over/under-performers are visible, not just the new number.
  4. Forward probabilities   = champion% / semifinal% / group-win% from the RESULTS-CONDITIONED
                              vectorized re-sim (data/resim_*_live.json) — the canonical sim.

Players (Golden Boot) are read from the scalar bonusfragen sheet's Torschützenkönig block
(player-level shares). NOTE: this is the pre-tournament goal-share estimate — real per-goal
scorer data is not ingested here (we have none; it must be supplied). Honest by construction.

This is READ-ONLY analytics: it does NOT mutate the sealed engine, ratings, or any sim. It only
reads live_state.json + a conditioned re-sim json + the bonusfragen sheet, and prints/saves a report.

    python3 scripts/rank_teams.py [--live-state data/live_state.json]
        [--resim data/resim_20260616_live.json] [--bonus data/bonusfragen_20260616.txt]
        [--output data/team_player_ranking_YYYYMMDD.txt]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import predictor
import tournament_bonusfragen as tbf

# --- context constants (folded into the EXPECTATION of a played match, not the rating) ---
HOST_HOME_ADV = 60.0          # Elo points added to a host team's expectation when it plays at home
ALTITUDE_ADV = 25.0           # extra expectation nudge for a high-altitude home team (Mexico City etc.)
WC_K = 60.0                   # World Football Elo K-factor for a World Cup match
HIGH_ALTITUDE_HOSTS = {"Mexico"}   # Mexico City / Guadalajara / Monterrey are materially elevated


def effective_pre_rating():
    """Each team's pre-tournament rating = base Elo + squad VORP + injury Elo (the engine stack).

    Restricted to the 48-team field (GROUPS): the Elo table also carries non-qualified
    reference nations (Denmark, Cameroon, …) that must not pollute the tournament ranking.
    """
    squad = tbf.compute_squad_elo_adjustments() if tbf.SQUAD_MARKET_VALUES else {}
    field = {t for teams in tbf.GROUPS.values() for t in teams}
    out = {}
    for team in field:
        data = predictor.WORLD_CUP_2026_TEAMS.get(team)
        if not data:
            continue
        out[team] = (float(data["elo"]) + float(squad.get(team, 0.0))
                     + float(tbf.INJURY_ELO_ADJUSTMENTS.get(team, 0.0)))
    return out, squad


def _g_weight(gd):
    """World-Football-Elo goal-difference multiplier."""
    agd = abs(gd)
    if agd <= 1:
        return 1.0
    if agd == 2:
        return 1.5
    return (11.0 + agd) / 8.0


def _expected(elo_a, elo_b):
    """Logistic expected score for A given the two ratings."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def apply_results(pre, live_state):
    """Walk played matches, return (post_rating, per_match_rows). Pairing-keyed 'A vs B': [ga, gb]."""
    post = dict(pre)
    rows = []
    for key, score in live_state.items():
        if " vs " not in key or not isinstance(score, list) or len(score) != 2:
            continue
        a, b = (s.strip() for s in key.split(" vs ", 1))
        if a not in post or b not in post:
            continue
        ga, gb = int(score[0]), int(score[1])
        # context: host home advantage + altitude folded into the expectation
        ctx = []
        adv_a = adv_b = 0.0
        if a in tbf.HOST_TEAMS:
            adv_a += HOST_HOME_ADV; ctx.append(f"{a} home")
            if a in HIGH_ALTITUDE_HOSTS:
                adv_a += ALTITUDE_ADV; ctx.append("altitude")
        if b in tbf.HOST_TEAMS:
            adv_b += HOST_HOME_ADV; ctx.append(f"{b} home")
            if b in HIGH_ALTITUDE_HOSTS:
                adv_b += ALTITUDE_ADV; ctx.append("altitude")
        w_e = _expected(post[a] + adv_a, post[b] + adv_b)   # A's context-adjusted expectation
        w_a = 1.0 if ga > gb else 0.5 if ga == gb else 0.0
        g = _g_weight(ga - gb)
        delta = WC_K * g * (w_a - w_e)
        post[a] += delta
        post[b] -= delta
        rows.append({"a": a, "b": b, "ga": ga, "gb": gb, "w_a": w_a, "w_e": w_e,
                     "delta": delta, "ctx": ", ".join(ctx)})
    return post, rows


def parse_golden_boot(bonus_path):
    """Pull player-level Golden Boot shares from the scalar bonusfragen sheet's Torschützenkönig block."""
    if not bonus_path or not os.path.exists(bonus_path):
        return []
    players = []
    pat = re.compile(r"([A-Za-zÀ-ÿ' .-]+?)\s+([\d.]+)%\s+\(([^)]+)\)")
    in_block = False
    with open(bonus_path, encoding="utf-8") as f:
        for line in f:
            low = line.lower()
            if "torschützenkönig" in low or "golden boot" in low:
                in_block = True
                continue
            if in_block:
                m = pat.search(line)
                if m:
                    team, pct, player = m.group(1).strip(), float(m.group(2)), m.group(3).strip()
                    players.append((player, team, pct))
                elif players and ("─" in line or "═" in line or "╚" in line):
                    break
    # de-dupe keep first (the ranked panel), cap 10
    seen, out = set(), []
    for p, t, pct in players:
        if p not in seen:
            seen.add(p); out.append((p, t, pct))
    return out[:10]


def main():
    ap = argparse.ArgumentParser(description="Team & Player evaluation from games played")
    ap.add_argument("--live-state", default="data/live_state.json")
    ap.add_argument("--resim", default="data/resim_20260616_live.json")
    ap.add_argument("--bonus", default="data/bonusfragen_20260616.txt")
    ap.add_argument("--output")
    ap.add_argument("--top", type=int, default=24, help="How many teams to print in the ranking")
    args = ap.parse_args()

    with open(args.live_state, encoding="utf-8") as f:
        live_state = json.load(f)
    resim = {}
    if os.path.exists(args.resim):
        with open(args.resim, encoding="utf-8") as f:
            resim = json.load(f)
    champ = (resim.get("champion", {}) or {}).get("all", {})
    sf = (resim.get("semifinalists", {}) or {}).get("probabilities", {})
    gw = {}
    for g, d in (resim.get("group_winners", {}) or {}).items():
        for team, p in (d.get("all", {}) or {}).items():
            gw[team] = (g, p)

    pre, _ = effective_pre_rating()
    post, rows = apply_results(pre, live_state)
    played = {r["a"] for r in rows} | {r["b"] for r in rows}

    L = []
    L.append("=" * 74)
    L.append("  WM 2026 — TEAM & PLAYER EVALUATION  (read-only; through games played)")
    L.append("=" * 74)
    L.append("  Rating = post-friendlies Elo + squad VORP + injury Elo, re-rated from")
    L.append(f"  played results (World-Football-Elo, K={WC_K:.0f}, GD-weighted; host +{HOST_HOME_ADV:.0f}")
    L.append(f"  & altitude +{ALTITUDE_ADV:.0f} folded into expectation). Champion%/SF% = results-")
    L.append("  conditioned vectorized re-sim. ✓played  ·  ±Δ = form move from MD1.")
    L.append("")

    # --- per-match performance vs expectation ---
    L.append("── MD1 performance vs expectation " + "─" * 40)
    for r in sorted(rows, key=lambda x: -abs(x["delta"])):
        sign = "＋" if r["delta"] >= 0 else "－"
        edge = (r["w_a"] - r["w_e"])
        verdict = "OVER" if edge > 0.10 else "UNDER" if edge < -0.10 else "≈par"
        ctx = f"  [{r['ctx']}]" if r["ctx"] else ""
        L.append(f"  {r['a']:>14} {r['ga']}:{r['gb']} {r['b']:<14}  "
                 f"xW(A)={r['w_e']*100:4.0f}%  {verdict:<5} {sign}{abs(r['delta']):4.1f}{ctx}")
    L.append("")

    # --- team power ranking ---
    L.append("── TEAM POWER RANKING " + "─" * 52)
    L.append(f"  {'#':>2}  {'Team':<15}{'pre':>7}{'Δ':>6}{'post':>7}   {'Champ%':>6} {'SF%':>5}  MD1")
    order = sorted(post, key=lambda t: -post[t])
    for i, team in enumerate(order[:args.top], 1):
        d = post[team] - pre[team]
        ds = f"{d:+.0f}" if abs(d) >= 0.5 else "  ·"
        c = champ.get(team, 0.0) * 100
        s = sf.get(team, 0.0) * 100
        # MD1 line for this team
        md1 = ""
        for r in rows:
            if team in (r["a"], r["b"]):
                if r["a"] == team:
                    md1 = f"{r['ga']}:{r['gb']} v {r['b']}"
                else:
                    md1 = f"{r['gb']}:{r['ga']} v {r['a']}"
                break
        mark = "✓" if team in played else " "
        L.append(f"  {i:>2}  {team:<15}{pre[team]:>7.0f}{ds:>6}{post[team]:>7.0f}   "
                 f"{c:>5.1f}% {s:>4.1f}% {mark}{md1}")
    L.append("")

    # --- biggest movers ---
    movers = sorted(((t, post[t] - pre[t]) for t in played), key=lambda x: -x[1])
    if movers:
        up = movers[0]; down = movers[-1]
        L.append(f"  ▲ biggest riser: {up[0]} {up[1]:+.0f}    ▼ biggest faller: {down[0]} {down[1]:+.0f}")
        L.append("")

    # --- player ranking (Golden Boot) ---
    players = parse_golden_boot(args.bonus)
    L.append("── PLAYER RANKING — GOLDEN BOOT " + "─" * 42)
    if players:
        L.append("  (pre-tournament goal-share × expected team goals — NOT real scorer data)")
        for i, (player, team, pct) in enumerate(players, 1):
            L.append(f"  {i:>2}  {player:<18} {team:<14} {pct:>5.1f}%")
    else:
        L.append("  (no bonusfragen sheet found — run tournament_bonusfragen.py first)")
    L.append("")
    L.append("  ⚠ No real per-game xG / shots / goalscorer data ingested — scoreline + ratings")
    L.append("    only. Supply per-match stats to upgrade the form term and player eval.")
    L.append("=" * 74)

    out = "\n".join(L)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"wrote {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
