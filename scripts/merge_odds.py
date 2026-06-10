#!/usr/bin/env python3
"""Bulk odds merger for gate G2 (S16) — "we do not type numbers, we merge matrices."

Fills data/wc{YEAR}_odds.csv from ANY raw odds CSV (Kaggle/GitHub download)
with the validation battery that pure automation lacks: a swapped column or a
year-mismatched dataset corrupts the gate exactly like a typo, so every
imported triple must pass integrity gates or it is QUARANTINED, not written.

    python3 scripts/merge_odds.py --year 2022 --raw data/raw_kaggle_2022.csv
    python3 scripts/merge_odds.py --year 2022 --raw raw.csv \
        --map home=HomeTeam away=AwayTeam h=B365H d=B365D a=B365A --dry-run

Pipeline per template row (never touches already-filled rows):
  1. NAME CANONICALIZATION — predictor.TEAM_NAME_MAPPING + historical aliases
     ("Korea Republic", "IR Iran", "United States", ...); exact canonical match
     first; guarded fuzzy fallback (ratio >= 0.87 AND clear margin) only as a
     last resort, every fuzzy hit logged for review.
  2. ORIENTATION — auto-detects a flipped fixture and swaps home/away odds.
  3. AGGREGATION — multiple raw rows for one fixture (several bookmakers)
     collapse to the per-leg MEDIAN.
  4. VALIDATION GATES (failures -> quarantine report, nothing written):
       * decimal odds: all three parse, each > 1.01;
       * book overround sum(1/o) in [0.95, 1.30] (catches American odds,
         percentages, comma decimals);
       * ELO CONCORDANCE vs the year's PRE-tournament table: if the Elo gap is
         >= 250 and the market's implied favourite is the OTHER side by >= 10pp,
         the row is quarantined — this is what catches the classic 1.35 -> 13.5
         column swap and wrong-year datasets.

Exit codes: 0 = merged (even partially); 1 = nothing merged (wrong --map?).
"""
import argparse
import csv
import difflib
import os
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import predictor  # noqa: E402

# Historical/odds-feed spellings that differ from the results-CSV names.
ALIASES = {
    "korea republic": "South Korea", "south korea": "South Korea", "korea": "South Korea",
    "ir iran": "Iran", "iran ir": "Iran",
    "united states": "USA", "united states of america": "USA", "us": "USA", "usa": "USA",
    "côte d'ivoire": "Ivory Coast", "cote d'ivoire": "Ivory Coast", "cote divoire": "Ivory Coast",
    "bosnia and herzegovina": "Bosnia", "bosnia-herzegovina": "Bosnia", "bosnia & herzegovina": "Bosnia",
    "korea dpr": "North Korea", "china pr": "China",
    "trinidad and tobago": "Trinidad", "serbia and montenegro": "Serbia",
    "czech republic": "Czechia",
}

# Column auto-detection candidates, in preference order (closing > pinnacle > b365 > avg).
TEAM_COL_CANDIDATES = {
    "home": ["home_team", "hometeam", "home team", "team1", "team_1", "home", "team_home", "homename"],
    "away": ["away_team", "awayteam", "away team", "team2", "team_2", "away", "team_away", "awayname"],
}
ODDS_TRIPLE_CANDIDATES = [
    ("psch", "pscd", "psca"),                     # Pinnacle closing
    ("avgch", "avgcd", "avgca"),                  # market average closing
    ("b365ch", "b365cd", "b365ca"),               # Bet365 closing
    ("psh", "psd", "psa"),                        # Pinnacle
    ("b365h", "b365d", "b365a"),                  # Bet365
    ("avgh", "avgd", "avga"),
    ("odds_home", "odds_draw", "odds_away"),
    ("home_win", "draw", "away_win"),
    ("odds_1", "odds_x", "odds_2"),
    ("1", "x", "2"),
    ("home_odds", "draw_odds", "away_odds"),
    ("oddsh", "oddsd", "oddsa"),
]

