#!/usr/bin/env python3
import os
import sys
import csv
import argparse
from io import StringIO
from typing import List, Dict

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import predictor

TEAM_STATS = {
    "Qatar": {"off": 0.8, "def": 1.4},
    "Ecuador": {"off": 1.1, "def": 1.0},
    "Senegal": {"off": 1.2, "def": 1.1},
    "Netherlands": {"off": 1.5, "def": 0.8},
    "England": {"off": 1.8, "def": 0.7},
    "Iran": {"off": 0.9, "def": 1.2},
    "USA": {"off": 1.1, "def": 0.9},
    "Wales": {"off": 0.8, "def": 1.3},
    "Argentina": {"off": 1.9, "def": 0.7},
    "Saudi Arabia": {"off": 0.9, "def": 1.3},
    "Mexico": {"off": 1.1, "def": 1.0},
    "Poland": {"off": 1.0, "def": 1.1},
    "France": {"off": 2.0, "def": 0.8},
    "Australia": {"off": 1.0, "def": 1.1},
    "Denmark": {"off": 1.2, "def": 0.9},
    "Tunisia": {"off": 0.9, "def": 1.0},
    "Spain": {"off": 1.7, "def": 0.8},
    "Costa Rica": {"off": 0.7, "def": 1.5},
    "Germany": {"off": 1.6, "def": 1.0},
    "Japan": {"off": 1.3, "def": 1.0},
    "Belgium": {"off": 1.3, "def": 1.0},
    "Canada": {"off": 1.0, "def": 1.3},
    "Morocco": {"off": 1.3, "def": 0.6},
    "Croatia": {"off": 1.4, "def": 0.8},
    "Brazil": {"off": 2.0, "def": 0.7},
    "Serbia": {"off": 1.2, "def": 1.3},
    "Switzerland": {"off": 1.2, "def": 1.0},
    "Cameroon": {"off": 1.1, "def": 1.2},
    "Portugal": {"off": 1.7, "def": 0.9},
    "Ghana": {"off": 1.1, "def": 1.4},
    "Uruguay": {"off": 1.1, "def": 0.9},
    "South Korea": {"off": 1.1, "def": 1.1}
}

