#!/usr/bin/env python3
"""KO-round Kicktipp tip generator (plan step S19).

Generates EV-optimal tips for knockout fixtures through the SAME pipeline as
everything else (predictor.predict_single_match), which means the tips
automatically target the pool's verified scoring convention
(kicktipp_ko_convention = "shootout_total", gate G1 / validation/POOL_RULES.md)
and use the full stack: squad+injury Elo overrides, xG form, host support,
optional venue/altitude context, market 1X2 snapshots, and the bench-depth-
scaled "Dead Legs" fatigue for teams that played extra time in the previous
round.

Fixtures are supplied explicitly (KO pairings only exist once the groups
finish):

    python3 ko_tips.py --round R32 --matches "Spain vs Uruguay; France vs Germany" \
        --seed 42 --output data/r32_tips_v1.txt
    python3 ko_tips.py --round QF --fixtures data/qf_fixtures.json \
        --fatigued "Croatia,Japan" --odds-snapshot data/polymarket_snapshot_X.json

--fixtures JSON shape: [{"team_a": "...", "team_b": "...",
                         "venue": "Dallas"?, "rest_days_a": 3?, ...}, ...]
(optional per-fixture keys: venue, elevation, temp, humidity, rest_days_a/b,
 travel_miles_a/b, tz_crossed_a/b, accl_days_a/b)

Output format intentionally mirrors matchday_tips so
scripts/log_predictions.py --kind ko parses it unchanged.
"""
import argparse
import json
import random
import subprocess
import sys
from datetime import datetime, timezone

import predictor
import tournament_bonusfragen as tbf
from matchday_tips import _elo_overrides, load_market_snapshot

try:
    from squad_data import SQUAD_VALUES
except ImportError:
    SQUAD_VALUES = {}

VALID_ROUNDS = ["R32", "R16", "QF", "SF", "THIRD", "FINAL"]


def _dead_legs_multipliers(team: str):
    """Bench-depth-scaled exhaustion penalty for a team that played ET in its
    previous match — the same formula as vectorized_mc._build_knockout_matrix
    and backtest_harness (base 0.10, halved-to-full by bench resilience)."""
    val = SQUAD_VALUES.get(predictor.validate_team_name(team), {"xi": 100.0, "bench": 50.0})
    resilience = min(2.0, val.get("bench", 50.0) / 50.0)
    penalty = 0.10 / max(1.0, resilience)
    return 1.0 - penalty, 1.0 + penalty   # (attack multiplier, defence-leak multiplier)


def parse_fixtures(args) -> list:
    fixtures = []
    if args.fixtures:
        with open(args.fixtures, "r", encoding="utf-8") as f:
            for fx in json.load(f):
                fixtures.append(dict(fx))
    if args.matches:
        for part in args.matches.split(";"):
            part = part.strip()
            if not part:
                continue
            if " vs " not in part:
                raise SystemExit(f"Bad --matches entry {part!r} — expected 'TeamA vs TeamB'")
            a, b = part.split(" vs ", 1)
            fixtures.append({"team_a": a.strip(), "team_b": b.strip()})
    if not fixtures:
        raise SystemExit('No fixtures. Pass --matches "A vs B; C vs D" or --fixtures file.json')
    return fixtures


