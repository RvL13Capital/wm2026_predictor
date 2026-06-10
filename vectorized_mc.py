#!/usr/bin/env python3
# vectorized_mc.py — High-Performance Vectorized FIFA World Cup 2026 Monte Carlo Engine
import os
import sys
import time
import argparse
import json
import math
import copy
import numpy as np
from collections import Counter, OrderedDict
from typing import Tuple

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Suppress OpenBLAS warnings locally to keep stdout clean
os.environ["OPENBLAS_CORETYPE"] = "HASWELL"

import predictor
from predictor import MatchModelConfig, ModelDistribution, MatchPhase
import tournament_bonusfragen as tb

DTYPE_INT = np.int8
DTYPE_FLOAT = np.float32

# Map phase index to Enum
PHASE_MAP = [
    MatchPhase.R32, MatchPhase.R16, MatchPhase.QUARTER,
    MatchPhase.SEMI, MatchPhase.THIRD, MatchPhase.FINAL
]

def get_phase_idx(m_id: str) -> int:
    n = int(m_id[1:])
    if n <= 88: return 0  # R32
    if n <= 96: return 1  # R16
    if n <= 100: return 2 # QF
    if n <= 102: return 3 # SF
    if n == 103: return 4 # Third
    return 5              # Final

def solve_third_assignment(qualified_groups):
    """Backtracking solver to map 3rd-place qualifying groups to slot assignments."""
    slot_order = ["M75", "M77", "M79", "M80", "M81", "M82", "M85", "M88"]
    def _solve(idx, used, assignment):
        if idx == len(slot_order):
            return assignment.copy()
        slot = slot_order[idx]
        pool = tb.THIRD_PLACE_POOLS[slot]
        for g in pool:
            if g in qualified_groups and g not in used:
                assignment[slot] = g
                used.add(g)
                result = _solve(idx + 1, used, assignment)
                if result is not None:
                    return result
                    
                used.discard(g)
                del assignment[slot]
        return None

    assignment = _solve(0, set(), {})
    if assignment is None:
        # Fallback
        assignment = {}
        used_groups = set()
        for slot in slot_order:
            pool = tb.THIRD_PLACE_POOLS[slot]
            available = [g for g in pool if g in qualified_groups and g not in used_groups]
            if available:
                chosen = available[0]
                assignment[slot] = chosen
                used_groups.add(chosen)
            else:
                assignment[slot] = "A"
    return assignment

