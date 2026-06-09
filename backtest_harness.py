# backtest_harness.py — Phase 7: Point-in-Time Walk-Forward Backtesting Harness
import os
import sys
import json
import csv
import math
import argparse
import numpy as np
from datetime import datetime

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import predictor
from predictor import MatchModelConfig, ModelDistribution, MatchPhase
import tournament_bonusfragen as tb
from backtest_wm2014 import PRE_WM2014_ELO
from backtest_wm2018 import PRE_WM2018_ELO
from backtest_wm2022 import PRE_WM2022_ELO
try:
    from squad_data import SQUAD_VALUES
except ImportError:
    SQUAD_VALUES = {}

def went_to_extra_time_real(team_a: str, team_b: str, phase: str, year: int) -> bool:
    """Hardcoded lookup of actual World Cup matches that went to Extra Time/Penalties."""
    if year == 2022:
        et_matches = {
            frozenset(["Japan", "Croatia"]),         # R16
            frozenset(["Morocco", "Spain"]),         # R16
            frozenset(["Croatia", "Brazil"]),        # QF
            frozenset(["Netherlands", "Argentina"]),  # QF
            frozenset(["Argentina", "France"])       # Final
        }
    elif year == 2018:
        et_matches = {
            frozenset(["Spain", "Russia"]),          # R16
            frozenset(["Croatia", "Denmark"]),       # R16
            frozenset(["Colombia", "England"]),      # R16
            frozenset(["Russia", "Croatia"]),        # QF
            frozenset(["Croatia", "England"])        # SF
        }
    elif year == 2014:
        et_matches = {
            frozenset(["Brazil", "Chile"]),          # R16
            frozenset(["Costa Rica", "Greece"]),     # R16
            frozenset(["Germany", "Algeria"]),       # R16
            frozenset(["Argentina", "Switzerland"]),  # R16
            frozenset(["Belgium", "USA"]),           # R16
            frozenset(["Netherlands", "Costa Rica"]),# QF
            frozenset(["Argentina", "Netherlands"]), # SF
            frozenset(["Germany", "Argentina"])      # Final
        }
    else:
        et_matches = set()
    return phase != "GROUP" and frozenset([team_a, team_b]) in et_matches

def load_match_data(csv_path: str) -> list:
    data = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            match_dict = {
                "team_a": row["team_a"].strip(),
                "team_b": row["team_b"].strip(),
                "goals_a": int(row["goals_a"]),
                "goals_b": int(row["goals_b"]),
                "elevation": float(row.get("elevation", 0.0)),
                "temp": float(row.get("temp", 22.0)),
                "humidity": float(row.get("humidity", 50.0)),
                "phase": row.get("phase", "GROUP").strip()
            }
            # Add other contextual columns if present
            for k, v in row.items():
                if k not in match_dict and v.strip() != '':
                    try:
                        match_dict[k] = float(v)
                    except ValueError:
                        match_dict[k] = v.strip()
            data.append(match_dict)
    return data

