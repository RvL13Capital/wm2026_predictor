#!/usr/bin/env python3
"""Read-only runner: main tip vs DIFFERENTIAL fatigue tip (heat + travel + congestion).

Reconstructs each team's match timeline (venue + date) from the FIFA calendar, derives
per-team rest / travel / timezone / cumulative-miles, fetches the per-venue kickoff
forecast (open-meteo, reusing weather_tips), asks fatigue_engine for each team's
capacity factor, and prints the fatigue-adjusted tip next to the main tip and a
heat-only reference. The asymmetric factors can flip a tight game.

Data flows one way (main -> fatigue); calls run_matchday directly (no WhatsApp hook).

Usage:
    python3 fatigue_tips.py --md 2 --odds-snapshot data/polymarket_match_odds.json
"""
import argparse
import datetime
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import prematch_alert as pa

import predictor
import stadium_data
import matchday_tips
import fatigue_engine
import weather_tips                       # reuse venue_key + fetch_forecast (+ open-meteo cache)

ROOT = os.path.dirname(os.path.abspath(__file__))

# A fatigue-flipped tip whose EV beats the main tip by less than this (Kicktipp points)
# is a coin-flip tie-break, not a fatigue signal — shown but not starred.
MIN_EV_MARGIN = 0.02


def _desc(team):
    try:
        return team["TeamName"][0]["Description"]
    except Exception:
        return None


def _date(iso):
    return datetime.date.fromisoformat((iso or "")[:10])


def build_timeline(raw):
    """{team: sorted [(date_iso, venue_key)]} over all First-Stage matches."""
    tl = defaultdict(list)
    for m in raw.get("Results", []):
        stage = ""
        if m.get("StageName"):
            stage = m["StageName"][0].get("Description", "")
        if "First Stage" not in stage:
            continue
        hn, an = pa.engine_name(_desc(m.get("Home"))), pa.engine_name(_desc(m.get("Away")))
        sd = m.get("Stadium") or {}
        venue = weather_tips.venue_key((sd.get("Name") or [{}])[0].get("Description", ""))
        for t in (hn, an):
            if t:
                tl[t].append((m.get("Date"), venue))
    for t in tl:
        tl[t].sort()
    return tl


def leg(prev_v, this_v):
    """(miles, tz_crossed, direction) for a hop prev_v -> this_v, or (0,0,'None')."""
    if not prev_v or not this_v or prev_v not in predictor.STADIUM_DATA or this_v not in predictor.STADIUM_DATA:
        return 0.0, 0, "None"
    miles = stadium_data.haversine_distance(prev_v, this_v)
    a, b = predictor.STADIUM_DATA[prev_v], predictor.STADIUM_DATA[this_v]
    tz = abs(int(a.get("tz_offset", 0)) - int(b.get("tz_offset", 0)))
    direction = "east" if b["lon"] > a["lon"] else ("west" if b["lon"] < a["lon"] else "None")
    return miles, tz, direction


def team_load(timeline, team, this_date_iso, this_venue):
    """rest_days, travel_miles, tz_crossed, direction, cum_miles for `team` arriving at
    this fixture. Previous = latest match strictly before this date."""
    hist = [(d, v) for (d, v) in timeline.get(team, []) if _date(d) < _date(this_date_iso)]
    if not hist:
        return 5.0, 0.0, 0, "None", 0.0           # no prior -> treat as rested arrival
    prev_d, prev_v = hist[-1]
    rest = (_date(this_date_iso) - _date(prev_d)).days
    miles, tz, direction = leg(prev_v, this_venue)
    # cumulative miles already flown: sum of legs between consecutive prior matches
    cum = 0.0
    for i in range(1, len(hist)):
        cum += leg(hist[i - 1][1], hist[i][1])[0]
    return float(rest), float(miles), int(tz), direction, float(cum)