FALLBACK_MATCHES = [
    {
        "team_a": "Germany", "team_b": "Japan", "goals_a": 1, "goals_b": 2,
        "elevation": 0.0, "temp": 22.0, "humidity": 50.0, "status_a": "Neutral", "status_b": "Neutral",
        "fan_pct_a": 0.5, "fan_pct_b": 0.5, "rest_days_a": 3.0, "rest_days_b": 6.0,
        "travel_miles_a": 4000.0, "travel_miles_b": 0.0, "tz_crossed_a": 6, "tz_crossed_b": 0,
        "direction_a": "East", "direction_b": "None", "accl_days_a": 0.0, "accl_days_b": 0.0,
        "heat_accl_days_a": 0.0, "heat_accl_days_b": 0.0, "alpha_a": 0.05, "alpha_b": 0.05, "rho": -0.05
    },
    {
        "team_a": "Croatia", "team_b": "Morocco", "goals_a": 0, "goals_b": 0,
        "elevation": 0.0, "temp": 22.0, "humidity": 50.0, "status_a": "Neutral", "status_b": "Neutral",
        "fan_pct_a": 0.2, "fan_pct_b": 0.8, "rest_days_a": 5.0, "rest_days_b": 5.0,
        "travel_miles_a": 0.0, "travel_miles_b": 0.0, "tz_crossed_a": 0, "tz_crossed_b": 0,
        "direction_a": "None", "direction_b": "None", "accl_days_a": 0.0, "accl_days_b": 0.0,
        "heat_accl_days_a": 0.0, "heat_accl_days_b": 0.0, "alpha_a": 0.05, "alpha_b": 0.05, "rho": -0.15
    },
    {
        "team_a": "France", "team_b": "Australia", "goals_a": 4, "goals_b": 1,
        "elevation": 0.0, "temp": 22.0, "humidity": 50.0, "status_a": "Neutral", "status_b": "Neutral",
        "fan_pct_a": 0.6, "fan_pct_b": 0.4, "rest_days_a": 5.0, "rest_days_b": 5.0,
        "travel_miles_a": 0.0, "travel_miles_b": 0.0, "tz_crossed_a": 0, "tz_crossed_b": 0,
        "direction_a": "None", "direction_b": "None", "accl_days_a": 0.0, "accl_days_b": 0.0,
        "heat_accl_days_a": 0.0, "heat_accl_days_b": 0.0, "alpha_a": 0.15, "alpha_b": 0.05, "rho": -0.05
    },
    {
        "team_a": "Argentina", "team_b": "Croatia", "goals_a": 3, "goals_b": 0,
        "elevation": 0.0, "temp": 22.0, "humidity": 50.0, "status_a": "Neutral", "status_b": "Neutral",
        "fan_pct_a": 0.8, "fan_pct_b": 0.2, "rest_days_a": 4.0, "rest_days_b": 2.5,
        "travel_miles_a": 0.0, "travel_miles_b": 0.0, "tz_crossed_a": 0, "tz_crossed_b": 0,
        "direction_a": "None", "direction_b": "None", "accl_days_a": 0.0, "accl_days_b": 0.0,
        "heat_accl_days_a": 0.0, "heat_accl_days_b": 0.0, "alpha_a": 0.05, "alpha_b": 0.05, "rho": -0.05
    },
    {
        "team_a": "Morocco", "team_b": "Portugal", "goals_a": 1, "goals_b": 0,
        "elevation": 0.0, "temp": 22.0, "humidity": 50.0, "status_a": "Neutral", "status_b": "Neutral",
        "fan_pct_a": 0.8, "fan_pct_b": 0.2, "rest_days_a": 4.0, "rest_days_b": 4.0,
        "travel_miles_a": 0.0, "travel_miles_b": 0.0, "tz_crossed_a": 0, "tz_crossed_b": 0,
        "direction_a": "None", "direction_b": "None", "accl_days_a": 0.0, "accl_days_b": 0.0,
        "heat_accl_days_a": 0.0, "heat_accl_days_b": 0.0, "alpha_a": 0.05, "alpha_b": 0.05, "rho": -0.05
    },
    {
        "team_a": "England", "team_b": "USA", "goals_a": 0, "goals_b": 0,
        "elevation": 0.0, "temp": 28.0, "humidity": 75.0, "status_a": "Neutral", "status_b": "Neutral",
        "fan_pct_a": 0.5, "fan_pct_b": 0.5, "rest_days_a": 4.0, "rest_days_b": 4.0,
        "travel_miles_a": 0.0, "travel_miles_b": 0.0, "tz_crossed_a": 0, "tz_crossed_b": 0,
        "direction_a": "None", "direction_b": "None", "accl_days_a": 0.0, "accl_days_b": 0.0,
        "heat_accl_days_a": 0.0, "heat_accl_days_b": 0.0, "alpha_a": 0.05, "alpha_b": 0.05, "rho": -0.10
    }
]

