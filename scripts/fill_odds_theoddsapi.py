#!/usr/bin/env python3
"""Fill the 2022 gate-G2 template from The Odds API historical snapshots (S16).

The only clean, ToS-compliant automated source of WC2022 closing odds:
The Odds API keeps odds snapshots from June 2020 onward (paid "historical"
endpoint; WC2018/2014 are NOT covered — this script refuses those years).

    export ODDS_API_KEY=...   # plan with historical access
    python3 scripts/fill_odds_theoddsapi.py --year 2022 --estimate      # cost preview, no calls
    python3 scripts/fill_odds_theoddsapi.py --year 2022 --yes           # fetch + fill
    python3 scripts/fill_odds_theoddsapi.py --year 2022 --from-cache data/oddsapi_2022_snapshots.json

How it works:
  1. Sweeps snapshot timestamps across the tournament window (default every
     12h, ~60 calls ≈ 600 credits at 10/region-market). Every fetched snapshot
     is CACHED to data/oddsapi_2022_snapshots.json — re-runs are free and the
     cache is the provenance record.
  2. For each event, the LAST snapshot strictly before its commence_time is
     the closing book; the per-leg MEDIAN across bookmakers is used.
  3. Fills the template through scripts/merge_odds.merge() — i.e. the same
     canonicalization, orientation and QUARANTINE gates (odds sanity,
     overround window, Elo concordance) as any bulk import. Never guesses,
     never overwrites filled rows.

NOTE: this container's egress allowlist blocks api.the-odds-api.com — run the
fetch on your own machine; --from-cache / tests work anywhere.
"""
import argparse
import importlib.util
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_spec = importlib.util.spec_from_file_location(
    "merge_odds", os.path.join(REPO, "scripts", "merge_odds.py"))
merge_odds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(merge_odds)

WINDOWS = {2022: ("2022-11-19T12:00:00Z", "2022-12-18T20:00:00Z")}


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def closing_index_from_snapshots(snapshots: list) -> dict:
    """Pure: snapshots -> {(canon_home, canon_away): [(oh, od, oa)]}.

    A snapshot is the API's historical payload: {"timestamp": iso, "data":
    [events]}. For each event the last snapshot strictly BEFORE commence_time
    wins (closing); its odds triple is the per-leg median across bookmakers.
    Events never seen before kickoff are omitted (no guessing).
    """
    best = {}   # event_key -> (snap_ts, [triples])
    for snap in snapshots:
        snap_ts = _parse_iso(snap["timestamp"])
        for ev in snap.get("data", []):
            commence = _parse_iso(ev["commence_time"])
            if snap_ts >= commence:
                continue
            home, away = ev.get("home_team", ""), ev.get("away_team", "")
            triples = []
            for bk in ev.get("bookmakers", []):
                for mkt in bk.get("markets", []):
                    if mkt.get("key") != "h2h":
                        continue
                    prices = {o.get("name"): o.get("price") for o in mkt.get("outcomes", [])}
                    oh, od, oa = prices.get(home), prices.get("Draw"), prices.get(away)
                    if oh and od and oa:
                        triples.append((float(oh), float(od), float(oa)))
            if not triples:
                continue
            key = (home, away, ev["commence_time"])
            prev = best.get(key)
            if prev is None or snap_ts > prev[0]:
                best[key] = (snap_ts, triples)

    index = {}
    for (home, away, _ct), (_ts, triples) in best.items():
        oh = statistics.median(t[0] for t in triples)
        od = statistics.median(t[1] for t in triples)
        oa = statistics.median(t[2] for t in triples)
        index.setdefault((merge_odds.canon(home), merge_odds.canon(away)), []).append(
            (round(oh, 3), round(od, 3), round(oa, 3)))
    return index


def sweep_timestamps(year: int, sweep_hours: float) -> list:
    start, end = (_parse_iso(t) for t in WINDOWS[year])
    out, t = [], start
    while t <= end:
        out.append(t.strftime("%Y-%m-%dT%H:%M:%SZ"))
        t += timedelta(hours=sweep_hours)
    return out


