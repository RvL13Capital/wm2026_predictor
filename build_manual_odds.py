#!/usr/bin/env python3
"""
Manual / fallback odds ingestion — for when Polymarket has zero or thin volume.

Reads a CSV of 1X2 DECIMAL odds (team_a,team_b,odds_home,odds_draw,odds_away) — e.g. a sharp
book's 3-way closing line (Pinnacle) — and emits the same JSON schema matchday_tips consumes,
so a hand-entered line blends at the full 80% exactly like a live market. Manual lines carry
NO "liquidity" key, so the router treats them as TRUSTED (always blends, never auto-skipped).

Usage:
  python3 build_manual_odds.py manual_odds.csv > data/match_odds.json
  python3 build_manual_odds.py manual_odds.csv data/polymarket_match_odds.json > data/match_odds.json
      (2nd arg = merge: each manual row OVERRIDES any Polymarket line for the same pair, either
       orientation — so you fetch Polymarket, then override only the thin/missing matches by hand.)

NOTE — 3-way 1X2 only. Asian Handicap / Over-Under can't be turned into a clean 1X2 without the
bivariate totals solver (parked — no historical O/U data to validate it). Use a book's 3-way line.
"""
import csv, json, sys


def _pair(a, b):
    """Orientation-independent key for a fixture."""
    return tuple(sorted([a.strip().lower(), b.strip().lower()]))


def load_manual(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ta = (r.get("team_a") or "").strip()
            tb = (r.get("team_b") or "").strip()
            if not ta or not tb or ta.startswith("#"):          # skip blanks / comment rows
                continue
            try:
                oh, od, oa = float(r["odds_home"]), float(r["odds_draw"]), float(r["odds_away"])
            except (KeyError, ValueError, TypeError):
                print(f"[manual] skip unparseable row: {dict(r)}", file=sys.stderr); continue
            if not (oh > 1.0 and od > 1.0 and oa > 1.0):
                print(f"[manual] skip non-decimal odds for {ta} v {tb}: {oh}/{od}/{oa}", file=sys.stderr); continue
            rows.append((ta, tb, round(oh, 3), round(od, 3), round(oa, 3)))
    return rows


def main():
    if len(sys.argv) < 2:
        print("usage: build_manual_odds.py manual.csv [polymarket.json]  > out.json", file=sys.stderr)
        sys.exit(2)

    probs = {}
    if len(sys.argv) > 2:                                       # optional Polymarket base to merge into
        probs.update(json.load(open(sys.argv[2], encoding="utf-8")).get("probabilities", {}))

    manual = load_manual(sys.argv[1])
    for ta, tb, oh, od, oa in manual:
        p = _pair(ta, tb)                                       # drop any existing line for this pair (either way round)
        for k in [k for k in probs if "|" in k and _pair(*k.split("|")) == p]:
            del probs[k]
        probs[f"{ta}|{tb}"] = {"1": oh, "X": od, "2": oa}       # no "liquidity" key -> trusted, always blends

    print(f"[manual] {len(manual)} manual line(s) -> {len(probs)} total market(s) out", file=sys.stderr)
    json.dump({"source": "manual_1x2", "probabilities": probs}, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
