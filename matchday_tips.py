import argparse
import sys
import json
import time
from typing import Dict, Any, List
import random
from datetime import datetime, timezone
import subprocess

import predictor
import tournament_bonusfragen as tbf
import schedule_context

# --- Strategic-flag thresholds (READ-ONLY advisory; does NOT change the EV tip) ---
# Cells the 144-match backtest (WC 2014-22) showed the NB grid OVER-predicts in-sample
# (1-1 0.61x, 3-1 0.72x, 1-3 0.60x actual/model) -> treat as soft "traps", not certainty.
BACKTEST_TRAPS = {(1, 1), (3, 1), (1, 3)}
# ...and UNDER-predicts (2-1 1.34x, 1-2 1.63x) -> live differential value on a near-tie.
BACKTEST_VALUE = {(2, 1), (1, 2)}
EV_PLATEAU = 0.05   # EV gap below which #1 and #2 are effectively tied (display heuristic, not fitted)
MIN_MARKET_LIQUIDITY = 1000.0   # USD; a tagged market below this is noise -> skip the blend, fall back to Elo


def run_matchday(md: int, n_simulations: int, seed: int, market_probs: dict = None) -> List[Dict[str, Any]]:
    """Generate tips for a specific matchday using the FULL STACK."""
    match_results = []
    
    # Ensure seed is set for determinism
    rng = random.Random(seed)
    
    # Calculate squad value adjustments
    squad_elo_adj = tbf.compute_squad_elo_adjustments() if tbf.SQUAD_MARKET_VALUES else {}
    
    group_contexts, _ = schedule_context.get_group_match_contexts()
    
    match_index = 0
    for group, teams in tbf.GROUPS.items():
        if md == 1:
            matchups = [(teams[0], teams[1]), (teams[2], teams[3])]
        elif md == 2:
            matchups = [(teams[0], teams[2]), (teams[1], teams[3])]
        elif md == 3:
            matchups = [(teams[0], teams[3]), (teams[1], teams[2])]
        else:
            raise ValueError("Matchday must be 1, 2, or 3")
            
        for team_a, team_b in matchups:
            match_index += 1
            row = {"team_a": team_a, "team_b": team_b, "phase": "GROUP"}
            
            # Inject context from tournament_bonusfragen logic
            ctx = group_contexts.get((team_a, team_b))
            if not ctx:
                ctx = group_contexts.get((team_b, team_a))
                if ctx:
                    # swap prefix
                    row["rest_days_a"] = str(ctx["rest_days_b"])
                    row["rest_days_b"] = str(ctx["rest_days_a"])
                    row["travel_miles_a"] = str(ctx["travel_miles_b"])
                    row["travel_miles_b"] = str(ctx["travel_miles_a"])
                    row["tz_crossed_a"] = str(ctx["tz_crossed_b"])
                    row["tz_crossed_b"] = str(ctx["tz_crossed_a"])
            
            if ctx and "rest_days_a" not in row:
                for k, v in ctx.items():
                    row[k] = str(v)
            
            if team_a in tbf.HOST_TEAMS:
                row["status_a"] = "True Home"
                if team_a == "Mexico":
                    row["fan_pct_a"] = "0.90"
                elif team_a == "USA":
                    row["fan_pct_a"] = "0.80"
                elif team_a == "Canada":
                    row["fan_pct_a"] = "0.75"
            
            if team_b in tbf.HOST_TEAMS:
                row["status_b"] = "True Home"
                if team_b == "Mexico":
                    row["fan_pct_b"] = "0.90"
                elif team_b == "USA":
                    row["fan_pct_b"] = "0.80"
                elif team_b == "Canada":
                    row["fan_pct_b"] = "0.75"
                    
            elevation, accl_a, accl_b = tbf._get_match_elevation(team_a, team_b)
            if elevation > 0:
                row["elevation"] = str(elevation)
                row["accl_days_a"] = str(accl_a)
                row["accl_days_b"] = str(accl_b)
                
            # Apply form multipliers
            form_a, form_b = tbf.compute_xg_form_multipliers(team_a, team_b)

            # --- Empirical MD3 caution (the ONLY MD3 effect the backtest survived) ---
            # validation/md3_regime_backtest.py: across 48 real MD3 matches (2014-2022),
            # goals ran ~0.84-0.87x of base expectation in EVERY bucket — a universal
            # "decisive group game is cagey" effect, not regime game-theory. So: one flat trim.
            if md == 3:
                form_a *= 0.87
                form_b *= 0.87

            row["form_a"] = str(form_a)
            row["form_b"] = str(form_b)
            
            # --- REAL MATCH ODDS INTEGRATION (1X2) ---
            # market_probs is keyed "TeamA|TeamB" -> {"1": dec, "X": dec, "2": dec} (raw decimal
            # odds, vig intact). predictor strips the FLB via the Power method + KL solver, so we
            # blend at full 0.80. No synthesis, no sqrt: the clean wisdom-of-crowds path.
            if market_probs:
                ta = predictor.TEAM_NAME_MAPPING.get(team_a.lower(), team_a)
                tb = predictor.TEAM_NAME_MAPPING.get(team_b.lower(), team_b)
                key_fwd = f"{ta}|{tb}"
                key_rev = f"{tb}|{ta}"
                odds_data = None
                is_reversed = False
                if key_fwd in market_probs:
                    odds_data = market_probs[key_fwd]
                elif key_rev in market_probs:
                    odds_data = market_probs[key_rev]
                    is_reversed = True
                # liquidity guard: a thin/illiquid market is noise — skip the blend, fall back to Elo.
                # (a manual override with no "liquidity" key is trusted and always blends.)
                if odds_data and "1" in odds_data and "2" in odds_data and "X" in odds_data \
                        and float(odds_data.get("liquidity", float("inf"))) >= MIN_MARKET_LIQUIDITY:
                    if not is_reversed:
                        row["odds_home"] = str(odds_data["1"])
                        row["odds_draw"] = str(odds_data["X"])
                        row["odds_away"] = str(odds_data["2"])
                    else:
                        # market lists the teams the other way round -> swap home/away
                        row["odds_home"] = str(odds_data["2"])
                        row["odds_draw"] = str(odds_data["X"])
                        row["odds_away"] = str(odds_data["1"])
                    row["market_weight"] = "0.80"   # reactivated: real 1x2 line, not outrights

            # Use predictor's full pipeline
            # Injecting squad and injury adjustments
            elo_a = predictor.WORLD_CUP_2026_TEAMS.get(team_a, {}).get("elo", 1500)
            elo_b = predictor.WORLD_CUP_2026_TEAMS.get(team_b, {}).get("elo", 1500)
            
            # Predictor's predict_single_match uses WORLD_CUP_2026_TEAMS directly, 
            # so we temporarily apply the adjustments to the global dict (as in tournament_sim)
            orig_elo_a = predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"] if team_a in predictor.WORLD_CUP_2026_TEAMS else 1500
            orig_elo_b = predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"] if team_b in predictor.WORLD_CUP_2026_TEAMS else 1500
            
            if team_a in predictor.WORLD_CUP_2026_TEAMS:
                predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"] = orig_elo_a + squad_elo_adj.get(team_a, 0.0) + tbf.INJURY_ELO_ADJUSTMENTS.get(team_a, 0.0)
            if team_b in predictor.WORLD_CUP_2026_TEAMS:
                predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"] = orig_elo_b + squad_elo_adj.get(team_b, 0.0) + tbf.INJURY_ELO_ADJUSTMENTS.get(team_b, 0.0)
            
            result = predictor.predict_single_match(row)
            
            # Restore
            if team_a in predictor.WORLD_CUP_2026_TEAMS:
                predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"] = orig_elo_a
            if team_b in predictor.WORLD_CUP_2026_TEAMS:
                predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"] = orig_elo_b
            
            # Parse grid from str keys to int keys
            grid_str = result["grid"]
            grid = {}
            for ga_str, gb_dict in grid_str.items():
                ga = int(ga_str)
                grid[ga] = {}
                for gb_str, p in gb_dict.items():
                    grid[ga][int(gb_str)] = float(p)
            
            base_a = result["lambda_a_base"]
            base_b = result["lambda_b_base"]
            lambda_adj_a = result["lambda_a_adj"]
            lambda_adj_b = result["lambda_b_adj"]
            
            # Optimal tip is already calculated by predict_single_match
            # It returns optimal_tip as a string "X:Y", we need to parse it to tuple (X,Y)
            tip_str = result["optimal_tip"]
            optimal_tip = (int(tip_str.split(":")[0]), int(tip_str.split(":")[1]))
            max_ev = result["ev"]
            
            # Monte Carlo
            mc_stats = None
            if n_simulations > 0:
                match_seed = seed + match_index  # F6: unique seed per match!
                match_rng = random.Random(match_seed)
                
                # We need a dummy config to pass to get_points
                # since we only use it for the scoring rules (pts_exact, etc)
                from predictor import MatchModelConfig, ModelDistribution
                dummy_config = MatchModelConfig(
                    dist_type=ModelDistribution.POISSON,
                    mu_a=lambda_adj_a, mu_b=lambda_adj_b,
                    pts_exact=4, pts_diff=3, pts_tend=2, max_goals=15
                )
                
                pts = []
                for _ in range(n_simulations):
                    r_a = match_rng.random()
                    
                    cum_prob = 0.0
                    ga_sim, gb_sim = 0, 0
                    for g_a in range(dummy_config.max_goals + 1):
                        for g_b in range(dummy_config.max_goals + 1):
                            cum_prob += grid.get(g_a, {}).get(g_b, 0.0)
                            if cum_prob > r_a:
                                ga_sim, gb_sim = g_a, g_b
                                break
                        if cum_prob > r_a:
                            break
                            
                    pt = predictor.get_points(optimal_tip[0], optimal_tip[1], ga_sim, gb_sim, pts_exact=4, pts_diff=3, pts_tend=2)
                    pts.append(pt)
                    
                pts.sort()
                mc_stats = {
                    "mean": sum(pts) / len(pts),
                    "std": (sum((x - sum(pts)/len(pts))**2 for x in pts) / len(pts))**0.5,
                    "p0": pts.count(0) / len(pts),
                    "p2": pts.count(2) / len(pts),
                    "p3": pts.count(3) / len(pts),
                    "p4": pts.count(4) / len(pts),
                }

            match_results.append({
                "team_a": team_a,
                "team_b": team_b,
                "lambda_base_a": base_a,
                "lambda_base_b": base_b,
                "lambda_adj_a": lambda_adj_a,
                "lambda_adj_b": lambda_adj_b,
                "grid": grid,
                "optimal_tip": optimal_tip,
                "ev": max_ev,
                "top_tips": result.get("top_tips", []),
                "mc": mc_stats
            })
            
    return match_results