def main():
    ap = argparse.ArgumentParser(description="Fill G2 odds template from The Odds API history")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--api-key", default=os.environ.get("ODDS_API_KEY"))
    ap.add_argument("--sweep-hours", type=float, default=12.0)
    ap.add_argument("--regions", default="eu")
    ap.add_argument("--cache", default=None, help="Snapshot cache JSON (default data/oddsapi_<year>_snapshots.json)")
    ap.add_argument("--from-cache", default=None, help="Skip fetching; build from this cache file")
    ap.add_argument("--estimate", action="store_true", help="Print request/credit estimate and exit")
    ap.add_argument("--yes", action="store_true", help="Confirm spending API credits")
    ap.add_argument("--dry-run", action="store_true", help="Merge preview; write nothing")
    args = ap.parse_args()

    if args.year not in WINDOWS:
        sys.exit(f"❌ The Odds API history starts June 2020 — {args.year} is not covered. "
                 f"For 2018/2014 use manual entry + 'merge_odds.py --validate-only' "
                 f"(data/ODDS_DATA_README.md).")
    cache_path = args.cache or os.path.join(REPO, "data", f"oddsapi_{args.year}_snapshots.json")

    timestamps = sweep_timestamps(args.year, args.sweep_hours)
    est_credits = len(timestamps) * 10 * len(args.regions.split(","))
    if args.estimate:
        print(f"📋 {len(timestamps)} snapshot calls (every {args.sweep_hours}h, "
              f"{WINDOWS[args.year][0]} → {WINDOWS[args.year][1]}) ≈ {est_credits} credits "
              f"(historical = ~10/region-market). Cache: {cache_path}")
        return

    if args.from_cache:
        with open(args.from_cache, "r", encoding="utf-8") as f:
            snapshots = json.load(f)
        print(f"📥 {len(snapshots)} snapshots loaded from {args.from_cache} (no API calls)")
    else:
        if not args.api_key:
            sys.exit("❌ No API key: set ODDS_API_KEY or pass --api-key "
                     "(historical endpoint requires a paid plan).")
        if not args.yes:
            sys.exit(f"⛔ This will spend ≈{est_credits} credits over {len(timestamps)} calls. "
                     f"Re-run with --yes to confirm (or --estimate to preview).")
        from odds_client import OddsAPIClient
        client = OddsAPIClient(args.api_key)
        snapshots = []
        # Resume support: start from an existing cache
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                snapshots = json.load(f)
            have = {s["timestamp"] for s in snapshots}
            timestamps = [t for t in timestamps
                          if _parse_iso(t).strftime("%Y-%m-%dT%H:%M:%SZ") not in have]
            print(f"📥 resuming: {len(snapshots)} snapshots cached, {len(timestamps)} to fetch")
        for i, ts in enumerate(timestamps, 1):
            try:
                snap = client.get_historical_odds(ts, regions=args.regions)
            except RuntimeError as e:
                print(f"⚠ {ts}: {e}", file=sys.stderr)
                if "401" in str(e) or "422" in str(e):
                    sys.exit("❌ Historical endpoint refused — does the plan include "
                             "historical access?")
                continue
            snapshots.append({"timestamp": snap.get("timestamp", ts),
                              "data": snap.get("data", [])})
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(snapshots, f)     # checkpoint after every call
            rem = client.remaining_requests
            print(f"  [{i}/{len(timestamps)}] {ts}: {len(snap.get('data', []))} events"
                  + (f" · credits left {rem}" if rem is not None else ""))
        print(f"💾 cache: {cache_path}")

    raw_index = closing_index_from_snapshots(snapshots)
    print(f"🧮 closing books reconstructed for {len(raw_index)} fixtures")

    template_path = os.path.join(REPO, "data", f"wc{args.year}_odds.csv")
    import csv
    with open(template_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)

    mod = __import__(f"backtest_wm{args.year}")
    elo_table = getattr(mod, f"PRE_WM{args.year}_ELO")
    rows, filled, quarantine, fuzzy_log, unmatched = merge_odds.merge(
        rows, raw_index, elo_table, "theoddsapi_median_close",
        "the-odds-api.com historical")

    for line in fuzzy_log:
        print(f"🔁 {line}")
    for m, reason in quarantine:
        print(f"🚧 QUARANTINED {m}: {reason}")
    if unmatched:
        print(f"ℹ {len(unmatched)} fixtures not in snapshots (fill manually): {unmatched[:5]}"
              + (" …" if len(unmatched) > 5 else ""))
    if args.dry_run:
        print(f"🧪 DRY RUN — would fill {filled} fixtures.")
        return
    if filled == 0:
        sys.exit("❌ nothing filled — empty cache or no pre-kickoff snapshots?")
    with open(template_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"✅ filled {filled} fixtures in {os.path.relpath(template_path, REPO)} — "
          f"next: python3 backtest_real_market.py --years {args.year}")


if __name__ == "__main__":
    main()