class BacktestHarness:
    def __init__(self, csv_path: str, year: int = 2022, edge_threshold: float = 0.015, kelly_fraction: float = 0.25):
        self.csv_path = csv_path
        self.year = year
        self.edge_threshold = edge_threshold
        self.kelly_fraction = kelly_fraction
        
        if year == 2014:
            self.elo_table = PRE_WM2014_ELO
        elif year == 2018:
            self.elo_table = PRE_WM2018_ELO
        else:
            self.elo_table = PRE_WM2022_ELO
            
        # Inject pre-tournament Elos to prevent look-ahead bias
        self.original_teams = {t: dict(v) for t, v in predictor.WORLD_CUP_2026_TEAMS.items()}
        predictor.WORLD_CUP_2026_TEAMS.clear()
        for team, data in self.elo_table.items():
            predictor.WORLD_CUP_2026_TEAMS[team] = data
            
        self.matches = load_match_data(csv_path)
        self.fatigue_status = {t: False for t in self.elo_table}
        
    def calculate_kelly_stake(self, prob_model: float, decimal_odds: float) -> float:
        b = decimal_odds - 1.0
        q = 1.0 - prob_model
        if b <= 0: return 0.0
        kelly_pct = (b * prob_model - q) / b
        return max(0.0, kelly_pct * self.kelly_fraction)
        
    def run_backtest(self):
        bankroll = 100000.0
        initial_bankroll = bankroll
        equity_curve = [bankroll]
        returns = []
        
        bets_placed = 0
        bets_won = 0
        
        brier_base_all = []
        brier_opt_all = []
        brier_base_crucible = []
        brier_opt_crucible = []
        
        base_pen = predictor.CONSTANTS["pen_conversion_rate"]
        
        print("\n" + "="*115)
        print(f"🏃 STARTING WALK-FORWARD BACKTEST ON WORLD CUP {self.year} (Synthetic Elo Market vs Apex Model)")
        print("="*115)
        print(f"{'Match':<30} | {'Phase':<6} | {'Market Odds (Vig)':<20} | {'Model Prob':<12} | {'Actioned Bet':<15} | {'Result':<6} | {'P&L ($)':<9} | {'Bankroll ($)':<10}")
        print("-" * 115)
        
        for idx, row in enumerate(self.matches):
            team_a, team_b = row["team_a"], row["team_b"]
            goals_a, goals_b = row["goals_a"], row["goals_b"]
            phase_str = row["phase"]
            phase = predictor.parse_match_phase(phase_str)
            is_ko = phase != MatchPhase.GROUP
            
            # --- 1. Synthetic Market Odds (Vanilla Elo, No Context, No Fatigue) ---
            elo_a = self.elo_table.get(team_a, {}).get("elo", 1500)
            elo_b = self.elo_table.get(team_b, {}).get("elo", 1500)
            
            la_base, lb_base = predictor.estimate_base_lambdas_from_elo(team_a, team_b, elo_a, elo_b)
            config_base = MatchModelConfig(
                dist_type=ModelDistribution.POISSON,
                mu_a=la_base, mu_b=lb_base, rho=-0.05,
                max_goals=14, phase=phase
            )
            
            if is_ko:
                grid_base = predictor.generate_ko_final_grid(config_base, max_final_goals=14, pen_conv_a=base_pen, pen_conv_b=base_pen)
            else:
                grid_base = predictor.generate_joint_grid(config_base)
                
            # Extract baseline probabilities
            if is_ko:
                p_adv_a_base = sum(predictor.get_grid_val(grid_base, ga, gb) for ga in range(15) for gb in range(15) if ga > gb)
                p_adv_b_base = 1.0 - p_adv_a_base
                # Add 5% overround to baseline to generate bookie decimal odds
                odds_a = round(1.0 / (p_adv_a_base * 1.05), 2)
                odds_b = round(1.0 / (p_adv_b_base * 1.05), 2)
            else:
                p_win_base = sum(predictor.get_grid_val(grid_base, ga, gb) for ga in range(15) for gb in range(15) if ga > gb)
                p_draw_base = sum(predictor.get_grid_val(grid_base, g, g) for g in range(15))
                p_lose_base = 1.0 - p_win_base - p_draw_base
                # Add 5% overround
                odds_home = round(1.0 / (p_win_base * 1.05), 2)
                odds_draw = round(1.0 / (p_draw_base * 1.05), 2)
                odds_away = round(1.0 / (p_lose_base * 1.05), 2)
                
            # --- 2. Apex Model Expected Goals (Context + Carry-Over Fatigue) ---
            # Get context adjustments via predict_single_match
            res = predictor.predict_single_match(row)
            la_adj = res["lambda_a_adj"]
            lb_adj = res["lambda_b_adj"]
            
            # Apply dynamic depth-fatigue carry-over
            fat_a = self.fatigue_status.get(team_a, False)
            fat_b = self.fatigue_status.get(team_b, False)
            
            val_a = SQUAD_VALUES.get(predictor.validate_team_name(team_a), {"xi": 100.0, "bench": 50.0})
            val_b = SQUAD_VALUES.get(predictor.validate_team_name(team_b), {"xi": 100.0, "bench": 50.0})
            bench_a = val_a.get("bench", 50.0)
            bench_b = val_b.get("bench", 50.0)
            
            base_fat = 0.10
            avg_bench = 50.0
            
            res_a = min(2.0, bench_a / avg_bench)
            penalty_a = base_fat / max(1.0, res_a)
            att_a, def_a = 1.0 - penalty_a, 1.0 + penalty_a
            
            res_b = min(2.0, bench_b / avg_bench)
            penalty_b = base_fat / max(1.0, res_b)
            att_b, def_b = 1.0 - penalty_b, 1.0 + penalty_b
            
            if fat_a:
                la_adj *= att_a
                lb_adj *= def_a
            if fat_b:
                la_adj *= def_b
                lb_adj *= att_b
                
            # Generate advanced grid
            config_opt = MatchModelConfig(
                dist_type=ModelDistribution.POISSON,
                mu_a=la_adj, mu_b=lb_adj, rho=-0.05,
                max_goals=14, phase=phase
            )
            
            pen_a = base_pen * predictor.PENALTY_STRENGTH.get(predictor.validate_team_name(team_a), 1.0)
            pen_b = base_pen * predictor.PENALTY_STRENGTH.get(predictor.validate_team_name(team_b), 1.0)
            
            if is_ko:
                grid_opt = predictor.generate_ko_final_grid(config_opt, max_final_goals=14, pen_conv_a=pen_a, pen_conv_b=pen_b)
            else:
                grid_opt = predictor.generate_joint_grid(config_opt)
                
            # Extract advanced model probabilities
            if is_ko:
                p_adv_a_mod = sum(predictor.get_grid_val(grid_opt, ga, gb) for ga in range(15) for gb in range(15) if ga > gb)
                p_adv_b_mod = 1.0 - p_adv_a_mod
            else:
                p_win_mod = sum(predictor.get_grid_val(grid_opt, ga, gb) for ga in range(15) for gb in range(15) if ga > gb)
                p_draw_mod = sum(predictor.get_grid_val(grid_opt, g, g) for g in range(15))
                p_lose_mod = 1.0 - p_win_mod - p_draw_mod
                
            # --- 3. Brier Score Calculations ---
            # Group Stage binary outcomes
            if not is_ko:
                y_home = 1.0 if goals_a > goals_b else 0.0
                y_draw = 1.0 if goals_a == goals_b else 0.0
                y_away = 1.0 if goals_a < goals_b else 0.0
                
                bs_base = (p_win_base - y_home)**2 + (p_draw_base - y_draw)**2 + (p_lose_base - y_away)**2
                bs_opt = (p_win_mod - y_home)**2 + (p_draw_mod - y_draw)**2 + (p_lose_mod - y_away)**2
            else:
                # Knockout stage binary outcomes (no draws)
                y_a = 1.0 if goals_a > goals_b else 0.0
                y_b = 1.0 if goals_a < goals_b else 0.0
                
                bs_base = (p_adv_a_base - y_a)**2 + (p_adv_b_base - y_b)**2
                bs_opt = (p_adv_a_mod - y_a)**2 + (p_adv_b_mod - y_b)**2
                
            brier_base_all.append(bs_base)
            brier_opt_all.append(bs_opt)
            
            # Filter for extreme "crucible" matches (temp >= 27 WBGT equivalent or fatigue active)
            is_crucible = (row["temp"] >= 27.0) or fat_a or fat_b
            if is_crucible:
                brier_base_crucible.append(bs_base)
                brier_opt_crucible.append(bs_opt)
                
            # --- 4. Virtual Betting Decision (Fractional Kelly) ---
            best_bet = None
            best_ev = -1.0
            
            if is_ko:
                edge_a = p_adv_a_mod - (p_adv_a_base * 1.05)
                edge_b = p_adv_b_mod - (p_adv_b_base * 1.05)
                ev_a = p_adv_a_mod * odds_a - 1.0
                ev_b = p_adv_b_mod * odds_b - 1.0
                
                options = [
                    ("Advance A", odds_a, p_adv_a_mod, edge_a, ev_a),
                    ("Advance B", odds_b, p_adv_b_mod, edge_b, ev_b)
                ]
            else:
                edge_home = p_win_mod - (p_win_base * 1.05)
                edge_draw = p_draw_mod - (p_draw_base * 1.05)
                edge_away = p_lose_mod - (p_lose_base * 1.05)
                ev_home = p_win_mod * odds_home - 1.0
                ev_draw = p_draw_mod * odds_draw - 1.0
                ev_away = p_lose_mod * odds_away - 1.0
                
                options = [
                    ("Home", odds_home, p_win_mod, edge_home, ev_home),
                    ("Draw", odds_draw, p_draw_mod, edge_draw, ev_draw),
                    ("Away", odds_away, p_lose_mod, edge_away, ev_away)
                ]
                
            for name, odds, prob, edge, ev in options:
                if edge > self.edge_threshold and ev > 0:
                    if ev > best_ev:
                        best_ev = ev
                        best_bet = (name, odds, prob)
                        
            # Determine actual result outcome for grading
            # For Group: Home Win, Draw, Away Win. For KO: Advance A (ga > gb), Advance B (ga < gb).
            if is_ko:
                actual_result = "Advance A" if goals_a > goals_b else "Advance B"
            else:
                if goals_a > goals_b:
                    actual_result = "Home"
                elif goals_a == goals_b:
                    actual_result = "Draw"
                else:
                    actual_result = "Away"
                    
            p_and_l = 0.0
            bet_str = "-"
            rec_stake_pct = 0.0
            
            if best_bet:
                bet_name, bet_odds, bet_prob = best_bet
                rec_stake_pct = self.calculate_kelly_stake(bet_prob, bet_odds)
                stake_amount = rec_stake_pct * bankroll
                
                bets_placed += 1
                is_win = bet_name == actual_result
                if is_win:
                    bets_won += 1
                    p_and_l = stake_amount * (bet_odds - 1.0)
                    result_icon = "W"
                else:
                    p_and_l = -stake_amount
                    result_icon = "L"
                    
                bankroll += p_and_l
                returns.append(p_and_l / (bankroll - p_and_l)) # Return relative to start of match bankroll
                bet_str = f"{bet_name} ({bet_odds:.2f})"
                result_str = f"{result_icon} ({goals_a}:{goals_b})"
            else:
                result_str = f"({goals_a}:{goals_b})"
                
            equity_curve.append(bankroll)
            
            # Print row
            match_name = f"{team_a} vs {team_b}"
            if len(match_name) > 28:
                match_name = match_name[:28]
                
            mkt_str = f"H:{odds_home:.2f}/D:{odds_draw:.2f}/A:{odds_away:.2f}" if not is_ko else f"A:{odds_a:.2f}/B:{odds_b:.2f}"
            prob_str = f"{p_win_mod*100:>4.1f}%" if not is_ko else f"A:{p_adv_a_mod*100:>4.1f}%"
            
            print(f"{match_name:<30} | {phase_str:<6} | {mkt_str:<20} | {prob_str:<12} | {bet_str:<15} | {result_str:<6} | {p_and_l:>+9.2f} | {bankroll:>10.2f}")
            
            # --- 5. State Collapse & Fatigue Carry-Over ---
            # Reset current fatigue for these teams (they are out of the round)
            self.fatigue_status[team_a] = False
            self.fatigue_status[team_b] = False
            
            # If the match went to ET in real life, mark them fatigued for subsequent matches
            if went_to_extra_time_real(team_a, team_b, phase_str, self.year):
                self.fatigue_status[team_a] = True
                self.fatigue_status[team_b] = True
                
        # --- 6. Post-Backtest Metrics Aggregation ---
        final_roi = (bankroll - initial_bankroll) / initial_bankroll * 100.0
        
        # Max Drawdown
        peak = equity_curve[0]
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd
                
        # Sharpe Ratio
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns)
        else:
            sharpe = 0.0
            
        win_rate = (bets_won / bets_placed * 100.0) if bets_placed > 0 else 0.0
        
        # Brier Averages
        avg_brier_base_all = np.mean(brier_base_all)
        avg_brier_opt_all = np.mean(brier_opt_all)
        brier_skill_all = 1.0 - (avg_brier_opt_all / avg_brier_base_all)
        
        avg_brier_base_crucible = np.mean(brier_base_crucible) if brier_base_crucible else 0.0
        avg_brier_opt_crucible = np.mean(brier_opt_crucible) if brier_opt_crucible else 0.0
        brier_skill_crucible = 1.0 - (avg_brier_opt_crucible / avg_brier_base_crucible) if avg_brier_base_crucible > 0 else 0.0
        
        print("="*115)
        print("\n" + "="*50)
        print(f"📊 INSTITUTIONAL BACKTEST REPORT CARD (WC {self.year})")
        print("="*50)
        print(f"Initial Bankroll      : ${initial_bankroll:,.2f}")
        print(f"Final Bankroll        : ${bankroll:,.2f}")
        print(f"Cumulative Yield (ROI): {final_roi:+.2f}%")
        print(f"Total Bets Placed     : {bets_placed}  (Wins: {bets_won} | Win Rate: {win_rate:.1f}%)")
        print(f"Sharpe Ratio (per bet): {sharpe:.3f}")
        print(f"Maximum Drawdown      : {max_dd*100:.2f}%")
        print("-" * 50)
        print(f"Brier Score (All Matches):")
        print(f"  Vanilla Elo Baseline : {avg_brier_base_all:.4f}")
        print(f"  Apex Physics Engine  : {avg_brier_opt_all:.4f}")
        print(f"  Brier Skill Score    : {brier_skill_all:+.2%}")
        print("-" * 50)
        print(f"Brier Score (Extreme Crucible Matches - Temp/Fatigue):")
        print(f"  Vanilla Elo Baseline : {avg_brier_base_crucible:.4f}")
        print(f"  Apex Physics Engine  : {avg_brier_opt_crucible:.4f}")
        print(f"  Brier Skill Score    : {brier_skill_crucible:+.2%}")
        print("="*50)
        
        # Restore original engine state
        predictor.WORLD_CUP_2026_TEAMS.clear()
        for team, data in self.original_teams.items():
            predictor.WORLD_CUP_2026_TEAMS[team] = data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Point-in-Time Kelly Backtest Harness")
    parser.add_argument("--tournament", type=int, default=2022, choices=[2014, 2018, 2022], help="World Cup tournament year (2014, 2018, or 2022)")
    parser.add_argument("--threshold", type=float, default=0.015, help="Minimum probability edge to trigger alert")
    parser.add_argument("--kelly", type=float, default=0.25, help="Fractional Kelly multiplier")
    args = parser.parse_args()
    
    csv_filename = f"wc{args.tournament}_full.csv"
    csv_path = os.path.join(project_root, "data", csv_filename)
    harness = BacktestHarness(csv_path=csv_path, year=args.tournament, edge_threshold=args.threshold, kelly_fraction=args.kelly)
    harness.run_backtest()
