#!/usr/bin/env python3
"""Fatigue tip engine — a SEPARATE, read-only DIFFERENTIAL fatigue model.

Supersedes the heat-only weather_engine by combining the three fatigue drivers the
operator called out, PER TEAM:

  * HEAT      — predictor.calculate_thermal_factor (WBGT × pressing intensity), the
                same primitive weather_engine uses.
  * TRAVEL    — predictor.calculate_travel_penalty (rest deficit + distance + timezone)
                computed from each team's PREVIOUS match venue/date vs this fixture's.
  * CONGESTION— a small cumulative-load drag from total tournament miles already flown.

Each team gets its OWN capacity factor in (0, 1]; lower = more fatigued. Applying the
two factors to the two lambdas shifts the lambda RATIO (not just the total), so unlike
a symmetric heat-only cut this can FLIP a tight game: the more-loaded team (more travel,
less rest, hotter/heavier pressing) "breaks" and an even matchup tips the other way.

Direction: this is the FATIGUE direction (more load -> fewer goals for that team),
matching the operator's hypothesis. It is NOT a reconstruction of predictor's own
get_adjusted_lambdas (whose thermal term is asymmetric and actually raises goals in
heat); it shares only the f_therm / travel primitives. See weather_engine.py for the
fuller note on that divergence.

CAVEAT ON MAGNITUDE: the travel term is heavily damped by rest. At ~6 days rest
(typical group-stage spacing) calculate_travel_penalty is near zero, so in the group
stage fatigue ≈ heat alone. Travel/congestion bite in the KNOCKOUT rounds (3-4 day
rest, longer hops) — that is where this engine diverges most from the heat-only view.

ISOLATION CONTRACT: imports only `predictor` (+ stdlib math); consumes the main
model's lambda_adj + config + per-team fatigue inputs (read-only, mutates nothing);
returns its own tip dict; never imported by the core path; one-directional. No feedback.
"""
import math

import predictor

# Cumulative-load drag: total tournament miles already flown -> a small extra factor.
# Deliberately gentle (caps at CONG_MAX) so congestion nudges, never dominates.
CONG_MILES_FULL = 6000.0   # cumulative miles that reach the full CONG_MAX drag
CONG_MAX = 0.06            # cap cumulative drag at 6 %


def team_fatigue_factor(temp_c, humidity_pct, venue, ppda,
                        rest_days, travel_miles, tz_crossed, direction,
                        cum_miles=0.0, heat_accl=0.0):
    """Per-team capacity factor in (0, 1] = f_heat * f_travel * f_cong, plus a
    components dict for transparency. Lower factor = more fatigued.

    Heat uses the venue roof state (retractable -> closed) exactly as the core does.
    Travel uses predictor.calculate_travel_penalty (0..travel_max_penalty=0.30).
    """
    roof = bool(predictor.STADIUM_DATA.get(venue, {}).get("retractable_roof", False))
    if temp_c is None or humidity_pct is None:
        f_heat = 1.0
        wbgt = None
    else:
        f_heat = predictor.calculate_thermal_factor(temp_c, humidity_pct, heat_accl,
                                                    is_retractable_roof=roof, ppda=ppda)
        wbgt = 21.0 if roof else predictor.calculate_wbgt(temp_c, humidity_pct)

    travel_pen = predictor.calculate_travel_penalty(rest_days, travel_miles, tz_crossed, direction)
    f_travel = max(0.5, 1.0 - travel_pen)

    cong = min(CONG_MAX, CONG_MAX * max(0.0, cum_miles) / CONG_MILES_FULL)
    f_cong = 1.0 - cong

    factor = f_heat * f_travel * f_cong
    return factor, {
        "factor": factor, "f_heat": f_heat, "f_travel": f_travel, "f_cong": f_cong,
        "travel_pen": travel_pen, "rest_days": rest_days, "travel_miles": travel_miles,
        "tz_crossed": tz_crossed, "cum_miles": cum_miles, "roof": roof, "wbgt": wbgt,
    }


