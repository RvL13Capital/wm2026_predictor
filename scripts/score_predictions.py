#!/usr/bin/env python3
"""Score pre-registered predictions against real results (S20/S21 early slice).

Closes the ops loop: scripts/log_predictions.py records what we predicted;
this scores it as results arrive, per logged artifact:

    python3 scripts/score_predictions.py --results data/live_state.json

For every matchday/ko entry in predictions_log/2026.jsonl it prints each
match's tip vs result with Kicktipp points (4/3/2 incl. the Tordifferenz draw
rule), the realized total vs the model's Σ-EV expectation over the SAME scored
subset, and what's still pending. Results come from the same live_state.json
the simulators consume ("Team A vs Team B": [ga, gb]; for KO matches enter the
shootout_total score per gate G1). Bonusfragen entries are listed but only
scoreable after the tournament (S21).
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import predictor  # noqa: E402

DEFAULT_LOG = os.path.join(REPO, "predictions_log", "2026.jsonl")


def _canon(name: str) -> str:
    return predictor.TEAM_NAME_MAPPING.get(str(name).strip().lower(), str(name).strip())


def build_results_index(results: dict) -> dict:
    """live_state-style dict -> {(canon_a, canon_b): (ga, gb)} both orientations."""
    index = {}
    for key, val in results.items():
        if " vs " not in key or not isinstance(val, (list, tuple)) or len(val) != 2:
            continue
        a, b = (
            _canon(part) for part in key.split(" vs ", 1))
        ga, gb = int(val[0]), int(val[1])
        index[(a, b)] = (ga, gb)
        index[(b, a)] = (gb, ga)
    return index


def score_entry(entry: dict, results_index: dict) -> dict:
    """Pure: one matchday/ko log entry -> scoring summary."""
    rows, total, ev_scored, pending = [], 0, 0.0, 0
    for m in entry.get("matches", []):
        a, b = _canon(m["team_a"]), _canon(m["team_b"])
        tip_a, tip_b = (int(x) for x in m["tip"].split(":"))
        res = results_index.get((a, b))
        if res is None:
            pending += 1
            rows.append((m, None, None))
            continue
        pts = predictor.get_points(tip_a, tip_b, res[0], res[1])
        total += pts
        ev_scored += float(m.get("ev", 0.0))
        rows.append((m, res, pts))
    return {"rows": rows, "points": total, "ev_scored": ev_scored,
            "n_scored": len(rows) - pending, "pending": pending}


def main():
    ap = argparse.ArgumentParser(description="Score the prediction log against real results")
    ap.add_argument("--results", default=os.path.join(REPO, "data", "live_state.json"),
                    help="Results JSON in live_state format")
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--all-matches", action="store_true",
                    help="Print every match line (default: only scored ones)")
    args = ap.parse_args()

    if not os.path.exists(args.results):
        sys.exit(f"❌ no results file at {args.results} — create it per docs/LIVE_STATE.md "
                 f"(and validate with scripts/validate_live_state.py)")
    with open(args.results, encoding="utf-8") as f:
        results_index = build_results_index(json.load(f))
    with open(args.log, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    grand_pts, grand_ev, grand_n = 0, 0.0, 0
    for entry in entries:
        kind = entry.get("kind")
        label = f"{kind} · {entry.get('source_file', '?')} · seed {entry.get('header', {}).get('seed', '?')}"
        if kind == "bonusfragen":
            print(f"\n⏳ {label}: bonus answers — scoreable post-tournament (S21)")
            continue
        s = score_entry(entry, results_index)
        print(f"\n📋 {label}")
        for m, res, pts in s["rows"]:
            if res is None:
                if args.all_matches:
                    print(f"   {m['team_a']} vs {m['team_b']}: tip {m['tip']} — pending")
                continue
            icon = {4: "🎯", 3: "✅", 2: "☑️", 0: "❌"}[pts]
            print(f"   {icon} {m['team_a']} vs {m['team_b']}: tip {m['tip']} → "
                  f"result {res[0]}:{res[1]} = {pts} pts (EV {m.get('ev', 0):.2f})")
        if s["n_scored"]:
            delta = s["points"] - s["ev_scored"]
            print(f"   Σ {s['points']} pts over {s['n_scored']} scored "
                  f"(model expected {s['ev_scored']:.2f}, luck {delta:+.2f}) · {s['pending']} pending")
            grand_pts += s["points"]
            grand_ev += s["ev_scored"]
            grand_n += s["n_scored"]
        else:
            print(f"   no results yet ({s['pending']} pending)")

    if grand_n:
        print(f"\n{'=' * 64}\nTOTAL: {grand_pts} pts over {grand_n} matches · "
              f"expected {grand_ev:.2f} · luck {grand_pts - grand_ev:+.2f}\n{'=' * 64}")


if __name__ == "__main__":
    main()