def main():
    ap = argparse.ArgumentParser(description="Main tip vs differential fatigue tip (isolated)")
    ap.add_argument("--md", type=int, required=True)
    ap.add_argument("--odds-snapshot", default="data/polymarket_match_odds.json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    snap = args.odds_snapshot if os.path.isabs(args.odds_snapshot) else os.path.join(ROOT, args.odds_snapshot)
    market_probs, market_extras = matchday_tips.load_market_snapshot(snap)
    results = matchday_tips.run_matchday(args.md, 0, args.seed, market_probs, market_extras)
    by_pair = {frozenset((r["team_a"], r["team_b"])): r for r in results}

    raw = pa._http_json(pa.CALENDAR_URL)
    timeline = build_timeline(raw)
    fixtures = weather_tips.upcoming_fixtures()

    print(f"FATIGUE ENGINE  —  Matchday {args.md}  (isolated, read-only; heat + travel + congestion, differential)")
    print("=" * 118)
    print(f"{'Match (official)':30} {'Venue':12} {'rest h/a':>8} {'mi h/a':>9} "
          f"{'fH/fA':>11} {'Main':>5} {'Heat':>5} {'Fatig':>6}  Note")
    print("-" * 118)

    n_shown = n_diff = n_flip = 0
    for date_utc, local_date, home, away, venue in fixtures:
        r = by_pair.get(frozenset((home, away)))
        if not r:
            continue
        n_shown += 1
        if r["team_a"] == home:
            lam_h, lam_a = r["lambda_adj_a"], r["lambda_adj_b"]
            mt = r["optimal_tip"]; main_tip = f"{mt[0]}:{mt[1]}"
        else:
            lam_h, lam_a = r["lambda_adj_b"], r["lambda_adj_a"]
            mt = r["optimal_tip"]; main_tip = f"{mt[1]}:{mt[0]}"

        ppda_h = predictor.TEAM_PPDA.get(home, 11.0)
        ppda_a = predictor.TEAM_PPDA.get(away, 11.0)
        temp, hum = weather_tips.fetch_forecast(venue, date_utc)

        rest_h, mi_h, tz_h, dir_h, cum_h = team_load(timeline, home, date_utc, venue)
        rest_a, mi_a, tz_a, dir_a, cum_a = team_load(timeline, away, date_utc, venue)
        fac_h, ch = fatigue_engine.team_fatigue_factor(temp, hum, venue, ppda_h, rest_h, mi_h, tz_h, dir_h, cum_h)
        fac_a, ca = fatigue_engine.team_fatigue_factor(temp, hum, venue, ppda_a, rest_a, mi_a, tz_a, dir_a, cum_a)

        fat = fatigue_engine.fatigue_adjusted_tip(lam_h, lam_a, r["config"], fac_h, fac_a)
        # heat-only reference (travel/congestion factors forced to 1.0)
        heat = fatigue_engine.fatigue_adjusted_tip(lam_h, lam_a, r["config"], ch["f_heat"], ca["f_heat"])

        label = f"{home} vs {away}"[:30]
        # Gate on the EV margin: a flip beating the main tip by < MIN_EV_MARGIN under the
        # fatigue-adjusted grid is a coin-flip tie-break, not a fatigue signal.
        marg = (fat["ev_by_tip"].get(fat["tip"], 0.0) - fat["ev_by_tip"].get(main_tip, 0.0)) \
            if fat["tip"] != main_tip else 0.0
        real = fat["tip"] != main_tip and marg >= MIN_EV_MARGIN
        flip = real and _winner(fat["tip"]) != _winner(main_tip)
        if real:
            n_diff += 1
        if flip:
            n_flip += 1
        note = []
        if ch["roof"] and ca["roof"]:
            note.append("roofed")
        if max(ch["travel_pen"], ca["travel_pen"]) < 0.01:
            note.append("travel~0 (rested)")
        if flip:
            note.append(f"⚑ WINNER FLIP {main_tip}->{fat['tip']} Δev{marg:+.3f}")
        elif real:
            note.append(f"shift {main_tip}->{fat['tip']} Δev{marg:+.3f}")
        elif fat["tip"] != main_tip:
            note.append(f"~tie {main_tip}->{fat['tip']} Δev{marg:+.3f} (coin-flip)")
        flag = " *" if real else "  "
        print(f"{label:30} {venue:12} {rest_h:>3.0f}/{rest_a:<3.0f} {mi_h:>4.0f}/{mi_a:<4.0f} "
              f"{fac_h:>5.2f}/{fac_a:<5.2f} {main_tip:>5} {heat['tip']:>5} {fat['tip']:>5}{flag} {'; '.join(note)}")

    print("-" * 118)
    print(f"{n_shown} fixtures shown (MD{args.md}); {n_diff} differ from main, {n_flip} WINNER flips")
    print("Note: FATIGUE = main lambdas × per-team (heat × travel × congestion); ASYMMETRIC, so it can flip a")
    print("      tight game. Group stage: ~6-day rest damps travel to ~0, so fatigue ≈ heat here; travel/congestion")
    print("      bite in the knockouts (3-4 day rest, longer hops). Read-only; feeds back into nothing.")


def _winner(tip):
    a, b = (int(x) for x in tip.split(":"))
    return "H" if a > b else ("A" if a < b else "D")


if __name__ == "__main__":
    main()