def run_ko_round(round_name: str, fixtures: list, n_simulations: int, seed: int,
                 market_probs: dict = None, fatigued=None) -> list:
    """Generate tips for one KO round. Returns a list of per-match dicts."""
    fatigued = {predictor.validate_team_name(t) for t in (fatigued or [])}
    squad_elo_adj = tbf.compute_squad_elo_adjustments() if tbf.SQUAD_MARKET_VALUES else {}

    results = []
    for idx, fx in enumerate(fixtures, 1):
        team_a = predictor.validate_team_name(str(fx["team_a"]))
        team_b = predictor.validate_team_name(str(fx["team_b"]))
        row = {"team_a": team_a, "team_b": team_b, "phase": round_name}

        # xG form and Dead Legs share the multiplicative form lever on λ_base
        form_a, form_b = tbf.compute_xg_form_multipliers(team_a, team_b)
        flags = []
        if team_a in fatigued:
            att, deff = _dead_legs_multipliers(team_a)
            form_a *= att
            form_b *= deff
            flags.append(f"{team_a} dead legs (att x{att:.2f}, leak x{deff:.2f})")
        if team_b in fatigued:
            att, deff = _dead_legs_multipliers(team_b)
            form_b *= att
            form_a *= deff
            flags.append(f"{team_b} dead legs (att x{att:.2f}, leak x{deff:.2f})")
        row["form_a"] = str(form_a)
        row["form_b"] = str(form_b)

        # Venue / environment context (manual or stadium-derived)
        venue = fx.get("venue")
        if venue:
            row["venue"] = venue
            sd = predictor.STADIUM_DATA.get(venue)
            if sd and sd.get("elevation", 0) > 1000 and "elevation" not in fx:
                row["elevation"] = str(sd["elevation"])
        for k in ("elevation", "temp", "humidity",
                  "rest_days_a", "rest_days_b", "travel_miles_a", "travel_miles_b",
                  "tz_crossed_a", "tz_crossed_b", "accl_days_a", "accl_days_b"):
            if k in fx:
                row[k] = str(fx[k])

        # Host support — same shares as the bonusfragen KO path
        if team_a in tbf.HOST_TEAMS:
            row["status_a"] = "True Home"
            row["fan_pct_a"] = "0.65"
            row["fan_pct_b"] = "0.35"
        elif team_b in tbf.HOST_TEAMS:
            row["status_b"] = "True Home"
            row["fan_pct_a"] = "0.35"
            row["fan_pct_b"] = "0.65"

        # Market 1X2 (same snapshot mechanics + orientation swap as matchday)
        if market_probs:
            od = market_probs.get(f"{team_a}|{team_b}")
            reversed_ = False
            if od is None:
                od = market_probs.get(f"{team_b}|{team_a}")
                reversed_ = od is not None
            if od and all(k in od for k in ("1", "X", "2")):
                row["odds_home"] = str(od["2"] if reversed_ else od["1"])
                row["odds_draw"] = str(od["X"])
                row["odds_away"] = str(od["1"] if reversed_ else od["2"])
                row["market_weight"] = "0.80"

        with _elo_overrides(team_a, team_b, squad_elo_adj):
            result = predictor.predict_single_match(row)

        grid = {int(a): {int(b): float(p) for b, p in inner.items()}
                for a, inner in result["grid"].items()}
        tip_a, tip_b = result["optimal_tip_a"], result["optimal_tip_b"]

        # Per-match MC (independent stream per fixture: seed + idx)
        mc_stats = None
        if n_simulations > 0:
            rng = random.Random(seed + idx)
            max_g = max(grid.keys())
            pts = []
            for _ in range(n_simulations):
                r = rng.random()
                cum = 0.0
                ga_sim = gb_sim = 0
                done = False
                for g_a in range(max_g + 1):
                    for g_b in range(max_g + 1):
                        cum += grid.get(g_a, {}).get(g_b, 0.0)
                        if cum > r:
                            ga_sim, gb_sim = g_a, g_b
                            done = True
                            break
                    if done:
                        break
                pts.append(predictor.get_points(tip_a, tip_b, ga_sim, gb_sim))
            mean = sum(pts) / len(pts)
            mc_stats = {
                "mean": mean,
                "std": (sum((x - mean) ** 2 for x in pts) / len(pts)) ** 0.5,
                "p0": pts.count(0) / len(pts),
                "p2": pts.count(2) / len(pts),
                "p3": pts.count(3) / len(pts),
                "p4": pts.count(4) / len(pts),
            }

        results.append({
            "team_a": team_a, "team_b": team_b, "phase": round_name,
            "lambda_base_a": result["lambda_a_base"], "lambda_base_b": result["lambda_b_base"],
            "lambda_adj_a": result["lambda_a_adj"], "lambda_adj_b": result["lambda_b_adj"],
            "p_home": result["p_home"], "p_draw": result["p_draw"], "p_away": result["p_away"],
            "optimal_tip": (tip_a, tip_b), "ev": result["ev"],
            "top_tips": result.get("top_tips", []),
            "ko_convention": result.get("ko_convention"),
            "flags": flags, "mc": mc_stats,
        })
    return results


