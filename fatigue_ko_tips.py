#!/usr/bin/env python3
"""Read-only KNOCKOUT runner: main KO tip vs differential fatigue+venue tip.

Knockout sibling of fatigue_tips.py (which is group-matchday only). For a KO round
it reconstructs each team's full match timeline (venue + date, all prior rounds)
from the FIFA calendar and fetches the per-venue kickoff forecast (open-meteo).

NOTE: rest/travel/altitude now live in the MAIN KO tip itself (the core consumes
prematch_alert.ko_travel_context inside build_ko_row), so this overlay applies ONLY
the increment the core lacks — heat[forecast @ kickoff hour] × congestion — on top
of the core's lambda_adj, to avoid double-counting travel. It rebuilds the SAME KO
shootout_total grid the main tip uses (fatigue_engine.fatigue_adjusted_ko_tip — NOT
the 90' draw grid). rest/mi columns are shown for context (now in the core).

ISOLATION CONTRACT: read-only. Drives lambdas from prematch_alert.compute_ko_tip,
applies the heat+congestion increment, prints a side column. Mutates nothing; the
main KO tips are unaffected by THIS file.

Usage:
    python3 fatigue_ko_tips.py --round R32
    python3 fatigue_ko_tips.py --round R16 --odds-snapshot data/polymarket_match_odds.json
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import prematch_alert as pa

import predictor
import weather_tips
import fatigue_engine
import fatigue_tips as ft          # reuse leg/team_load/_date/_winner/MIN_EV_MARGIN

ROOT = os.path.dirname(os.path.abspath(__file__))

ROUND_STAGE = {
    "R32": "Round of 32", "R16": "Round of 16", "QF": "Quarter-final",
    "SF": "Semi-final", "F": "Final",
}


def _desc(team):
    try:
        return team["TeamName"][0]["Description"]
    except Exception:
        return None


def build_timeline_all(raw):
    """{team: sorted [(date_iso, venue_key)]} over EVERY match with known teams +
    a resolvable venue (all rounds, not just First Stage). team_load then finds a
    team's previous match in ANY prior round — so an R16 fixture correctly sees the
    R32 game as the prior leg."""
    tl = defaultdict(list)
    for m in raw.get("Results", []):
        hn, an = pa.engine_name(_desc(m.get("Home"))), pa.engine_name(_desc(m.get("Away")))
        if not hn or not an:
            continue                       # slot not yet determined (future round)
        sd = m.get("Stadium") or {}
        venue = weather_tips.venue_key((sd.get("Name") or [{}])[0].get("Description", ""))
        for t in (hn, an):
            tl[t].append((m.get("Date"), venue))
    for t in tl:
        tl[t].sort()
    return tl


def round_fixtures(raw, stage_name):
    out = []
    for m in raw.get("Results", []):
        sn = m.get("StageName")
        if not (sn and stage_name in sn[0].get("Description", "")):
            continue
        home, away = pa.engine_name(_desc(m.get("Home"))), pa.engine_name(_desc(m.get("Away")))
        if not home or not away:
            continue                       # pairing not yet known
        sd = m.get("Stadium") or {}
        venue = weather_tips.venue_key((sd.get("Name") or [{}])[0].get("Description", ""))
        out.append((m.get("Date"), home, away, venue))
    out.sort()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Main KO tip vs differential fatigue+venue tip (isolated, read-only)")
    ap.add_argument("--round", required=True, choices=list(ROUND_STAGE), help="KO round")
    ap.add_argument("--odds-snapshot", default=None,
                    help="market snapshot (default: live refresh via prematch_alert)")
    args = ap.parse_args(argv)

    snap = args.odds_snapshot or pa.refresh_snapshot()
    raw = pa._http_json(pa.CALENDAR_URL)
    timeline = build_timeline_all(raw)
    fixtures = round_fixtures(raw, ROUND_STAGE[args.round])

    print(f"\nFATIGUE+VENUE KO OVERLAY  —  {args.round}  (isolated, read-only; KO shootout_total grid, no draws)")
    print("=" * 122)
    if not fixtures:
        print(f"No {args.round} fixtures with known pairings yet — the bracket slot is undetermined.")
        print("Re-run once the prior round has been played and the FIFA calendar resolves the teams.")
        return 0
    print("travel/rest now live in the MAIN tip (prematch_alert.ko_travel_context); this overlay adds only")
    print("the increment the core lacks: heat[open-meteo @ kickoff hour] × congestion. rest/mi shown for context.")
    print("-" * 122)
    print(f"{'Match (official)':28} {'Venue':12} {'rest h/a':>8} {'mi h/a':>10} {'cum h/a':>11} "
          f"{'C/WBGT':>8} {'fH/fA':>11} {'Main':>5} {'Fatig':>6}  Note")
    print("-" * 122)

    n_diff = n_flip = 0
    for date_utc, home, away, venue in fixtures:
        row = pa.compute_ko_tip(home, away, args.round, snap)
        main_tip = row["optimal_tip"]
        ppda_h = predictor.TEAM_PPDA.get(home, 11.0)
        ppda_a = predictor.TEAM_PPDA.get(away, 11.0)
        try:
            temp, hum = weather_tips.fetch_forecast(venue, date_utc)
        except Exception:
            temp, hum = None, None
        rest_h, mi_h, tz_h, dir_h, cum_h = ft.team_load(timeline, home, date_utc, venue)
        rest_a, mi_a, tz_a, dir_a, cum_a = ft.team_load(timeline, away, date_utc, venue)
        fac_h, ch = fatigue_engine.team_fatigue_factor(temp, hum, venue, ppda_h, rest_h, mi_h, tz_h, dir_h, cum_h)
        fac_a, ca = fatigue_engine.team_fatigue_factor(temp, hum, venue, ppda_a, rest_a, mi_a, tz_a, dir_a, cum_a)

        # Travel is now baked into the main tip's lambda_adj (prematch_alert.ko_travel_context),
        # so apply ONLY the increment the core lacks — heat[forecast] × congestion — to avoid
        # double-counting the travel penalty. (rest/mi columns below stay informational.)
        fac_h = ch["f_heat"] * ch["f_cong"]
        fac_a = ca["f_heat"] * ca["f_cong"]
        fat = fatigue_engine.fatigue_adjusted_ko_tip(
            row["lambda_a_adj"], row["lambda_b_adj"], row["config"], fac_h, fac_a, home, away)
        fat_tip = fat["tip"]
        marg = (fat["ev_by_tip"].get(fat_tip, 0.0) - fat["ev_by_tip"].get(main_tip, 0.0)) \
            if fat_tip != main_tip else 0.0
        real = fat_tip != main_tip and marg >= ft.MIN_EV_MARGIN
        flip = real and ft._winner(fat_tip) != ft._winner(main_tip)
        if real:
            n_diff += 1
        if flip:
            n_flip += 1
        note = []
        if ch["roof"] and ca["roof"]:
            note.append("roofed->WBGT21")
        if max(ch["travel_pen"], ca["travel_pen"]) < 0.01:
            note.append("travel~0")
        if flip:
            note.append(f"FLIP {main_tip}->{fat_tip} dEV{marg:+.3f}")
        elif real:
            note.append(f"shift {main_tip}->{fat_tip} dEV{marg:+.3f}")
        elif fat_tip != main_tip:
            note.append(f"~tie {main_tip}->{fat_tip} dEV{marg:+.3f}")
        wbgt = ch["wbgt"]
        tw = f"{temp:.0f}/{wbgt:.0f}" if (temp is not None and wbgt is not None) else "-"
        flag = " *" if real else "  "
        print(f"{f'{home} vs {away}'[:28]:28} {venue:12} {rest_h:>3.0f}/{rest_a:<3.0f} {mi_h:>4.0f}/{mi_a:<4.0f} "
              f"{cum_h:>5.0f}/{cum_a:<5.0f} {tw:>8} {fac_h:>5.2f}/{fac_a:<5.2f} {main_tip:>5} {fat_tip:>6}{flag} {'; '.join(note)}")

    print("-" * 122)
    print(f"{len(fixtures)} {args.round} fixtures; {n_diff} differ from main (>= {ft.MIN_EV_MARGIN} EV), {n_flip} WINNER flips")
    print("fH/fA = per-team capacity (1.0=fresh). Grid = kicktipp_ko_convention (shootout_total), identical to main tip.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