class MatrixPrecomputer:
    """Precomputes all exact Dixon-Coles grids and routing maps for O(1) L3 Cache lookups."""
    def __init__(self, host_teams=None, market_probs=None):
        self.group_names = sorted(list(tb.GROUPS.keys()))
        self.teams = []
        for g in self.group_names:
            for t in tb.GROUPS[g]:
                self.teams.append(t)
                
        self.N_TEAMS = len(self.teams)
        self.team_to_id = {t: i for i, t in enumerate(self.teams)}
        self.id_to_team = {i: t for i, t in enumerate(self.teams)}
        
        self.base_elos = np.zeros(self.N_TEAMS, dtype=DTYPE_FLOAT)
        self.lam_a = np.zeros((self.N_TEAMS, self.N_TEAMS), dtype=DTYPE_FLOAT)
        self.lam_b = np.zeros((self.N_TEAMS, self.N_TEAMS), dtype=DTYPE_FLOAT)
        
        self._build_baseline_tensors(host_teams, market_probs)
        
        self.ko_cdfs = np.zeros((6, 4, self.N_TEAMS, self.N_TEAMS, 225), dtype=DTYPE_FLOAT)
        self.ko_et_probs = np.zeros((6, 4, self.N_TEAMS, self.N_TEAMS, 225), dtype=DTYPE_FLOAT)
        self._build_knockout_matrix(host_teams)
        
        self.routing_table = np.zeros((4096, 8), dtype=DTYPE_INT)
        self.slot_keys = ["M75", "M77", "M79", "M80", "M81", "M82", "M85", "M88"]
        self._build_3rd_place_routing_table()
        
    def _build_baseline_tensors(self, host_teams, market_probs):
        self.group_cdfs = np.zeros((72, 4, 225), dtype=DTYPE_FLOAT)
        
        # Determine exact group match scheduling
        self.GROUP_MATCHES = []
        for g_idx, g_name in enumerate(self.group_names):
            t0, t1, t2, t3 = [self.team_to_id[t] for t in tb.GROUPS[g_name]]
            self.GROUP_MATCHES.extend([
                (t0, t1, g_idx, 1), (t2, t3, g_idx, 1), # MD1
                (t0, t2, g_idx, 2), (t3, t1, g_idx, 2), # MD2
                (t3, t0, g_idx, 3), (t1, t2, g_idx, 3)  # MD3
            ])
            
        import schedule_context
        group_contexts, _ = schedule_context.get_group_match_contexts()
            
        for i, t_a in enumerate(self.teams):
            elo_a = predictor.WORLD_CUP_2026_TEAMS.get(predictor.validate_team_name(t_a), {}).get("elo", 1700)
            self.base_elos[i] = elo_a
            
            for j, t_b in enumerate(self.teams):
                if i == j: continue
                elo_b = predictor.WORLD_CUP_2026_TEAMS.get(predictor.validate_team_name(t_b), {}).get("elo", 1700)
                la_base, lb_base = predictor.estimate_base_lambdas_from_elo(t_a, t_b, elo_a, elo_b)
                
                ctx_a = {"team_name": t_a}
                ctx_b = {"team_name": t_b}
                if host_teams:
                    if t_a in host_teams:
                        ctx_a["status"] = "True Home"
                        ctx_a["fan_support_pct"] = 0.70
                        ctx_b["fan_support_pct"] = 0.30
                    elif t_b in host_teams:
                        ctx_b["status"] = "True Home"
                        ctx_b["fan_support_pct"] = 0.70
                        ctx_a["fan_support_pct"] = 0.30
                
                la_adj, lb_adj = predictor.get_adjusted_lambdas(la_base, lb_base, ctx_a, ctx_b)
                self.lam_a[i, j] = la_adj
                self.lam_b[i, j] = lb_adj

        for m_idx, (t_a, t_b, _, md) in enumerate(self.GROUP_MATCHES):
            team_a = self.id_to_team[t_a]
            team_b = self.id_to_team[t_b]
            
            # Setup row context for group match
            row = {
                "team_a": team_a,
                "team_b": team_b,
                "phase": "GROUP"
            }
            
            # Inject schedule context (rest, travel, tz)
            ctx = group_contexts.get((team_a, team_b))
            if not ctx:
                ctx = group_contexts.get((team_b, team_a))
                if ctx:
                    row["rest_days_a"] = str(ctx["rest_days_b"])
                    row["rest_days_b"] = str(ctx["rest_days_a"])
                    row["travel_miles_a"] = str(ctx["travel_miles_b"])
                    row["travel_miles_b"] = str(ctx["travel_miles_a"])
                    row["tz_crossed_a"] = str(ctx["tz_crossed_b"])
                    row["tz_crossed_b"] = str(ctx["tz_crossed_a"])
            if ctx and "rest_days_a" not in row:
                for k, v in ctx.items():
                    row[k] = str(v)
            
            # Inject form
            form_a, form_b = tb.compute_xg_form_multipliers(team_a, team_b)
            row["form_a"] = str(form_a)
            row["form_b"] = str(form_b)
            
            # Host support
            if host_teams:
                if team_a in host_teams:
                    row["status_a"] = "True Home"
                    row["fan_pct_a"] = "0.70"
                    row["fan_pct_b"] = "0.30"
                elif team_b in host_teams:
                    row["status_b"] = "True Home"
                    row["fan_pct_a"] = "0.30"
                    row["fan_pct_b"] = "0.70"
                    
            # Outright market blend
            if market_probs:
                p_a = market_probs.get(team_a, None)
                p_b = market_probs.get(team_b, None)
                if p_a is not None and p_b is not None:
                    s_a = math.sqrt(max(p_a, 0.001))
                    s_b = math.sqrt(max(p_b, 0.001))
                    p_a_win_raw = s_a / (s_a + s_b)
                    p_b_win_raw = s_b / (s_a + s_b)
                    mismatch = abs(p_a_win_raw - p_b_win_raw)
                    p_draw = 0.27 * (1.0 - mismatch)
                    rem = 1.0 - p_draw
                    p_home = p_a_win_raw * rem
                    p_away = p_b_win_raw * rem
                    oh = round(1.0 / max(p_home, 0.01), 2)
                    od = round(1.0 / max(p_draw, 0.01), 2)
                    oa = round(1.0 / max(p_away, 0.01), 2)
                    row["odds_home"] = str(oh)
                    row["odds_draw"] = str(od)
                    row["odds_away"] = str(oa)
                    row["market_weight"] = "0.7"
                    
            # Elevation
            elev, accl_a, accl_b = tb._get_match_elevation(team_a, team_b)
            if elev > 1000:
                row["elevation"] = str(elev)
                row["accl_days_a"] = str(accl_a)
                row["accl_days_b"] = str(accl_b)
                
            # Set Elos from predictor database
            row["elo_a"] = predictor.WORLD_CUP_2026_TEAMS[team_a]["elo"]
            row["elo_b"] = predictor.WORLD_CUP_2026_TEAMS[team_b]["elo"]
            
            res = predictor.predict_single_match(row)
            la_adj = res["lambda_a_adj"]
            lb_adj = res["lambda_b_adj"]
            
            self.lam_a[t_a, t_b] = la_adj
            self.lam_b[t_a, t_b] = lb_adj
            
            for state in range(4):
                a_damp = (state // 2) > 0
                b_damp = (state % 2) > 0
                
                la_f = la_adj * 0.85 if (md == 3 and a_damp) else la_adj
                lb_f = lb_adj * 0.85 if (md == 3 and b_damp) else lb_adj
                
                cfg = MatchModelConfig(
                    dist_type=ModelDistribution.POISSON,
                    mu_a=la_f, mu_b=lb_f, rho=-0.05,
                    phase=MatchPhase.GROUP, max_goals=14
                )
                grid = predictor.generate_joint_grid(cfg)
                
                flat = np.zeros(225, dtype=DTYPE_FLOAT)
                for i in range(15):
                    for j in range(15):
                        flat[i*15 + j] = grid.get(i, {}).get(j, 0.0)
                self.group_cdfs[m_idx, state] = np.cumsum(flat)

    def _build_knockout_matrix(self, host_teams):
        base_pen = predictor.CONSTANTS["pen_conversion_rate"]
        
        for p_idx, phase in enumerate(PHASE_MAP):
            for i in range(self.N_TEAMS):
                for j in range(i + 1, self.N_TEAMS):
                    t_a, t_b = self.id_to_team[i], self.id_to_team[j]
                    la, lb = self.lam_a[i, j], self.lam_b[i, j]
                    
                    rho_adj, la_adj, lb_adj = predictor.apply_phase_adjustments(-0.05, la, lb, phase)
                    
                    # Compute fatigue damping factors based on squad depth
                    try:
                        from squad_data import SQUAD_VALUES
                    except ImportError:
                        SQUAD_VALUES = {}
                        
                    val_a = SQUAD_VALUES.get(predictor.validate_team_name(t_a), {"xi": 100.0, "bench": 50.0})
                    val_b = SQUAD_VALUES.get(predictor.validate_team_name(t_b), {"xi": 100.0, "bench": 50.0})
                    
                    bench_a = val_a.get("bench", 50.0)
                    bench_b = val_b.get("bench", 50.0)
                    
                    base_fatigue_penalty = 0.10
                    avg_bench_val = 50.0
                    
                    depth_resilience_a = min(2.0, bench_a / avg_bench_val)
                    penalty_a = base_fatigue_penalty / max(1.0, depth_resilience_a)
                    att_a, def_a = 1.0 - penalty_a, 1.0 + penalty_a
                    
                    depth_resilience_b = min(2.0, bench_b / avg_bench_val)
                    penalty_b = base_fatigue_penalty / max(1.0, depth_resilience_b)
                    att_b, def_b = 1.0 - penalty_b, 1.0 + penalty_b
                    
                    pen_a = base_pen * predictor.PENALTY_STRENGTH.get(predictor.validate_team_name(t_a), 1.0)
                    pen_b = base_pen * predictor.PENALTY_STRENGTH.get(predictor.validate_team_name(t_b), 1.0)
                    
                    # Precompute all 4 fatigue states
                    for state_idx in range(4):
                        fat_a = (state_idx // 2) > 0
                        fat_b = (state_idx % 2) > 0
                        
                        f_la = la_adj
                        f_lb = lb_adj
                        
                        if fat_a:
                            f_la *= att_a
                            f_lb *= def_a
                        if fat_b:
                            f_la *= def_b
                            f_lb *= att_b
                            
                        cfg = MatchModelConfig(
                            dist_type=ModelDistribution.POISSON,
                            mu_a=f_la, mu_b=f_lb, rho=rho_adj,
                            max_goals=14, phase=phase
                        )
                        
                        grid = predictor.generate_ko_final_grid(cfg, max_final_goals=14, pen_conv_a=pen_a, pen_conv_b=pen_b)
                        grid_90 = predictor.generate_joint_grid(cfg)
                        
                        flat_prob = np.zeros(225, dtype=DTYPE_FLOAT)
                        flat_prob_sym = np.zeros(225, dtype=DTYPE_FLOAT)
                        
                        flat_et_prob = np.zeros(225, dtype=DTYPE_FLOAT)
                        flat_et_prob_sym = np.zeros(225, dtype=DTYPE_FLOAT)
                        
                        for ga in range(15):
                            for gb in range(15):
                                idx = ga * 15 + gb
                                idx_sym = gb * 15 + ga
                                
                                p_tot = predictor.get_grid_val(grid, ga, gb)
                                p_90 = predictor.get_grid_val(grid_90, ga, gb) if ga != gb else 0.0
                                p_et = max(0.0, p_tot - p_90)
                                
                                flat_prob[idx] = p_tot
                                flat_prob_sym[idx_sym] = p_tot
                                
                                et_ratio = p_et / p_tot if p_tot > 1e-12 else 0.0
                                flat_et_prob[idx] = et_ratio
                                flat_et_prob_sym[idx_sym] = et_ratio
                                
                        state_idx_sym = fat_b * 2 + fat_a
                        
                        self.ko_cdfs[p_idx, state_idx, i, j] = np.cumsum(flat_prob)
                        self.ko_cdfs[p_idx, state_idx_sym, j, i] = np.cumsum(flat_prob_sym)
                        
                        self.ko_et_probs[p_idx, state_idx, i, j] = flat_et_prob
                        self.ko_et_probs[p_idx, state_idx_sym, j, i] = flat_et_prob_sym

    def _build_3rd_place_routing_table(self):
        """Precomputes the O(1) 12-bit integer routing lookup for all 495 permutations."""
        group_letters = list(tb.GROUPS.keys())
        for i in range(4096):
            if bin(i).count('1') == 8:
                adv_letters = [group_letters[bit] for bit in range(12) if (i & (1 << bit))]
                assignment = solve_third_assignment(adv_letters)
                for j, sk in enumerate(self.slot_keys):
                    self.routing_table[i, j] = group_letters.index(assignment[sk])

class VectorizedSimulator:
    def __init__(self, matrix: MatrixPrecomputer, n_sims: int = 100000):
        self.mx = matrix
        self.N = n_sims
        
        self.striker_shares = np.zeros(self.mx.N_TEAMS, dtype=DTYPE_FLOAT)
        for i, team in enumerate(self.mx.teams):
            sc = tb.STRIKER_CONCENTRATION.get(team)
            conc = sc["concentration"] if sc else tb.STRIKER_CONCENTRATION_DEFAULT
            self.striker_shares[i] = conc
            
        self.CLEAN_BRACKET = OrderedDict([
            ("M73", ("2A", "2B")),
            ("M74", ("1C", "2F")),
            ("M75", ("1E", "3rd_M75")),
            ("M76", ("1F", "2C")),
            ("M77", ("1I", "3rd_M77")),
            ("M78", ("2E", "2I")),
            ("M79", ("1A", "3rd_M79")),
            ("M80", ("1L", "3rd_M80")),
            ("M81", ("1G", "3rd_M81")),
            ("M82", ("1D", "3rd_M82")),
            ("M83", ("1H", "2J")),
            ("M84", ("2K", "2L")),
            ("M85", ("1B", "3rd_M85")),
            ("M86", ("1J", "2H")),
            ("M87", ("2D", "2G")),
            ("M88", ("1K", "3rd_M88")),
            ("M89", ("M73", "M75")),
            ("M90", ("M74", "M77")),
            ("M91", ("M76", "M78")),
            ("M92", ("M79", "M80")),
            ("M93", ("M83", "M84")),
            ("M94", ("M81", "M82")),
            ("M95", ("M86", "M88")),
            ("M96", ("M85", "M87")),
            ("M97", ("M89", "M90")),
            ("M98", ("M93", "M94")),
            ("M99", ("M91", "M92")),
            ("M100", ("M95", "M96")),
            ("M101", ("M97", "M98")),
            ("M102", ("M99", "M100")),
            ("M104", ("M101", "M102")),
        ])

    def _sample_match_cdf(self, tA: np.ndarray, tB: np.ndarray, phase_idx: int,
                          fatigue_status: np.ndarray, m_id: str = None,
                          live_state: dict = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """O(1) Inverse Transform Boolean Sampling (L3 Cache Compatible).

        Live-state override semantics: a key equal to the match id (e.g. "M73")
        forces that [goals_a, goals_b] score in BRACKET orientation (tA, tB as
        passed) for every pairing occupying the slot; "TeamA vs TeamB" keys
        match a specific pairing and are auto-swapped if listed the other way
        round. The m_id key takes precedence over name keys.
        """
        U = np.random.rand(self.N, 1).astype(DTYPE_FLOAT)
        indices = np.zeros(self.N, dtype=np.int16)
        went_to_et = np.zeros(self.N, dtype=bool)
        
        fat_A = fatigue_status[np.arange(self.N), tA].astype(np.uint16)
        fat_B = fatigue_status[np.arange(self.N), tB].astype(np.uint16)
        state_idx = (fat_A << 1) | fat_B
        
        packed = (tA.astype(np.uint16) << 10) | (tB.astype(np.uint16) << 2) | state_idx
        unique_setups = np.unique(packed)
        
        for setup in unique_setups:
            setup_val = int(setup)
            a = (setup_val >> 10) & 0xFF
            b = (setup_val >> 2) & 0xFF
            s = setup_val & 0x03
            mask = (packed == setup)
            if np.any(mask):
                ta_name = self.mx.id_to_team[a]
                tb_name = self.mx.id_to_team[b]
                
                score = None
                val_a = val_b = None   # bound per setup; never reuse a previous iteration's values
                if live_state:
                    if m_id and m_id in live_state:
                        score = live_state[m_id]
                        if score is not None:
                            val_a, val_b = score[0], score[1]
                    else:
                        score = live_state.get(f"{ta_name} vs {tb_name}")
                        if score is not None:
                            val_a, val_b = score[0], score[1]
                        else:
                            score = live_state.get(f"{tb_name} vs {ta_name}")
                            if score is not None:
                                val_a, val_b = score[1], score[0]

                if score is not None and val_a is not None:
                    indices[mask] = np.clip(int(val_a) * 15 + int(val_b), 0, 224)
                    probs = self.mx.ko_et_probs[phase_idx, s, a, b, indices[mask]]
                    U_et = np.random.rand(np.sum(mask))
                    went_to_et[mask] = U_et < probs
                else:
                    cdf = self.mx.ko_cdfs[phase_idx, s, a, b]
                    sampled_idx = (cdf < U[mask]).sum(axis=-1)
                    indices[mask] = np.minimum(sampled_idx, 224)
                    probs = self.mx.ko_et_probs[phase_idx, s, a, b, indices[mask]]
                    U_et = np.random.rand(np.sum(mask))
                    went_to_et[mask] = U_et < probs
                
        goals_A = (indices // 15).astype(DTYPE_INT)
        goals_B = (indices % 15).astype(DTYPE_INT)
        return goals_A, goals_B, went_to_et

    def simulate(self, live_state: dict = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        PTS = np.zeros((self.N, self.mx.N_TEAMS), dtype=DTYPE_INT)
        GF = np.zeros((self.N, self.mx.N_TEAMS), dtype=DTYPE_INT)
        GD = np.zeros((self.N, self.mx.N_TEAMS), dtype=DTYPE_INT)
        team_goals = np.zeros((self.N, self.mx.N_TEAMS), dtype=DTYPE_INT)
        stage_reach = np.zeros((self.N, self.mx.N_TEAMS), dtype=DTYPE_INT)
        
        # 1. Group Stage MD1 & MD2
        for m_idx in range(48):
            ta, tb, _, _ = self.mx.GROUP_MATCHES[m_idx]
            ta_name = self.mx.id_to_team[ta]
            tb_name = self.mx.id_to_team[tb]
            
            score = None
            if live_state:
                score = live_state.get(f"{ta_name} vs {tb_name}")
                if score is not None:
                    g_a = np.full(self.N, score[0], dtype=DTYPE_INT)
                    g_b = np.full(self.N, score[1], dtype=DTYPE_INT)
                else:
                    score = live_state.get(f"{tb_name} vs {ta_name}")
                    if score is not None:
                        g_a = np.full(self.N, score[1], dtype=DTYPE_INT)
                        g_b = np.full(self.N, score[0], dtype=DTYPE_INT)
                        
            if score is None:
                U = np.random.rand(self.N, 1).astype(DTYPE_FLOAT)
                cdf = self.mx.group_cdfs[m_idx, 0]
                flat_scores = np.minimum((cdf < U).sum(axis=-1), 224)
                g_a = (flat_scores // 15).astype(DTYPE_INT)
                g_b = (flat_scores % 15).astype(DTYPE_INT)
            
            GF[:, ta] += g_a
            GF[:, tb] += g_b
            team_goals[:, ta] += g_a
            team_goals[:, tb] += g_b
            GD[:, ta] += (g_a - g_b)
            GD[:, tb] += (g_b - g_a)
            
            PTS[:, ta] += np.where(g_a > g_b, 3, np.where(g_a == g_b, 1, 0)).astype(DTYPE_INT)
            PTS[:, tb] += np.where(g_b > g_a, 3, np.where(g_a == g_b, 1, 0)).astype(DTYPE_INT)

        # 2. Group Stage MD3 (with Vectorized Dampening)
        damp_mask = (PTS >= 6) | (PTS == 0)
        for m_idx in range(48, 72):
            ta, tb, _, _ = self.mx.GROUP_MATCHES[m_idx]
            ta_name = self.mx.id_to_team[ta]
            tb_name = self.mx.id_to_team[tb]
            
            score = None
            if live_state:
                score = live_state.get(f"{ta_name} vs {tb_name}")
                if score is not None:
                    g_a = np.full(self.N, score[0], dtype=DTYPE_INT)
                    g_b = np.full(self.N, score[1], dtype=DTYPE_INT)
                else:
                    score = live_state.get(f"{tb_name} vs {ta_name}")
                    if score is not None:
                        g_a = np.full(self.N, score[1], dtype=DTYPE_INT)
                        g_b = np.full(self.N, score[0], dtype=DTYPE_INT)
                        
            if score is None:
                state = damp_mask[:, ta].astype(DTYPE_INT) * 2 + damp_mask[:, tb].astype(DTYPE_INT)
                cdfs = self.mx.group_cdfs[m_idx, state]
                U = np.random.rand(self.N, 1).astype(DTYPE_FLOAT)
                flat_scores = np.minimum((cdfs < U).sum(axis=-1), 224)
                g_a = (flat_scores // 15).astype(DTYPE_INT)
                g_b = (flat_scores % 15).astype(DTYPE_INT)
                
            GF[:, ta] += g_a
            GF[:, tb] += g_b
            team_goals[:, ta] += g_a
            team_goals[:, tb] += g_b
            GD[:, ta] += (g_a - g_b)
            GD[:, tb] += (g_b - g_a)
            
            PTS[:, ta] += np.where(g_a > g_b, 3, np.where(g_a == g_b, 1, 0)).astype(DTYPE_INT)
            PTS[:, tb] += np.where(g_b > g_a, 3, np.where(g_a == g_b, 1, 0)).astype(DTYPE_INT)

        # 3. Vectorized Tiebreakers (`np.lexsort`)
        lots = np.random.rand(self.N, self.mx.N_TEAMS).astype(DTYPE_FLOAT)
        Elo_tensor = np.tile(self.mx.base_elos, (self.N, 1))
        
        g_winners = np.zeros((self.N, 12), dtype=DTYPE_INT)
        g_runners = np.zeros((self.N, 12), dtype=DTYPE_INT)
        g_thirds = np.zeros((self.N, 12), dtype=DTYPE_INT)
        
        for g_idx in range(12):
            g_teams = np.array([self.mx.GROUP_MATCHES[g_idx*6][0], self.mx.GROUP_MATCHES[g_idx*6][1], 
                                self.mx.GROUP_MATCHES[g_idx*6+1][0], self.mx.GROUP_MATCHES[g_idx*6+1][1]], dtype=DTYPE_INT)
            
            pts_g, gd_g, gf_g, elo_g, lots_g = PTS[:, g_teams], GD[:, g_teams], GF[:, g_teams], Elo_tensor[:, g_teams], lots[:, g_teams]
            
            order = np.lexsort((lots_g, elo_g, gf_g, gd_g, pts_g), axis=-1)
            
            g_winners[:, g_idx] = g_teams[order[:, 3]]
            g_runners[:, g_idx] = g_teams[order[:, 2]]
            g_thirds[:, g_idx] = g_teams[order[:, 1]]

        # 4. Third Place Routing
        t_pts, t_gd, t_gf = np.take_along_axis(PTS, g_thirds, axis=1), np.take_along_axis(GD, g_thirds, axis=1), np.take_along_axis(GF, g_thirds, axis=1)
        t_elo, t_lots = np.take_along_axis(Elo_tensor, g_thirds, axis=1), np.take_along_axis(lots, g_thirds, axis=1)
        
        t_order = np.lexsort((t_lots, t_elo, t_gf, t_gd, t_pts), axis=-1)
        adv_idx = t_order[:, 4:12]
        
        mask = np.zeros(self.N, dtype=np.int32)
        for i in range(8):
            mask |= (1 << adv_idx[:, i])
            
        assignments = self.mx.routing_table[mask] # (N, 8)
        
        state = {}
        for g_idx, name in enumerate(self.mx.group_names):
            state[f"1{name}"] = g_winners[:, g_idx]
            state[f"2{name}"] = g_runners[:, g_idx]
        for i, sk in enumerate(self.mx.slot_keys):
            state[f"3rd_{sk}"] = g_thirds[np.arange(self.N), assignments[:, i]]

        for k, v in state.items():
            if k.startswith("1") or k.startswith("2") or k.startswith("3rd_"):
                stage_reach[np.arange(self.N), v] = 1 

        # 5. Knockout Stage Execution with Fatigue Tracking
        fatigue_status = np.zeros((self.N, self.mx.N_TEAMS), dtype=bool)
        for m_id, (ta_ref, tb_ref) in self.CLEAN_BRACKET.items():
            t_a, t_b = state[ta_ref], state[tb_ref]
            p_idx = get_phase_idx(m_id)
            
            g_a, g_b, went_to_et = self._sample_match_cdf(t_a, t_b, p_idx, fatigue_status, m_id, live_state)
            winner = np.where(g_a > g_b, t_a, t_b)
            state[m_id] = winner
            
            if p_idx < 5: 
                stage_reach[np.arange(self.N), winner] = p_idx + 2
            else:
                stage_reach[np.arange(self.N), winner] = 6 # Champ
                
            team_goals[np.arange(self.N), t_a] += g_a
            team_goals[np.arange(self.N), t_b] += g_b
            
            # Carry over fatigue to the next round for both teams
            fatigue_status[np.arange(self.N), t_a] = went_to_et
            fatigue_status[np.arange(self.N), t_b] = went_to_et

        # 6. Vectorized Golden Boot
        striker_goals = np.random.binomial(team_goals, self.striker_shares)
        noise = np.random.rand(self.N, self.mx.N_TEAMS) * 1e-5
        golden_boot_winners = np.argmax(striker_goals + noise, axis=1)

        return g_winners, stage_reach, golden_boot_winners, state["M104"], team_goals

def run_monte_carlo(n_sims: int = 100000, market_probs: dict = None,
                    seed: int = None, verbose: bool = True,
                    apply_injuries: bool = True,
                    apply_squad_value: bool = True,
                    live_state: dict = None) -> dict:
    """Run N vectorized tournament simulations and aggregate results with optional live state."""
    if seed is not None:
        np.random.seed(seed)
        
    original_teams = copy.deepcopy(predictor.WORLD_CUP_2026_TEAMS)
    
    try:
        # Setup ELO Adjustments
        original_elos = {}
        if apply_injuries and tb.INJURY_ELO_ADJUSTMENTS:
            if verbose:
                print("  🏥 Applying injury Elo adjustments:", file=sys.stderr)
            for team, adj in sorted(tb.INJURY_ELO_ADJUSTMENTS.items(), key=lambda x: x[1]):
                if team in predictor.WORLD_CUP_2026_TEAMS:
                    old_elo = predictor.WORLD_CUP_2026_TEAMS[team]["elo"]
                    original_elos[team] = old_elo
                    new_elo = old_elo + adj
                    predictor.WORLD_CUP_2026_TEAMS[team]["elo"] = new_elo
                    if verbose:
                        print(f"    {team:20s} {old_elo} → {new_elo} ({adj:+d})", file=sys.stderr)
                        
        if apply_squad_value and tb.SQUAD_MARKET_VALUES:
            squad_adjustments = tb.compute_squad_elo_adjustments()
            if squad_adjustments and verbose:
                print("  💰 Applying squad value & form Elo adjustments:", file=sys.stderr)
            for team, adj in sorted(squad_adjustments.items(), key=lambda x: x[1], reverse=True):
                if team in predictor.WORLD_CUP_2026_TEAMS:
                    if team not in original_elos:
                        original_elos[team] = predictor.WORLD_CUP_2026_TEAMS[team]["elo"]
                    old_elo = predictor.WORLD_CUP_2026_TEAMS[team]["elo"]
                    new_elo = old_elo + adj
                    predictor.WORLD_CUP_2026_TEAMS[team]["elo"] = new_elo
                    if verbose and abs(adj) >= 10:
                        print(f"    {team:20s} {old_elo} → {new_elo} ({adj:+d})", file=sys.stderr)
                        
        # Precompute Static Matrices
        if verbose:
            print("  📊 Precomputing static matrices...", file=sys.stderr)
        t_cache = time.time()
        
        matrix = MatrixPrecomputer(host_teams=tb.HOST_TEAMS, market_probs=market_probs)
        
        if verbose:
            print(f"  ✅ Matrices cached in {time.time() - t_cache:.1f}s", file=sys.stderr)
            
        t0 = time.time()
        
        sim = VectorizedSimulator(matrix, n_sims=n_sims)
        g_winners, stages, golden_boots, champs, team_goals = sim.simulate(live_state=live_state)
        
        if verbose:
            elapsed = time.time() - t0
            print(f"  ✅ {n_sims:,} simulations completed in {elapsed:.1f}s ({n_sims/elapsed:.0f}/s)", file=sys.stderr)
            
        # ── 12. AGGREGATE RESULTS ──
        results = {
            "n_sims": n_sims,
            "elapsed_seconds": round(time.time() - t0, 3),
        }
        
        # Group Winners
        results["group_winners"] = {}
        for g_idx, g_name in enumerate(matrix.group_names):
            winners = g_winners[:, g_idx]
            counts = Counter(matrix.id_to_team[idx] for idx in winners)
            sorted_teams = counts.most_common()
            results["group_winners"][g_name] = {
                "tip": sorted_teams[0][0],
                "probability": round(sorted_teams[0][1] / n_sims, 4),
                "all": {t: round(c / n_sims, 4) for t, c in sorted_teams}
            }
            
        # Semifinalists
        sf_counts = Counter()
        for idx in range(48):
            sf_hits = np.sum(stages[:, idx] >= 4)
            if sf_hits > 0:
                sf_counts[matrix.id_to_team[idx]] = sf_hits
        sf_sorted = sf_counts.most_common()
        results["semifinalists"] = {
            "tips": [t for t, _ in sf_sorted[:4]],
            "probabilities": {t: round(c / n_sims, 4) for t, c in sf_sorted},
        }
        
        # Champion (blended with market odds if present)
        champ_counts = Counter(matrix.id_to_team[idx] for idx in champs)
        if market_probs:
            blended_champ = {}
            for t_idx, team in enumerate(matrix.teams):
                mc_prob = champ_counts.get(team, 0) / n_sims
                mkt_prob = market_probs.get(team, mc_prob)
                blended_champ[team] = (mc_prob + mkt_prob) / 2.0
            champ_sorted = sorted(blended_champ.items(), key=lambda x: x[1], reverse=True)
            results["champion"] = {
                "tip": champ_sorted[0][0],
                "probability": round(champ_sorted[0][1], 4),
                "all": {t: round(c, 4) for t, c in champ_sorted if c > 0.005},
            }
        else:
            champ_sorted = champ_counts.most_common()
            results["champion"] = {
                "tip": champ_sorted[0][0],
                "probability": round(champ_sorted[0][1] / n_sims, 4),
                "all": {t: round(c / n_sims, 4) for t, c in champ_sorted if c / n_sims > 0.005},
            }
            
        # Top Scorer Team (Golden Boot Winners)
        gb_counts = Counter(matrix.id_to_team[idx] for idx in golden_boots)
        gb_sorted = gb_counts.most_common()
        
        avg_team_goals = np.mean(team_goals, axis=0)
        avg_goals_dict = {matrix.id_to_team[t_idx]: round(float(avg_team_goals[t_idx]), 1) for t_idx in range(48)}
        
        results["top_scorer_team"] = {
            "tip": gb_sorted[0][0],
            "probability": round(gb_sorted[0][1] / n_sims, 4),
            "avg_goals": avg_goals_dict,
            "all": {t: round(c / n_sims, 4) for t, c in gb_sorted[:10]}
        }
        
        return results
        
    finally:
        predictor.WORLD_CUP_2026_TEAMS.clear()
        predictor.WORLD_CUP_2026_TEAMS.update(original_teams)

def main():
    parser = argparse.ArgumentParser(
        description="WM 2026 Kicktipp Vectorized Monte Carlo Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  Default (100k sims):    python3 vectorized_mc.py
  Different seed:         python3 vectorized_mc.py --seed 42
  JSON output:            python3 vectorized_mc.py --json --output tips.json
"""
    )
    parser.add_argument("--sims", type=int, default=100000, help="Number of Monte Carlo simulations")
    parser.add_argument("--seed", type=int, default=None, help="Random number generator seed")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--json", action="store_true", default=False, help="Output results as JSON")
    parser.add_argument("--no-injuries", action="store_true", default=False, help="Disable pre-tournament injury ELO adjustment")
    parser.add_argument("--no-squad-value", action="store_true", default=False, help="Disable pre-tournament squad value ELO adjustment")
    parser.add_argument("--odds-snapshot", type=str, default=None, help="Path to market odds snapshot JSON")
    parser.add_argument("--fetch-odds", action="store_true", default=False, help="Fetch live market odds from Polymarket")
    parser.add_argument("--odds-api-key", type=str, default=None, help="Odds API key")
    parser.add_argument("--live-state", type=str, default=None, help="Path to live_state.json")
    parser.add_argument("--quiet", action="store_true", default=False, help="Suppress stdout messages")
    
    args = parser.parse_args()
    
    # Load Polymarket odds if snapshot or fetch is requested
    market_probs = None
    if args.odds_snapshot:
        try:
            with open(args.odds_snapshot, 'r') as f:
                market_probs = json.load(f)
        except Exception as e:
            print(f"⚠ Failed to load odds snapshot: {e}", file=sys.stderr)
            
    elif args.fetch_odds:
        try:
            from odds_client import OddsClient
            client = OddsClient(odds_api_key=args.odds_api_key)
            market_probs = client.fetch_polymarket_outright_odds()
            if market_probs and args.output:
                snap_dir = os.path.dirname(args.output) if os.path.dirname(args.output) else "."
                snap_path = os.path.join(snap_dir, f"polymarket_snapshot_{int(time.time())}.json")
                with open(snap_path, 'w') as f:
                    json.dump(market_probs, f, indent=2)
                if not args.quiet:
                    print(f"   💾 Snapshot saved to {snap_path}", file=sys.stderr)
        except Exception as e:
            print(f"⚠ Failed to fetch odds: {e}", file=sys.stderr)
            
    # Normalize market_probs keys
    if market_probs:
        normalized_probs = {}
        for k, v in market_probs.items():
            k_lower = k.lower().strip()
            mapped = predictor.TEAM_NAME_MAPPING.get(k_lower, k)
            normalized_probs[mapped] = v
        market_probs = normalized_probs
        
    live_state = None
    if args.live_state:
        try:
            with open(args.live_state, 'r') as f:
                live_state = json.load(f)
            if not args.quiet:
                print(f"   📥 Loaded live state with {len(live_state)} overridden matches.", file=sys.stderr)
        except Exception as e:
            print(f"⚠ Failed to load live state: {e}", file=sys.stderr)

    if not args.quiet:
        src = "Polymarket + Elo blend" if market_probs else "Elo ratings only"
        print(f"🏆 Starting {args.sims:,} tournament simulations ({src})...", file=sys.stderr)
        
    # Run Monte Carlo
    results = run_monte_carlo(
        n_sims=args.sims,
        market_probs=market_probs,
        seed=args.seed,
        verbose=not args.quiet,
        apply_injuries=not args.no_injuries,
        apply_squad_value=not args.no_squad_value,
        live_state=live_state
    )
    
    # Inject provenance metadata
    from datetime import datetime, timezone
    import subprocess
    try:
        commit_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.STDOUT).decode('utf-8').strip()
        is_dirty = subprocess.call(['git', 'diff', '--quiet']) != 0
        if is_dirty:
            commit_hash += " (dirty)"
    except Exception:
        commit_hash = "unknown"
        
    results["provenance"] = {
        "command": " ".join(sys.argv),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed if args.seed else "random",
        "commit": commit_hash,
    }
    
    # Format results
    if args.json:
        output = json.dumps(results, indent=2, ensure_ascii=False)
    else:
        output = tb.format_results(results)
        
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        if not args.quiet:
            print(f"💾 Results saved to {args.output}", file=sys.stderr)
    else:
        print(output)

if __name__ == "__main__":
    main()