def print_results(results: List[Dict[str, Any]], args: argparse.Namespace):
    try:
        commit_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.STDOUT).decode('utf-8').strip()
        is_dirty = subprocess.call(['git', 'diff', '--quiet']) != 0
        if is_dirty:
            commit_hash += " (dirty)"
    except Exception:
        commit_hash = "unknown"
        
    lines = []
    lines.append(f"Loaded {len(results)} matches dynamically from GROUPS for Matchday {args.md}")
    lines.append(f"📅 Timestamp: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"🌱 Seed: {args.seed}")
    lines.append(f"🔗 Commit: {commit_hash}")
    lines.append(f"⚙️  Cmd: {' '.join(sys.argv)}")
    lines.append("")
    
    total_ev = 0.0
    total_mc_mean = 0.0
    
    for i, res in enumerate(results, 1):
        lines.append(f"Match {i}: {res['team_a']} vs {res['team_b']} [GROUP]")
        lines.append(f"  λ_base: {res['lambda_base_a']:.3f} / {res['lambda_base_b']:.3f}  →  λ_adj: {res['lambda_adj_a']:.3f} / {res['lambda_adj_b']:.3f}")
        
        grid = res["grid"]
        p_h = sum(grid[ga][gb] for ga in grid for gb in grid[ga] if ga > gb) * 100
        p_d = sum(grid[ga][gb] for ga in grid for gb in grid[ga] if ga == gb) * 100
        p_a = sum(grid[ga][gb] for ga in grid for gb in grid[ga] if ga < gb) * 100
        lines.append(f"  P(Home)={p_h:.1f}%  P(Draw)={p_d:.1f}%  P(Away)={p_a:.1f}%")
        
        lines.append(f"  ★ Optimal tip: {res['optimal_tip'][0]}:{res['optimal_tip'][1]}  (EV = {res['ev']:.3f} pts)")
        total_ev += res["ev"]

        # READ-ONLY strategic flag: surface the EV margin + in-sample bias (does NOT change the tip)
        tt = res.get("top_tips") or []
        if len(tt) >= 2:
            top = tuple(int(x) for x in tt[0]["tip"].split(":"))
            alt = tuple(int(x) for x in tt[1]["tip"].split(":"))
            delta = tt[0]["ev"] - tt[1]["ev"]
            lines.append(f"     runner-up: {alt[0]}:{alt[1]} (EV {tt[1]['ev']:.3f})  |  margin Δ {delta:.3f}")
            if delta >= EV_PLATEAU:
                lines.append(f"     [+] STRONG SIGNAL — engine confident; lock in {top[0]}:{top[1]}.")
            elif top in BACKTEST_TRAPS and alt in BACKTEST_VALUE:
                lines.append(f"     [!] FLAT EV PLATEAU (Δ {delta:.3f} < {EV_PLATEAU}): {top[0]}:{top[1]} is an in-sample "
                             f"over-pick, {alt[0]}:{alt[1]} under-picked — effectively tied.")
                if getattr(args, "trailing", False):
                    lines.append(f"     [>] TRAILING the pool → lean {alt[0]}:{alt[1]}: ~0 EV cost, more differential variance.")
                else:
                    lines.append(f"     [>] LEVEL/AHEAD → lean {top[0]}:{top[1]}: matches the high-ownership consensus, lower variance.")
            else:
                lines.append(f"     [i] low confidence — {top[0]}:{top[1]} and {alt[0]}:{alt[1]} effectively tied (Δ {delta:.3f}).")
        
        if res["mc"]:
            mc = res["mc"]
            lines.append(f"  MC ({args.simulations:,} sims): μ={mc['mean']:.3f}  σ={mc['std']:.3f}  "
                         f"P(0)={mc['p0']*100:.1f}%  P(2)={mc['p2']*100:.1f}%  "
                         f"P(3)={mc['p3']*100:.1f}%  P(4)={mc['p4']*100:.1f}%")
            total_mc_mean += mc['mean']
        lines.append("")
        
    lines.append("=" * 60)
    lines.append("TOURNAMENT SUMMARY")
    lines.append("=" * 60)
    lines.append(f"  Matches:              {len(results)}")
    lines.append(f"  Total EV (analytic):  {total_ev:.3f} pts")
    if args.simulations > 0:
        lines.append(f"  Total MC mean:        {total_mc_mean:.3f} pts")
    lines.append("=" * 60)
    
    output = "\n".join(lines)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
    else:
        print(output)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Matchday Tip Generator")
    parser.add_argument("--md", type=int, choices=[1, 2, 3], required=True, help="Matchday (1, 2, 3)")
    parser.add_argument("--simulations", type=int, default=1000, help="Number of MC simulations")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--output", type=str, help="Output file")
    parser.add_argument("--odds-snapshot", type=str, help="Path to Polymarket JSON snapshot")
    parser.add_argument("--trailing", action="store_true", help="Pool game-theory: you are behind the leader -- lean contrarian on flat EV plateaus")
    
    args = parser.parse_args()
    
    market_probs = None
    if args.odds_snapshot:
        with open(args.odds_snapshot, "r") as f:
            snapshot = json.load(f)

        raw = snapshot.get("probabilities", snapshot)
        market_probs = {}
        aliases = {"united states": "usa", "us": "usa", "korea republic": "south korea"}
        for k, v in raw.items():
            if "|" in k:                              # match-specific "TeamA|TeamB" key
                parts = k.split("|")
                ta_key = aliases.get(parts[0].lower().strip(), parts[0].lower().strip())
                tb_key = aliases.get(parts[1].lower().strip(), parts[1].lower().strip())
                t1 = predictor.TEAM_NAME_MAPPING.get(ta_key, parts[0].strip())
                t2 = predictor.TEAM_NAME_MAPPING.get(tb_key, parts[1].strip())
                market_probs[f"{t1}|{t2}"] = v
        print(f"Loaded {len(market_probs)} match-specific 1X2 markets from {args.odds_snapshot}",
              file=sys.stderr)

    res = run_matchday(args.md, args.simulations, args.seed, market_probs)
    print_results(res, args)
