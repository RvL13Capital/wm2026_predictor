#!/usr/bin/env python3
"""Read-only runner: main tip ALONGSIDE the weather/heat-adjusted tip.

Presentation layer for the isolated `weather_engine`. It:
  1. pulls the FIFA calendar for upcoming First-Stage fixtures (official home/away
     order, venue, kickoff in UTC),
  2. reuses `matchday_tips.run_matchday` for the EXACT same per-match lambda_adj /
     config the main sheet uses,
  3. fetches a per-venue, per-kickoff forecast from open-meteo (temperature +
     relative humidity at the kickoff hour, UTC),
  4. asks the weather engine for the heat-adjusted tip and prints both columns.

Data flows one way only (main -> weather); nothing here writes back into the main
tip path. It calls run_matchday directly (NOT matchday_tips.main()), so the
recommendation-change WhatsApp hook is never invoked.

Usage:
    python3 weather_tips.py --md 2 --odds-snapshot data/polymarket_match_odds.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import prematch_alert as pa            # _http_json, engine_name, CALENDAR_URL

import predictor
import matchday_tips
import weather_engine

ROOT = os.path.dirname(os.path.abspath(__file__))

# A heat-flipped tip whose EV beats the main tip by less than this (Kicktipp points)
# is a coin-flip tie-break, not a heat signal — shown but not starred.
MIN_EV_MARGIN = 0.02

# FIFA generic stadium names -> STADIUM_DATA keys for the venues that don't reduce
# to "<City> Stadium" by stripping the suffix.
VENUE_ALIAS = {
    "BC Place Vancouver": "Vancouver",
    "New York/New Jersey": "New Jersey",
    "San Francisco Bay Area": "San Francisco",
}


def venue_key(stadium_name: str) -> str:
    base = (stadium_name or "").replace(" Stadium", "").strip()
    return VENUE_ALIAS.get(base, base)


def _desc(team):
    try:
        return team["TeamName"][0]["Description"]
    except Exception:
        return None


def upcoming_fixtures():
    """[(date_utc, local_date, home_engine, away_engine, venue_key)] for unplayed
    First-Stage fixtures, sorted by kickoff."""
    raw = pa._http_json(pa.CALENDAR_URL)
    try:
        live = json.load(open(os.path.join(ROOT, "data", "live_state.json")))
        played = {frozenset(k.split(" vs ")) for k in live}
    except Exception:
        played = set()
    out = []
    for m in raw.get("Results", []):
        if m.get("MatchStatus") != 1:
            continue
        stage = ""
        if m.get("StageName"):
            stage = m["StageName"][0].get("Description", "")
        if "First Stage" not in stage:
            continue
        hn, an = pa.engine_name(_desc(m.get("Home"))), pa.engine_name(_desc(m.get("Away")))
        if not hn or not an or frozenset((hn, an)) in played:
            continue
        sd = m.get("Stadium") or {}
        vname = (sd.get("Name") or [{}])[0].get("Description", "")
        out.append((m.get("Date"), m.get("LocalDate"), hn, an, venue_key(vname)))
    out.sort()
    return out


_FC_CACHE = {}


def fetch_forecast(venue: str, kickoff_utc_iso: str):
    """(temp_c, humidity_pct) at the kickoff hour from open-meteo, or (None, None)."""
    sd = predictor.STADIUM_DATA.get(venue)
    if not sd or not kickoff_utc_iso:
        return None, None
    day = kickoff_utc_iso[:10]
    ckey = (venue, day)
    if ckey not in _FC_CACHE:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={sd['lat']}&longitude={sd['lon']}"
               "&hourly=temperature_2m,relative_humidity_2m"
               f"&start_date={day}&end_date={day}&timezone=UTC")
        try:
            _FC_CACHE[ckey] = pa._http_json(url)
        except Exception as e:
            _FC_CACHE[ckey] = None
            print(f"  [weather] fetch failed for {venue} {day}: {e}", file=sys.stderr)
    data = _FC_CACHE[ckey]
    if not data:
        return None, None
    h = data.get("hourly", {})
    times, temps, hums = h.get("time", []), h.get("temperature_2m", []), h.get("relative_humidity_2m", [])
    target = kickoff_utc_iso[:13]          # "YYYY-MM-DDTHH"
    for i, t in enumerate(times):
        if t[:13] == target:
            return temps[i], hums[i]
    return None, None


def main():
    ap = argparse.ArgumentParser(description="Main tip vs weather/heat-adjusted tip (isolated engine)")
    ap.add_argument("--md", type=int, required=True)
    ap.add_argument("--odds-snapshot", default="data/polymarket_match_odds.json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    snap = args.odds_snapshot if os.path.isabs(args.odds_snapshot) else os.path.join(ROOT, args.odds_snapshot)
    market_probs, market_extras = matchday_tips.load_market_snapshot(snap)

    # main-model lambdas/config, keyed by the unordered team pair
    results = matchday_tips.run_matchday(args.md, 0, args.seed, market_probs, market_extras)
    by_pair = {frozenset((r["team_a"], r["team_b"])): r for r in results}

    fixtures = upcoming_fixtures()

    print(f"WEATHER/HEAT ENGINE  —  Matchday {args.md}  (isolated, read-only; main tip vs heat-adjusted tip)")
    print("=" * 104)
    print(f"{'Match (official)':30} {'Venue':12} {'Roof':4} {'°C/RH':>7} {'WBGT':>5} "
          f"{'fH/fA':>9}  {'Main':>5} {'Wx':>5}  Note")
    print("-" * 104)

    n_diff = 0
    n_hot = 0
    n_shown = 0
    for date_utc, local_date, home, away, venue in fixtures:
        r = by_pair.get(frozenset((home, away)))
        if not r:
            continue  # not in this matchday's run_matchday (e.g. an upcoming MD3 fixture)
        n_shown += 1
        # orient main-model lambdas/tip to the official home/away
        if r["team_a"] == home:
            lam_h, lam_a = r["lambda_adj_a"], r["lambda_adj_b"]
            mt = r["optimal_tip"]
            main_tip = f"{mt[0]}:{mt[1]}"
        else:
            lam_h, lam_a = r["lambda_adj_b"], r["lambda_adj_a"]
            mt = r["optimal_tip"]
            main_tip = f"{mt[1]}:{mt[0]}"

        ppda_h = predictor.TEAM_PPDA.get(home, 11.0)
        ppda_a = predictor.TEAM_PPDA.get(away, 11.0)

        temp, hum = fetch_forecast(venue, date_utc)
        wx = weather_engine.weather_adjusted_tip(lam_h, lam_a, r["config"], temp, hum,
                                                 venue, ppda_h, ppda_a)
        label = f"{home} vs {away}"[:30]
        loc = (local_date or "")[11:16]
        if wx is None:
            print(f"{label:30} {venue:12} {'-':4} {'—':>7} {'—':>5} {'—':>9}  {main_tip:>5} {'—':>5}  no forecast")
            continue
        hot = wx["wbgt"] > 20.0 and not wx["roof"]
        if hot:
            n_hot += 1
        # Gate a DIFF on the EV margin under the heat-adjusted grid: a flip that beats
        # the main tip by < MIN_EV_MARGIN is a coin-flip tie-break, not a heat signal.
        marg = (wx["ev_by_tip"].get(wx["tip"], 0.0) - wx["ev_by_tip"].get(main_tip, 0.0)) \
            if wx["tip"] != main_tip else 0.0
        real = wx["tip"] != main_tip and marg >= MIN_EV_MARGIN
        if real:
            n_diff += 1
        roof_s = "clsd" if wx["roof"] else "open"
        if wx["roof"]:
            note = "roofed → heat neutralised"
        elif not hot:
            note = f"mild (WBGT {wx['wbgt']:.0f}≤20) → no effect"
        elif real:
            note = f"HEAT: fH={wx['f_a']:.2f} fA={wx['f_b']:.2f}  → DIFF {main_tip}→{wx['tip']} Δev{marg:+.3f}"
        elif wx["tip"] != main_tip:
            note = f"HEAT: fH={wx['f_a']:.2f} fA={wx['f_b']:.2f}  → ~tie {main_tip}→{wx['tip']} Δev{marg:+.3f} (coin-flip)"
        else:
            note = f"HEAT: fH={wx['f_a']:.2f} fA={wx['f_b']:.2f}  (tip holds)"
        flag = " *" if real else "  "
        print(f"{label:30} {venue:12} {roof_s:4} {temp:>4.0f}/{hum:<2.0f} {wx['wbgt']:>5.1f} "
              f"{wx['f_a']:>4.2f}/{wx['f_b']:<4.2f} {main_tip:>5} {wx['tip']:>4}{flag} {note}")

    print("-" * 104)
    print(f"{n_shown} fixtures shown (MD{args.md}); {n_hot} with active heat (open-air, WBGT>20); "
          f"{n_diff} where the heat-adjusted tip DIFFERS from the main tip")
    print("Note: FATIGUE model — heat-adjusted tip = main lambdas × calculate_thermal_factor(real forecast),")
    print("      i.e. heat -> FEWER goals (the operator's hypothesis). This is the OPPOSITE direction to the")
    print("      core engine's own thermal term (which raises goals via defensive degradation) and is NOT a")
    print("      reconstruction of it. Read-only, feeds back into nothing. Roof from STADIUM_DATA (retract.→closed).")


if __name__ == "__main__":
    main()