OVERROUND_WINDOW = (0.95, 1.30)
ELO_GAP_GATE = 250.0          # only police rows with a decisive Elo favourite
IMPLIED_MARGIN_GATE = 0.10    # ...where the market inverts it by >= 10pp
FUZZY_RATIO = 0.87
FUZZY_MARGIN = 0.05


def canon(name: str) -> str:
    low = str(name).strip().lower()
    if low in ALIASES:
        return ALIASES[low]
    return predictor.TEAM_NAME_MAPPING.get(low, str(name).strip())


def detect_columns(fieldnames):
    """Auto-detect (home, away, h, d, a) column names; None where ambiguous."""
    lower = {f.lower().strip(): f for f in fieldnames}
    home = next((lower[c] for c in TEAM_COL_CANDIDATES["home"] if c in lower), None)
    away = next((lower[c] for c in TEAM_COL_CANDIDATES["away"] if c in lower), None)
    triple = next((t for t in ODDS_TRIPLE_CANDIDATES if all(c in lower for c in t)), None)
    odds = tuple(lower[c] for c in triple) if triple else None
    return home, away, odds


def load_raw(path, col_home, col_away, col_h, col_d, col_a):
    """Raw rows -> {(canon_home, canon_away): [(oh, od, oa), ...]} (parse failures skipped)."""
    index = {}
    skipped = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                key = (canon(r[col_home]), canon(r[col_away]))
                triple = (float(r[col_h]), float(r[col_d]), float(r[col_a]))
            except (KeyError, ValueError, TypeError):
                skipped += 1
                continue
            index.setdefault(key, []).append(triple)
    return index, skipped


def fuzzy_lookup(ta, tb, index, log):
    """Guarded fuzzy fallback over the raw index keys. Returns (key, swapped) or None."""
    names = sorted({n for k in index for n in k})

    def best(name):
        scored = sorted(((difflib.SequenceMatcher(None, name.lower(), c.lower()).ratio(), c)
                         for c in names), reverse=True)
        if not scored or scored[0][0] < FUZZY_RATIO:
            return None
        if len(scored) > 1 and scored[0][0] - scored[1][0] < FUZZY_MARGIN:
            return None                      # ambiguous — refuse to guess
        return scored[0][1]

    fa, fb = best(ta), best(tb)
    if not fa or not fb or fa == fb:
        return None
    for key, swapped in (((fa, fb), False), ((fb, fa), True)):
        if key in index:
            log.append(f"fuzzy: '{ta}' vs '{tb}' -> raw '{key[0]}' vs '{key[1]}'"
                       + (" (flipped)" if swapped else ""))
            return key, swapped
    return None