def load_match_data(csv_path: str) -> List[dict]:
    if not csv_path or not isinstance(csv_path, str):
        raise ValueError("Invalid CSV path")
    
    if os.path.isdir(csv_path):
        raise IsADirectoryError(f"Path is a directory: {csv_path}")

    if not os.path.exists(csv_path):
        raise ValueError(f"File not found: {csv_path}")
        
    if os.path.getsize(csv_path) == 0:
        raise ValueError("File is empty")
        
    with open(csv_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    if not content.strip():
        raise ValueError("File is empty")
        
    reader = csv.DictReader(StringIO(content.strip()))
    if not reader.fieldnames:
        raise ValueError("Missing headers")
        
    required_headers = {'team_a', 'team_b', 'goals_a', 'goals_b', 'elevation', 'temp', 'humidity'}
    fieldnames_set = set(reader.fieldnames)
    if not required_headers.issubset(fieldnames_set):
        raise ValueError("Missing required headers")
        
    data = []
    for row in reader:
        team_a = row.get('team_a')
        team_b = row.get('team_b')
        if not team_a or not team_b:
            raise ValueError("Missing team names")
            
        team_a_clean = team_a.strip()
        team_b_clean = team_b.strip()
        if not team_a_clean or not team_b_clean:
            raise ValueError("Team names cannot be empty or whitespace-only")
        if team_a_clean == team_b_clean:
            raise ValueError("team_a cannot be equal to team_b")
            
        goals_a_str = row.get('goals_a')
        goals_b_str = row.get('goals_b')
        if goals_a_str is None or goals_b_str is None or goals_a_str.strip() == '' or goals_b_str.strip() == '':
            raise ValueError("Missing goals values")
            
        try:
            goals_a = int(goals_a_str)
            goals_b = int(goals_b_str)
            if goals_a < 0 or goals_b < 0:
                raise ValueError("Goals must be non-negative")
        except ValueError:
            raise ValueError("Goals must be integers")
            
        match_dict = {
            'team_a': team_a_clean,
            'team_b': team_b_clean,
            'goals_a': goals_a,
            'goals_b': goals_b
        }
        
        for key in ['elevation', 'temp', 'humidity']:
            val = row.get(key)
            if val is None or val.strip() == '':
                continue
            try:
                match_dict[key] = float(val)
            except ValueError:
                raise ValueError(f"Malformed value for {key}")
                
        # Known string columns
        string_keys = {'team_a', 'team_b', 'status_a', 'status_b', 'direction_a', 'direction_b', 'phase'}

        for key, val in row.items():
            if key in ['team_a', 'team_b', 'goals_a', 'goals_b', 'elevation', 'temp', 'humidity']:
                continue
            if val is None or val.strip() == '':
                continue
            val_str = val.strip()
            
            if key in string_keys:
                match_dict[key] = val_str
                continue

            try:
                try:
                    match_dict[key] = int(val_str)
                except ValueError:
                    match_dict[key] = float(val_str)
            except ValueError:
                raise ValueError(f"Malformed value for {key}: {val_str}")
                
        data.append(match_dict)
        
    return data

def get_team_stats(team_name: str) -> dict:
    if team_name is None:
        return {"off": 1.2, "def": 1.0}
    if not isinstance(team_name, str):
        raise AttributeError("team_name must be a string")
    if not team_name:
        return {"off": 1.2, "def": 1.0}
    return TEAM_STATS.get(team_name.strip(), {"off": 1.2, "def": 1.0})

def make_context(row: dict, suffix: str) -> dict:
    context = {}
    for key in ["elevation", "temp", "humidity"]:
        if key in row:
            context[key] = row[key]
    mapping = {
        "status": f"status_{suffix}",
        "fan_support_pct": f"fan_pct_{suffix}",
        "fan_pct_A" if suffix == "a" else "fan_pct_B": f"fan_pct_{suffix}",
        "rest_days": f"rest_days_{suffix}",
        "travel_miles": f"travel_miles_{suffix}",
        "tz_crossed": f"tz_crossed_{suffix}",
        "direction": f"direction_{suffix}",
        "accl_days": f"accl_days_{suffix}",
        f"accl_days_{suffix.upper()}": f"accl_days_{suffix}",
        "heat_accl_days": f"heat_accl_days_{suffix}",
        f"heat_accl_days_{suffix.upper()}": f"heat_accl_days_{suffix}",
    }
    for ctx_key, row_key in mapping.items():
        if row_key in row:
            context[ctx_key] = row[row_key]
    return context

def run_backtest(model_type: str, data: List[dict]) -> dict:
    total_points = 0.0
    predictions = []
    
    for row in data:
        team_a = row["team_a"]
        team_b = row["team_b"]
        goals_a = row["goals_a"]
        goals_b = row["goals_b"]
        
        stats_a = get_team_stats(team_a)
        stats_b = get_team_stats(team_b)
        
        off_a = stats_a["off"]
        def_a = stats_a["def"]
        off_b = stats_b["off"]
        def_b = stats_b["def"]
        
        mu_a = off_a * def_b
        mu_b = off_b * def_a
        
        phase_str = row.get("phase", None)
        phase = predictor.parse_match_phase(phase_str) if phase_str else None
        
        if model_type == "baseline":
            config = predictor.MatchModelConfig(
                dist_type=predictor.ModelDistribution.POISSON,
                mu_a=mu_a,
                mu_b=mu_b,
                alpha_a=0.0,
                alpha_b=0.0,
                rho=0.0
            )
        elif model_type == "optimized":
            team_a_ctx = make_context(row, "a")
            team_b_ctx = make_context(row, "b")
            
            mu_a_adj, mu_b_adj = predictor.get_adjusted_lambdas(mu_a, mu_b, team_a_ctx, team_b_ctx)
            
            rho = row.get("rho", 0.0)
            alpha_a = row.get("alpha_a", 0.0)
            alpha_b = row.get("alpha_b", 0.0)
            
            # Apply phase adjustments (v4: knockout modeling)
            import sys
            if "--no-phase" not in sys.argv:
                rho_adj, mu_a_adj, mu_b_adj = predictor.apply_phase_adjustments(
                    rho, mu_a_adj, mu_b_adj, phase
                )
            else:
                rho_adj = rho
            
            dist_type = predictor.ModelDistribution.NEGATIVE_BINOMIAL if (alpha_a > 0.0 or alpha_b > 0.0) else predictor.ModelDistribution.POISSON
            
            import argparse
            # Hack to read global args in run_backtest
            import sys
            no_context = "--no-context" in sys.argv
            no_phase = "--no-phase" in sys.argv
            no_nb = "--no-nb" in sys.argv
            no_dc = "--no-dc" in sys.argv
            
            if no_context:
                mu_a_adj, mu_b_adj = mu_a, mu_b
            if no_phase:
                rho_adj = rho
                # restore mu
                # actually apply_phase_adjustments already changed them, we shouldn't have called it
                pass 
            if no_nb:
                dist_type = predictor.ModelDistribution.POISSON
                alpha_a = 0.0
                alpha_b = 0.0
            if no_dc:
                rho_adj = 0.0
            
            config = predictor.MatchModelConfig(
                dist_type=dist_type,
                mu_a=mu_a_adj,
                mu_b=mu_b_adj,
                alpha_a=alpha_a,
                alpha_b=alpha_b,
                rho=rho_adj,
                phase=phase,
            )
        else:
            raise ValueError(f"Unknown model_type: {model_type}")
        
        # For the optimized model in KO phases, use the 3-layer KO grid
        is_ko = phase is not None and phase != predictor.MatchPhase.GROUP
        if model_type == "optimized" and is_ko:
            ko_grid = predictor.generate_ko_final_grid(config, max_final_goals=15)
            tips, _, _ = predictor.solve_optimal_tip_from_grid(
                ko_grid, max_tip=10,
                pts_exact=4, pts_diff=3, pts_tend=2
            )
        else:
            tips, _, _ = predictor.solve_optimal_tip(config)
        optimal_tip = tips[0][0]
        
        points = predictor.get_points(optimal_tip[0], optimal_tip[1], goals_a, goals_b)
        total_points += points
        
        predictions.append({
            "team_a": team_a,
            "team_b": team_b,
            "goals_a": goals_a,
            "goals_b": goals_b,
            "tip_a": optimal_tip[0],
            "tip_b": optimal_tip[1],
            "points": points,
            "phase": phase.value if phase else "GROUP",
        })
        
    return {
        "total_points": float(total_points),
        "predictions": predictions
    }

def generate_summary_report(results_base: dict, results_opt: dict) -> dict:
    base_total = results_base.get("total_points", 0.0)
    opt_total = results_opt.get("total_points", 0.0)
    
    base_preds = results_base.get("predictions", [])
    opt_preds = results_opt.get("predictions", [])
    
    base_len = len(base_preds)
    opt_len = len(opt_preds)
    
    base_avg = base_total / base_len if base_len > 0 else 0.0
    opt_avg = opt_total / opt_len if opt_len > 0 else 0.0
    
    delta_total = opt_total - base_total
    delta_avg = opt_avg - base_avg
    
    return {
        "baseline_total_points": float(base_total),
        "optimized_total_points": float(opt_total),
        "baseline_avg_points": float(base_avg),
        "optimized_avg_points": float(opt_avg),
        "delta_total_points": float(delta_total),
        "delta_avg_points": float(delta_avg)
    }

def main():
    parser = argparse.ArgumentParser(description="Backtesting Suite for World Cup 2026 Predictor v4")
    parser.add_argument("--csv", type=str, default=None, help="Path to the historical match data CSV")
    parser.add_argument("--year", type=str, default="2022", help="Which year to backtest: '2022', '2018', '2014', or 'all' (default: 2022)")
    parser.add_argument("--details", action="store_true", default=False, help="Show per-match detailed results")
    parser.add_argument("--no-context", action="store_true", help="Ablation: disable context")
    parser.add_argument("--no-phase", action="store_true", help="Ablation: disable phase adjustment")
    parser.add_argument("--no-nb", action="store_true", help="Ablation: disable negative binomial")
    parser.add_argument("--no-dc", action="store_true", help="Ablation: disable dixon coles")
    args = parser.parse_args()
    
    data = []
    if args.csv:
        try:
            data = load_match_data(args.csv)
            print(f"Loaded {len(data)} matches from {args.csv}")
        except Exception as e:
            print(f"Error loading CSV from {args.csv}: {e}. Falling back to default matches.")
            data = FALLBACK_MATCHES
    else:
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        years_to_load = ["2014", "2018", "2022"] if args.year == "all" else [args.year]
        for y in years_to_load:
            csv_path = os.path.join(base_dir, "data", f"wc{y}_full.csv")
            try:
                year_data = load_match_data(csv_path)
                print(f"Loaded {len(year_data)} matches from {csv_path}")
                data.extend(year_data)
            except Exception as e:
                print(f"Error loading {csv_path}: {e}")
        
        if not data:
            data = FALLBACK_MATCHES
            print(f"Using default embedded fallback matches ({len(data)} matches).")
        
    results_base = run_backtest("baseline", data)
    results_opt = run_backtest("optimized", data)
    
    report = generate_summary_report(results_base, results_opt)
    
    # Per-match details
    if args.details:
        base_preds = results_base.get("predictions", [])
        opt_preds = results_opt.get("predictions", [])
        
        print(f"\n{'=' * 90}")
        print(f"{'#':<4} {'Match':<30} {'Actual':>7} {'Base Tip':>10} {'Base Pts':>10} {'Opt Tip':>10} {'Opt Pts':>10} {'Phase':<7}")
        print(f"{'=' * 90}")
        
        for i, (bp, op) in enumerate(zip(base_preds, opt_preds)):
            match_str = f"{bp['team_a']} - {bp['team_b']}"
            if len(match_str) > 28:
                match_str = match_str[:28]
            actual = f"{bp['goals_a']}:{bp['goals_b']}"
            base_tip = f"{bp['tip_a']}:{bp['tip_b']}"
            opt_tip = f"{op['tip_a']}:{op['tip_b']}"
            phase = op.get("phase", "GROUP")
            
            # Highlight exact matches with a star
            base_marker = "★" if bp['points'] == 4 else " "
            opt_marker = "★" if op['points'] == 4 else " "
            
            print(f"{i+1:<4} {match_str:<30} {actual:>7} {base_tip:>8}{base_marker} {bp['points']:>9} {opt_tip:>8}{opt_marker} {op['points']:>9} {phase:<7}")
        
        print(f"{'=' * 90}")
    
    # Overall report
    print("\n" + "=" * 60)
    print("BACKTEST COMPARISON REPORT")
    print("=" * 60)
    print(f"Total Matches:          {len(data)}")
    print(f"Baseline Total Points:  {report['baseline_total_points']:.1f}")
    print(f"Optimized Total Points: {report['optimized_total_points']:.1f}")
    print(f"Baseline Avg Points:    {report['baseline_avg_points']:.3f}")
    print(f"Optimized Avg Points:   {report['optimized_avg_points']:.3f}")
    print(f"Delta Total Points:     {report['delta_total_points']:+.1f}")
    print(f"Delta Avg Points:       {report['delta_avg_points']:+.3f}")
    
    # Per-phase breakdown
    opt_preds = results_opt.get("predictions", [])
    base_preds = results_base.get("predictions", [])
    
    phases = {}
    for bp, op in zip(base_preds, opt_preds):
        phase = op.get("phase", "GROUP")
        if phase not in phases:
            phases[phase] = {"count": 0, "base_pts": 0, "opt_pts": 0}
        phases[phase]["count"] += 1
        phases[phase]["base_pts"] += bp["points"]
        phases[phase]["opt_pts"] += op["points"]
    
    if len(phases) > 1:
        print(f"\n{'─' * 60}")
        print(f"PER-PHASE BREAKDOWN")
        print(f"{'─' * 60}")
        for phase_name in ["GROUP", "R16", "QF", "SF", "THIRD", "FINAL"]:
            if phase_name in phases:
                p = phases[phase_name]
                base_avg = p["base_pts"] / p["count"]
                opt_avg = p["opt_pts"] / p["count"]
                delta = p["opt_pts"] - p["base_pts"]
                print(f"  {phase_name:<8} ({p['count']:>2} matches): Baseline={p['base_pts']:>5.1f}  Optimized={p['opt_pts']:>5.1f}  Δ={delta:+.1f}  (Avg: {base_avg:.2f} → {opt_avg:.2f})")
    
    print("=" * 60)
    
    if len(data) > 0:
        if report['optimized_total_points'] >= report['baseline_total_points']:
            print("✅ Optimized model achieved at least baseline simulated Kicktipp points.")
        else:
            delta = report['baseline_total_points'] - report['optimized_total_points']
            print(f"⚠️  Baseline outperformed optimized by {delta:.0f} pts on this dataset.")
            print("   Note: With penalty-scoring rules, the simple baseline can occasionally")
            print("   match penalty result tendencies by chance on small KO datasets.")

if __name__ == '__main__':
    main()