def fatigue_adjusted_tip(lambda_h_adj, lambda_a_adj, config, factor_h, factor_a):
    """Tip after applying the two per-team fatigue factors to the two lambdas.

    Rebuilds the joint grid with the SAME generator/config and runs the SAME 4/3/2
    EV solver — the only change is the per-team lambda scaling, whose ASYMMETRY can
    flip the winner in a tight game.
    """
    la = float(lambda_h_adj) * float(factor_h)
    lb = float(lambda_a_adj) * float(factor_a)
    cfg = predictor.MatchModelConfig(
        dist_type=config.dist_type, mu_a=la, mu_b=lb,
        alpha_a=getattr(config, "alpha_a", 0.0), alpha_b=getattr(config, "alpha_b", 0.0),
        rho=getattr(config, "rho", -0.05), max_goals=getattr(config, "max_goals", 12),
        max_tip=getattr(config, "max_tip", 6),
        pts_exact=getattr(config, "pts_exact", 4), pts_diff=getattr(config, "pts_diff", 3),
        pts_tend=getattr(config, "pts_tend", 2))
    grid = predictor.generate_joint_grid(cfg)
    max_tip = getattr(config, "max_tip", 6)
    tips, scores, (p_home, p_draw, p_away) = predictor.solve_optimal_tip_from_grid(
        grid, max_tip, pts_exact=getattr(config, "pts_exact", 4),
        pts_diff=getattr(config, "pts_diff", 3), pts_tend=getattr(config, "pts_tend", 2))
    (ta, tb), ev = tips[0]
    (r2a, r2b), ev2 = tips[1] if len(tips) > 1 else tips[0]
    ev_by_tip = {f"{a}:{b}": e for (a, b), e in tips}   # EV of every tip under THIS grid
    return {
        "ev_by_tip": ev_by_tip,
        "tip": f"{ta}:{tb}", "tip_a": ta, "tip_b": tb, "ev": ev,
        "runner_up": f"{r2a}:{r2b}", "runner_up_ev": ev2,
        "lam_h": la, "lam_a": lb,
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
    }


def fatigue_adjusted_ko_tip(lambda_h_adj, lambda_a_adj, config, factor_h, factor_a,
                            team_a="", team_b=""):
    """KNOCKOUT-convention-correct sibling of fatigue_adjusted_tip.

    fatigue_adjusted_tip rebuilds with generate_joint_grid (90-minute grid, DRAWS
    allowed) — right for group games, but WRONG for a knockout, whose pool scoring
    is ``shootout_total`` (no draws; 90'+ET+every shootout kick summed). On a draw-
    allowed grid a tight KO game can spuriously pick a 0:0, which is not even a legal
    KO score. This rebuilds the SAME grid predictor.predict_single_match uses for the
    active ``kicktipp_ko_convention``, so the fatigue-shifted KO tip is directly
    comparable to the main KO tip. team_a/team_b feed per-team penalty strength under
    shootout_total. Return shape matches fatigue_adjusted_tip."""
    la = float(lambda_h_adj) * float(factor_h)
    lb = float(lambda_a_adj) * float(factor_a)
    mt = max(getattr(config, "max_tip", 10), 10)
    cfg = predictor.MatchModelConfig(
        dist_type=config.dist_type, mu_a=la, mu_b=lb,
        alpha_a=getattr(config, "alpha_a", 0.0), alpha_b=getattr(config, "alpha_b", 0.0),
        rho=getattr(config, "rho", -0.05), max_goals=getattr(config, "max_goals", 12),
        max_tip=mt, pts_exact=getattr(config, "pts_exact", 4),
        pts_diff=getattr(config, "pts_diff", 3), pts_tend=getattr(config, "pts_tend", 2),
        phase=getattr(config, "phase", None))
    convention = str(predictor.CONSTANTS.get("kicktipp_ko_convention", "shootout_total")).strip().lower()
    if convention == "120min":
        grid = predictor.generate_ko_120_grid(cfg, max_final_goals=15)
    elif convention == "90min":
        grid = predictor.generate_joint_grid(cfg)
    else:  # shootout_total — 3-layer KO grid with team-specific penalty strength
        base = predictor.CONSTANTS["pen_conversion_rate"]
        grid = predictor.generate_ko_final_grid(
            cfg, max_final_goals=15,
            pen_conv_a=base * predictor.PENALTY_STRENGTH.get(team_a, 1.0),
            pen_conv_b=base * predictor.PENALTY_STRENGTH.get(team_b, 1.0))
    tips, scores, (p_home, p_draw, p_away) = predictor.solve_optimal_tip_from_grid(
        grid, mt, pts_exact=getattr(config, "pts_exact", 4),
        pts_diff=getattr(config, "pts_diff", 3), pts_tend=getattr(config, "pts_tend", 2))
    if convention != "120min":
        p_draw = 0.0                       # no-draw outcome space; zero numerical noise
    (ta, tb), ev = tips[0]
    (r2a, r2b), ev2 = tips[1] if len(tips) > 1 else tips[0]
    return {
        "ev_by_tip": {f"{a}:{b}": e for (a, b), e in tips},
        "tip": f"{ta}:{tb}", "tip_a": ta, "tip_b": tb, "ev": ev,
        "runner_up": f"{r2a}:{r2b}", "runner_up_ev": ev2,
        "lam_h": la, "lam_a": lb,
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
    }
