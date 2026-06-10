#!/usr/bin/env python3
"""Generate fixture-prefilled odds templates for gate G2 (S16).

Writes data/wc{2014,2018,2022}_odds.csv with team_a/team_b/phase copied from
the results CSVs (canonical names, exact join orientation) and BLANK odds
columns — so supplying the G2 data reduces to typing three numbers per row.
See data/ODDS_DATA_README.md for sources and definitions.

Refuses to overwrite a file that already contains any completed odds row
(your manual work) unless --force is given.
"""
import argparse
import csv
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEARS = (2014, 2018, 2022)
FIELDS = ["team_a", "team_b", "phase", "odds_home", "odds_draw", "odds_away",
          "bookmaker", "source_url"]


def has_filled_rows(path: str) -> bool:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                vals = (r.get("odds_home"), r.get("odds_draw"), r.get("odds_away"))
                if all(v is not None and str(v).strip() != "" for v in vals):
                    return True
    except OSError:
        pass
    return False


def main():
    ap = argparse.ArgumentParser(description="Write blank-odds fixture templates")
    ap.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    ap.add_argument("--force", action="store_true",
                    help="Overwrite even if a target contains completed odds rows")
    args = ap.parse_args()

    for year in args.years:
        src = os.path.join(REPO, "data", f"wc{year}_results.csv")
        dst = os.path.join(REPO, "data", f"wc{year}_odds.csv")
        if not os.path.exists(src):
            print(f"⚠ {src} missing — skipped", file=sys.stderr)
            continue
        if os.path.exists(dst) and has_filled_rows(dst) and not args.force:
            print(f"⏭  {dst} already has completed odds rows — NOT overwriting "
                  f"(use --force to discard them).")
            continue
        n = 0
        with open(src, newline="", encoding="utf-8") as f_in, \
             open(dst, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=FIELDS)
            writer.writeheader()
            for r in csv.DictReader(f_in):
                writer.writerow({
                    "team_a": r["team_a"].strip(),
                    "team_b": r["team_b"].strip(),
                    "phase": (r.get("phase") or "GROUP").strip(),
                    "odds_home": "", "odds_draw": "", "odds_away": "",
                    "bookmaker": "", "source_url": "",
                })
                n += 1
        print(f"✅ {dst}: {n} fixture rows, odds blank — fill and run "
              f"backtest_real_market.py --years {year}")


if __name__ == "__main__":
    main()