def elo_win_prob(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def validate_triple(oh, od, oa, elo_a, elo_b, elo_check=True):
    """Returns None if OK, else the quarantine reason."""
    if min(oh, od, oa) <= 1.01:
        return f"odds <= 1.01 ({oh}/{od}/{oa}) — not decimal odds?"
    over = 1.0 / oh + 1.0 / od + 1.0 / oa
    if not (OVERROUND_WINDOW[0] <= over <= OVERROUND_WINDOW[1]):
        return (f"book sum {over:.3f} outside {OVERROUND_WINDOW} "
                f"({oh}/{od}/{oa}) — wrong format/columns?")
    if elo_check and elo_a is not None and elo_b is not None:
        gap = elo_a - elo_b
        if abs(gap) >= ELO_GAP_GATE:
            p_h_implied = (1.0 / oh) / over
            p_a_implied = (1.0 / oa) / over
            market_lean = p_h_implied - p_a_implied
            if gap > 0 and market_lean <= -IMPLIED_MARGIN_GATE:
                return (f"Elo says home by {gap:.0f} but market favours away by "
                        f"{-market_lean:.0%} ({oh}/{od}/{oa}) — swapped columns or wrong year?")
            if gap < 0 and market_lean >= IMPLIED_MARGIN_GATE:
                return (f"Elo says away by {-gap:.0f} but market favours home by "
                        f"{market_lean:.0%} ({oh}/{od}/{oa}) — swapped columns or wrong year?")
    return None


def merge(template_rows, raw_index, elo_table, bookmaker_label, source_label,
          elo_check=True):
    """Pure merge over already-loaded structures.
    Returns (rows, filled, quarantine[list of (match, reason)], fuzzy_log, unmatched)."""
    filled = 0
    quarantine, fuzzy_log, unmatched = [], [], []
    for row in template_rows:
        if str(row.get("odds_home", "")).strip():
            continue                                       # human/previous fill wins
        ta, tb = canon(row["team_a"]), canon(row["team_b"])

        hit, swapped = None, False
        if (ta, tb) in raw_index:
            hit = (ta, tb)
        elif (tb, ta) in raw_index:
            hit, swapped = (tb, ta), True
        else:
            f = fuzzy_lookup(ta, tb, raw_index, fuzzy_log)
            if f:
                hit, swapped = f
        if hit is None:
            unmatched.append(f"{ta} vs {tb} [{row.get('phase', '?')}]")
            continue

        triples = raw_index[hit]
        oh = round(statistics.median(t[0] for t in triples), 3)
        od = round(statistics.median(t[1] for t in triples), 3)
        oa = round(statistics.median(t[2] for t in triples), 3)
        if swapped:
            oh, oa = oa, oh                                # flipped fixture: swap 1 and 2

        elo_a = elo_table.get(ta, {}).get("elo") if elo_table else None
        elo_b = elo_table.get(tb, {}).get("elo") if elo_table else None
        reason = validate_triple(oh, od, oa, elo_a, elo_b, elo_check=elo_check)
        if reason:
            quarantine.append((f"{ta} vs {tb} [{row.get('phase', '?')}]"
                               + (" (flipped src)" if swapped else ""), reason))
            continue

        row["odds_home"], row["odds_draw"], row["odds_away"] = f"{oh}", f"{od}", f"{oa}"
        row["bookmaker"] = bookmaker_label + (f"(x{len(triples)} median)" if len(triples) > 1 else "")
        if "source_url" in row and source_label:
            row["source_url"] = source_label
        filled += 1
    return template_rows, filled, quarantine, fuzzy_log, unmatched


def validate_filled_template(template_path, elo_table):
    """Run the quarantine gates over the ALREADY-FILLED rows of a template —
    the safety net for manual data entry (2018/2014). Returns failure list."""
    failures = []
    n_filled = 0
    with open(template_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not str(row.get("odds_home", "")).strip():
                continue
            n_filled += 1
            label = f"{row['team_a']} vs {row['team_b']} [{row.get('phase', '?')}]"
            try:
                oh, od, oa = (float(row[k]) for k in ("odds_home", "odds_draw", "odds_away"))
            except (ValueError, KeyError):
                failures.append((label, "unparseable odds"))
                continue
            ta, tb = canon(row["team_a"]), canon(row["team_b"])
            reason = validate_triple(oh, od, oa,
                                     elo_table.get(ta, {}).get("elo"),
                                     elo_table.get(tb, {}).get("elo"))
            if reason:
                failures.append((label, reason))
    return n_filled, failures


def main():
    ap = argparse.ArgumentParser(description="Merge a raw odds CSV into a gate-G2 template")
    ap.add_argument("--year", type=int, required=True, choices=[2014, 2018, 2022])
    ap.add_argument("--raw", type=str, default=None, help="Downloaded raw odds CSV")
    ap.add_argument("--map", nargs="+", default=None, metavar="k=COL",
                    help="Explicit columns: home=... away=... h=... d=... a=...")
    ap.add_argument("--bookmaker-label", type=str, default="bulk_merge")
    ap.add_argument("--source-label", type=str, default="", help="Provenance URL/name for source_url")
    ap.add_argument("--no-elo-check", action="store_true",
                    help="Disable the Elo-concordance gate (NOT recommended)")
    ap.add_argument("--dry-run", action="store_true", help="Report everything, write nothing")
    ap.add_argument("--validate-only", action="store_true",
                    help="No merge: run the quarantine gates over the template's "
                         "already-filled rows (manual-entry fat-finger net)")
    args = ap.parse_args()

    template_path = os.path.join(REPO, "data", f"wc{args.year}_odds.csv")
    if not os.path.exists(template_path):
        sys.exit(f"❌ {template_path} missing — run scripts/make_odds_templates.py first")

    if args.validate_only:
        mod = __import__(f"backtest_wm{args.year}")
        elo_table = getattr(mod, f"PRE_WM{args.year}_ELO")
        n_filled, failures = validate_filled_template(template_path, elo_table)
        if failures:
            print(f"❌ {len(failures)}/{n_filled} filled row(s) FAIL the integrity gates:")
            for label, reason in failures:
                print(f"   {label}: {reason}")
            sys.exit(1)
        print(f"✅ all {n_filled} filled row(s) pass the integrity gates "
              f"(odds sanity, overround window, Elo concordance).")
        return

    if not args.raw:
        sys.exit("❌ --raw <csv> required (or use --validate-only)")

    with open(args.raw, newline="", encoding="utf-8-sig") as f:
        fieldnames = csv.DictReader(f).fieldnames or []

    if args.map:
        m = dict(kv.split("=", 1) for kv in args.map)
        col_home, col_away = m["home"], m["away"]
        odds_cols = (m["h"], m["d"], m["a"])
    else:
        col_home, col_away, odds_cols = detect_columns(fieldnames)
        if not (col_home and col_away and odds_cols):
            print("❌ Could not auto-detect columns. Headers found:")
            print("   " + ", ".join(fieldnames))
            print("   Re-run with: --map home=<col> away=<col> h=<col> d=<col> a=<col>")
            sys.exit(1)
        print(f"🔎 Auto-detected columns: home={col_home} away={col_away} "
              f"1X2=({odds_cols[0]}, {odds_cols[1]}, {odds_cols[2]})")

    raw_index, parse_skipped = load_raw(args.raw, col_home, col_away, *odds_cols)
    print(f"📥 {args.raw}: {sum(len(v) for v in raw_index.values())} odds rows over "
          f"{len(raw_index)} fixtures ({parse_skipped} unparseable rows skipped)")

    # Year-appropriate pre-tournament Elo for the concordance gate
    elo_table = {}
    if not args.no_elo_check:
        mod = __import__(f"backtest_wm{args.year}")
        elo_table = getattr(mod, f"PRE_WM{args.year}_ELO")

    with open(template_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        tmpl_fields = reader.fieldnames
        rows = list(reader)

    rows, filled, quarantine, fuzzy_log, unmatched = merge(
        rows, raw_index, elo_table, args.bookmaker_label, args.source_label,
        elo_check=not args.no_elo_check)

    for line in fuzzy_log:
        print(f"🔁 {line}")
    if quarantine:
        qpath = os.path.join(REPO, "data", f"merge_quarantine_{args.year}.txt")
        print(f"\n🚧 QUARANTINED {len(quarantine)} fixture(s) — review by hand "
              f"({'' if args.dry_run else 'written to ' + os.path.relpath(qpath, REPO)}):")
        qlines = [f"{m}: {r}" for m, r in quarantine]
        for line in qlines:
            print(f"   {line}")
        if not args.dry_run:
            with open(qpath, "w", encoding="utf-8") as f:
                f.write("\n".join(qlines) + "\n")
    if unmatched:
        print(f"\nℹ {len(unmatched)} template fixture(s) had no raw match "
              f"(fill manually or use another source): {unmatched[:5]}"
              + (" …" if len(unmatched) > 5 else ""))

    if args.dry_run:
        print(f"\n🧪 DRY RUN — would fill {filled} fixture(s); template untouched.")
        return
    if filled == 0:
        print("\n❌ Nothing merged — wrong --map, wrong year, or names not resolving.")
        sys.exit(1)

    with open(template_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=tmpl_fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n✅ Filled {filled} fixture(s) in {os.path.relpath(template_path, REPO)}.")
    print(f"   Next: python3 backtest_real_market.py --years {args.year}")


if __name__ == "__main__":
    main()
