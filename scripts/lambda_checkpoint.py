#!/usr/bin/env python3
"""Group-stage λ-freeze checkpoint (pre-registered 2026-06-11, before the opener).

The λ calibration is frozen (validation/points_recalibration.md) — with ONE
sanctioned exception: after the last group match and before the Jun-28 KO
change freeze, this script evaluates whether the engine's clean-sheet-heavy
exact-score claims survived contact with the group stage. The criteria are
pre-registered here so the decision is mechanical, not vibes.

PRIMARY TRIPWIRE (band-conditional exact-hit deficit):
  Over all logged group-stage tips whose RESULT landed in the tip's
  goal-difference band (i.e. the tip already earned >= 3 points, so tendency
  luck is conditioned away), the engine claims the exact 4-pt hit arrives
  with probability p_i = P(exact tip | result in band) from its own grid.
  Let X = realized exact hits, E = sum p_i, V = sum p_i (1 - p_i).
  Trigger iff z = (X - E) / sqrt(V) <= -1.645  (one-sided 5%), n_banded >= 20.

  This is exactly the "1:0 vs 2:1" question: if real losers score more often
  than the low-λ grid claims, exact hits land below E and z goes negative.

SECONDARY (context only, never a trigger): realized points vs Σ-EV with the
model's own per-tip standard deviation — tendency variance dominates it, so
it is reported but carries no decision weight.

If the tripwire fires, λ recalibration is PERMITTED (not required) before the
first KO kickoff, under the standing rules: LOTO grid + 192-fold harness
re-run, beat the 295 points floor or update it with a measurement in the doc,
full suite green. If it does not fire, the freeze holds until post-tournament.

p_i caveat: grids are reproduced with the deterministic Elo+stack path
(no market blend) at evaluation time. The freeze guarantees the calibration
itself is unchanged since logging; injury-Elo drift between lock night and
evaluation shifts the conditional p_i only in second order. Documented, accepted.

Usage:
    python3 scripts/lambda_checkpoint.py --results data/live_state.json

Exit codes: 0 = no trigger (or nothing scoreable yet), 3 = TRIPWIRE FIRED.
"""
import argparse
import json
import math
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import matchday_tips as M  # noqa: E402
import predictor  # noqa: E402

DEFAULT_LOG = os.path.join(REPO, "predictions_log", "2026.jsonl")

Z_TRIGGER = -1.645   # one-sided 5%
MIN_BANDED = 20      # below this the test has no power — report only


def _canon(name: str) -> str:
    return predictor.TEAM_NAME_MAPPING.get(str(name).strip().lower(), str(name).strip())


def build_results_index(results: dict) -> dict:
    index = {}
    for key, val in results.items():
        if " vs " not in key or not isinstance(val, (list, tuple)) or len(val) != 2:
            continue
        a, b = (_canon(p) for p in key.split(" vs ", 1))
        ga, gb = int(val[0]), int(val[1])
        index[(a, b)] = (ga, gb)
        index[(b, a)] = (gb, ga)
    return index


def band_conditional_p(grid, tip_a: int, tip_b: int):
    """(P(exact tip | result in tip's >=3-pt band), P(band)) from an engine grid."""
    p_band = 0.0
    for a in grid:
        for b in grid[a]:
            if predictor.get_points(tip_a, tip_b, a, b) >= 3:
                p_band += grid[a][b]
    p_exact = grid.get(tip_a, {}).get(tip_b, 0.0)
    if p_band <= 0.0:
        return 0.0, 0.0
    return p_exact / p_band, p_band


def evaluate(banded):
    """Pure tripwire statistics. banded = [(hit: bool, p_i: float), ...]."""
    n = len(banded)
    x = sum(1 for hit, _ in banded if hit)
    e = sum(p for _, p in banded)
    v = sum(p * (1.0 - p) for _, p in banded)
    z = (x - e) / math.sqrt(v) if v > 0 else 0.0
    triggered = (n >= MIN_BANDED) and (z <= Z_TRIGGER)
    return {"n_banded": n, "exact_hits": x, "expected": e, "variance": v,
            "z": z, "triggered": triggered}


def engine_grids(md: int) -> dict:
    """{(canon_a, canon_b): grid} for one matchday — deterministic Elo+stack path."""
    grids = {}
    for r in M.run_matchday(md, 0, 42, None, None):
        grids[(_canon(r["team_a"]), _canon(r["team_b"]))] = r["grid"]
    return grids


def main():
    ap = argparse.ArgumentParser(description="Pre-registered group-stage λ-freeze checkpoint")
    ap.add_argument("--results", required=True, help="live_state.json with final scores")
    ap.add_argument("--log", default=DEFAULT_LOG, help="predictions log JSONL")
    args = ap.parse_args()

    results_index = build_results_index(json.load(open(args.results)))
    entries = [json.loads(line) for line in open(args.log)]
    md_entries = [e for e in entries if e.get("kind") == "matchday"]

    banded, scored, total_pts, total_ev = [], 0, 0, 0.0
    for entry in md_entries:
        m_md = re.search(r"matchday(\d)", entry.get("source_file", ""))
        if not m_md:
            continue
        grids = engine_grids(int(m_md.group(1)))
        for m in entry["matches"]:
            a, b = _canon(m["team_a"]), _canon(m["team_b"])
            res = results_index.get((a, b))
            if res is None:
                continue
            tip_a, tip_b = (int(x) for x in m["tip"].split(":"))
            pts = predictor.get_points(tip_a, tip_b, res[0], res[1])
            scored += 1
            total_pts += pts
            total_ev += float(m.get("ev", 0.0))
            if pts >= 3:  # result landed in the tip's band
                grid = grids.get((a, b)) or grids.get((b, a))
                if grid is None:
                    print(f"  ⚠ no engine grid for {a} vs {b} — skipped from tripwire")
                    continue
                p_i, p_band = band_conditional_p(grid, tip_a, tip_b)
                banded.append((pts == 4, p_i))

    if scored == 0:
        print("No logged group matches have results yet — nothing to evaluate. Freeze holds.")
        return 0

    stats = evaluate(banded)
    print("═" * 64)
    print("  λ-FREEZE CHECKPOINT  (pre-registered 2026-06-11)")
    print("═" * 64)
    print(f"  scored matches:          {scored}")
    print(f"  realized points / Σ-EV:  {total_pts} / {total_ev:.1f}  (context only)")
    print(f"  in-band (≥3 pts):        {stats['n_banded']}  (min for power: {MIN_BANDED})")
    print(f"  exact 4-pt hits:         {stats['exact_hits']}  vs model-claimed {stats['expected']:.2f}")
    print(f"  tripwire z:              {stats['z']:+.3f}  (trigger ≤ {Z_TRIGGER})")
    print("─" * 64)
    if stats["triggered"]:
        print("  🚨 TRIPWIRE FIRED — λ recalibration PERMITTED before first KO")
        print("     kickoff under the standing rules (harness re-run, beat or")
        print("     update the 295 floor with a measurement, full suite green).")
        return 3
    print("  ✅ No trigger — λ freeze holds until post-tournament.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