def format_results(results: list, args) -> str:
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                         stderr=subprocess.STDOUT).decode().strip()
        if subprocess.call(['git', 'diff', '--quiet']) != 0:
            commit += " (dirty)"
    except Exception:
        commit = "unknown"

    lines = []
    lines.append(f"Loaded {len(results)} fixtures for knockout round {args.round}")
    lines.append(f"📅 Timestamp: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"🌱 Seed: {args.seed}")
    lines.append(f"🔗 Commit: {commit}")
    lines.append(f"⚙️  Cmd: {' '.join(sys.argv)}")
    conv = results[0]["ko_convention"] if results else "?"
    lines.append(f"⚖️  KO convention: {conv} (gate G1, validation/POOL_RULES.md)")
    lines.append("")

    total_ev = 0.0
    for i, res in enumerate(results, 1):
        lines.append(f"Match {i}: {res['team_a']} vs {res['team_b']} [{res['phase']}]")
        lines.append(f"  λ_base: {res['lambda_base_a']:.3f} / {res['lambda_base_b']:.3f}"
                     f"  →  λ_adj: {res['lambda_adj_a']:.3f} / {res['lambda_adj_b']:.3f}")
        lines.append(f"  P(Home)={res['p_home']*100:.1f}%  P(Draw)={res['p_draw']*100:.1f}%"
                     f"  P(Away)={res['p_away']*100:.1f}%")
        lines.append(f"  ★ Optimal tip: {res['optimal_tip'][0]}:{res['optimal_tip'][1]}"
                     f"  (EV = {res['ev']:.3f} pts)")
        total_ev += res["ev"]
        tt = res.get("top_tips") or []
        if len(tt) >= 2:
            lines.append(f"     runner-up: {tt[1]['tip']} (EV {tt[1]['ev']:.3f})"
                         f"  |  margin Δ {tt[0]['ev'] - tt[1]['ev']:.3f}")
        for flag in res["flags"]:
            lines.append(f"     [!] {flag}")
        if res["mc"]:
            mc = res["mc"]
            lines.append(f"  MC ({args.simulations:,} sims): μ={mc['mean']:.3f}  σ={mc['std']:.3f}  "
                         f"P(0)={mc['p0']*100:.1f}%  P(2)={mc['p2']*100:.1f}%  "
                         f"P(3)={mc['p3']*100:.1f}%  P(4)={mc['p4']*100:.1f}%")
        lines.append("")

    lines.append("=" * 60)
    lines.append("ROUND SUMMARY")
    lines.append("=" * 60)
    lines.append(f"  Matches:              {len(results)}")
    lines.append(f"  Total EV (analytic):  {total_ev:.3f} pts")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KO-round Kicktipp tip generator")
    parser.add_argument("--round", type=str, required=True, choices=VALID_ROUNDS,
                        help="Knockout round")
    parser.add_argument("--matches", type=str, default=None,
                        help='Inline fixtures: "A vs B; C vs D"')
    parser.add_argument("--fixtures", type=str, default=None,
                        help="JSON file with fixture dicts (team_a, team_b, optional context)")
    parser.add_argument("--fatigued", type=str, default="",
                        help="Comma-separated teams that played ET in the previous round (Dead Legs)")
    parser.add_argument("--simulations", type=int, default=1000, help="MC sims per match")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--output", type=str, default=None, help="Output file")
    parser.add_argument("--odds-snapshot", type=str, default=None,
                        help="Polymarket 1X2 snapshot JSON (matchday_tips format)")
    args = parser.parse_args()

    market_probs = None
    if args.odds_snapshot:
        market_probs, _extras = load_market_snapshot(args.odds_snapshot)
        print(f"Loaded {len(market_probs)} 1X2 markets from {args.odds_snapshot}", file=sys.stderr)

    fatigued = [t.strip() for t in args.fatigued.split(",") if t.strip()]
    fixtures = parse_fixtures(args)
    results = run_ko_round(args.round, fixtures, args.simulations, args.seed,
                           market_probs=market_probs, fatigued=fatigued)
    output = format_results(results, args)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Results written to {args.output}")
    else:
        print(output)

    # Alert (stderr + WhatsApp if configured) when any tip changed vs the last run.
    from utils import recommendations_state as rec_state
    rec_state.alert_on_changes(
        f"KO-{args.round}",
        {f"{r['team_a']} vs {r['team_b']}": f"{r['optimal_tip'][0]}:{r['optimal_tip'][1]}" for r in results})
