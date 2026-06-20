#!/usr/bin/env python3
"""Read-only runner that shows the main tip ALONGSIDE the O/U-total tip.

This is the presentation layer for the isolated `ou_total_engine`. It reuses
`matchday_tips.run_matchday` to get the EXACT same per-match lambdas / config /
market_total the main sheet uses, then asks the O/U engine for its alternative
score. Data flows one way only (main -> O/U); nothing here writes back into the
main tip path.

It calls `run_matchday` directly (NOT matchday_tips.main()), so the
recommendation-change WhatsApp hook is never invoked — safe for ad-hoc runs.

Usage:
    python3 ou_total_tips.py --md 2 --odds-snapshot data/polymarket_match_odds.json \
        --upcoming-only --seed 42
"""
import argparse
import json
import os
import sys

import matchday_tips
import ou_total_engine

ROOT = os.path.dirname(os.path.abspath(__file__))

# A flipped tip whose EV beats the main tip by less than this (Kicktipp points) under
# the adjusted grid is a coin-flip tie-break, not a signal — shown but not starred.
MIN_EV_MARGIN = 0.02


def _upcoming_keys(live_state_path):
    """frozenset pairs already played (to filter them out), or None if unreadable."""
    try:
        with open(live_state_path) as f:
            live = json.load(f)
    except Exception:
        return None
    return {frozenset(k.split(" vs ")) for k in live}


def main():
    ap = argparse.ArgumentParser(description="Main tip vs O/U-total tip (isolated engine)")
    ap.add_argument("--md", type=int, required=True, help="matchday (1-3)")
    ap.add_argument("--odds-snapshot", default="data/polymarket_match_odds.json",
                    help="Polymarket snapshot (must carry O/U extras / market_total)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--simulations", type=int, default=0, help="MC sims (0 = skip; not needed here)")
    ap.add_argument("--upcoming-only", action="store_true",
                    help="show only fixtures not yet in --live-state")
    ap.add_argument("--live-state", default="data/live_state.json")
    args = ap.parse_args()

    snap_path = args.odds_snapshot if os.path.isabs(args.odds_snapshot) \
        else os.path.join(ROOT, args.odds_snapshot)
    market_probs, market_extras = matchday_tips.load_market_snapshot(snap_path)
    if not market_probs:
        sys.exit(f"❌ no market odds loaded from {snap_path} — the O/U engine needs market_total")

    results = matchday_tips.run_matchday(args.md, args.simulations, args.seed,
                                         market_probs, market_extras)

    played = _upcoming_keys(args.live_state) if args.upcoming_only else None

    print(f"O/U-TOTAL ENGINE  —  Matchday {args.md}  (isolated, read-only; main 1X2 tip vs O/U-total tip)")
    print("=" * 92)
    print(f"{'Match (engine order)':38} {'Main':>5}  {'O/U':>5}  {'Δtot':>6}  "
          f"{'λ→ (Tore:Geg.)':>14}  Note")
    print("-" * 92)

    n_diff = 0
    n_shown = 0
    no_market = []
    for r in results:
        key = frozenset((r["team_a"], r["team_b"]))
        if played is not None and key in played:
            continue
        n_shown += 1
        main_tip = f'{r["optimal_tip"][0]}:{r["optimal_tip"][1]}'
        ou = ou_total_engine.ou_total_tip(r["lambda_adj_a"], r["lambda_adj_b"],
                                          r["config"], r.get("market_total"))
        label = f'{r["team_a"]} vs {r["team_b"]}'[:38]
        if ou is None:
            no_market.append(label)
            print(f"{label:38} {main_tip:>5}  {'—':>5}  {'—':>6}  {'(no O/U)':>14}  market_total missing")
            continue
        # Gate a DIFF on the EV margin: a flipped tip that beats the main tip by less
        # than MIN_EV_MARGIN under the adjusted grid is a coin-flip, not a signal.
        marg = (ou["ev_by_tip"].get(ou["tip"], 0.0) - ou["ev_by_tip"].get(main_tip, 0.0)) \
            if ou["tip"] != main_tip else 0.0
        real = ou["tip"] != main_tip and marg >= MIN_EV_MARGIN
        if real:
            n_diff += 1
        dtot = ou["total_delta"]
        arrow = "↑more" if dtot > 0.15 else ("↓fewer" if dtot < -0.15 else "≈")
        if ou["tip"] == main_tip:
            note = f"agree ({arrow})"
        elif real:
            note = f"DIFF Δev{marg:+.3f}: market {arrow} goals (mkt {ou['market_total']:.2f} vs model {ou['model_total']:.2f})"
        else:
            note = f"~tie Δev{marg:+.3f} (coin-flip — keep main {main_tip})"
        flag = " *" if real else "  "
        print(f"{label:38} {main_tip:>5}  {ou['tip']:>5}{flag} {dtot:>+6.2f}  "
              f"{ou['lam_a']:>5.2f}:{ou['lam_b']:<4.2f}     {note}")

    print("-" * 92)
    print(f"{n_shown} fixtures shown; {n_diff} where the O/U-total tip DIFFERS from the main tip"
          + (f"; {len(no_market)} without an O/U market" if no_market else ""))
    print("Note: the O/U tip keeps the main model's winner & goal DIFFERENCE, only the TOTAL is")
    print("      re-slaved to Polymarket's Over/Under (market_total). It feeds back into nothing.")


if __name__ == "__main__":
    main()
