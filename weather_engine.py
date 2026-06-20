#!/usr/bin/env python3
"""Weather/heat tip engine — a SEPARATE, read-only derivative of the main tip engine.

It takes a per-venue, per-kickoff forecast (open-meteo, fetched in the runner) and
multiplies the main model's lambda_adj by the EXISTING, tested
predictor.calculate_thermal_factor (a capacity factor in [0.5, 1.0]). Lower factor =
fewer goals. Heat reduces both teams' expected goals, and more for high-pressing
(low-PPDA) and non-acclimatised sides — so a hot, open-air game COMPRESSES a pressing
favourite's edge. That is the operator's standing hypothesis, made visible.

⚠ THIS IS A DISTINCT MODEL, NOT A RECONSTRUCTION OF THE CORE PIPELINE. The core's own
get_adjusted_lambdas does NOT apply f_therm as a plain lambda multiplier: it routes it
through an asymmetric attack(+0.5*logF) / defence(-0.8*logF) log-transform and cross-
couples the teams (exponent_A = delta_att_A + delta_def_B, predictor.py ~L1319). Because
the defence weight (0.8) dominates the attack weight (0.5), the core's thermal term
actually RAISES goals in heat ("sloppy defending"). This engine takes the OPPOSITE,
fatigue direction ON PURPOSE because that is the operator's hypothesis — it shares only
the f_therm primitive with the core and must not be presented as reproducing it.

Self-consistency note: the main lambda_adj currently carries f_therm = 1.0 ONLY because
the core's context humidity defaults to 0.0 (WBGT(20 C, 0 %) = 15.3 <= the 20 threshold)
— NOT because 20 C is special (WBGT(20 C, humidity) crosses 20 at ~51 % RH). If the core
is ever fed real humidity, lambda_adj would already carry the core's (goal-raising)
thermal term and multiplying again here would double-count; revisit then.

ISOLATION CONTRACT (mirrors ou_total_engine):
  * INPUT  — the main model's lambda_a_adj/lambda_b_adj, its MatchModelConfig, and a
             forecast (temp, humidity) + venue + per-team PPDA. All read-only.
  * OUTPUT — its own tip dict, returned to the display layer only.
  * Imports ONLY `predictor` (+ stdlib math). Never imported by the core path;
    nothing downstream consumes its result. One-directional: main -> weather. No
    feedback into any other tip.
"""
import math

import predictor


def thermal_multipliers(temp_c, humidity_pct, venue, ppda_a, ppda_b,
                        heat_accl_a=0.0, heat_accl_b=0.0):
    """Per-team thermal capacity factors in [0.5, 1.0] from the real forecast,
    using predictor's own tested model and the venue's roof state.

    Roof state is read from STADIUM_DATA[venue]["retractable_roof"] — the SAME
    source get_adjusted_lambdas uses, so a retractable-roof venue is treated as
    closed/climate-controlled (WBGT pinned to 21 C inside calculate_thermal_factor)
    exactly as the core engine would.
    """
    roof = False
    sd = predictor.STADIUM_DATA.get(venue)
    if sd:
        roof = bool(sd.get("retractable_roof", False))
    f_a = predictor.calculate_thermal_factor(temp_c, humidity_pct, heat_accl_a,
                                             is_retractable_roof=roof, ppda=ppda_a)
    f_b = predictor.calculate_thermal_factor(temp_c, humidity_pct, heat_accl_b,
                                             is_retractable_roof=roof, ppda=ppda_b)
    return f_a, f_b, roof


def weather_adjusted_tip(lambda_a_adj, lambda_b_adj, config, temp_c, humidity_pct,
                         venue, ppda_a=11.0, ppda_b=11.0,
                         heat_accl_a=0.0, heat_accl_b=0.0):
    """Weather-adjusted tip, or None if no usable forecast is available.

    Multiplies the main model's lambda_adj by the real thermal factor, rebuilds the
    joint grid with the SAME generator/config, and runs the SAME 4/3/2 EV solver —
    so the ONLY difference vs the main tip is the heat-driven lambda reduction.
    `temp_c`/`humidity_pct` are treated as the conditions at kickoff; heat_accl_*
    default to 0 (no acclimatisation — the conservative, maximal-heat assumption,
    matching the core default).
    """
    if temp_c is None or humidity_pct is None:
        return None
    try:
        t = float(temp_c)
        h = float(humidity_pct)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(t) and math.isfinite(h)):
        return None

    f_a, f_b, roof = thermal_multipliers(t, h, venue, ppda_a, ppda_b,
                                         heat_accl_a, heat_accl_b)
    la = float(lambda_a_adj) * f_a
    lb = float(lambda_b_adj) * f_b

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
        grid, max_tip,
        pts_exact=getattr(config, "pts_exact", 4),
        pts_diff=getattr(config, "pts_diff", 3),
        pts_tend=getattr(config, "pts_tend", 2))

    (ta, tb), ev = tips[0]
    (r2a, r2b), ev2 = tips[1] if len(tips) > 1 else tips[0]
    wbgt = 21.0 if roof else predictor.calculate_wbgt(t, h)
    ev_by_tip = {f"{a}:{b}": e for (a, b), e in tips}   # EV of every tip under THIS grid
    return {
        "ev_by_tip": ev_by_tip,
        "tip": f"{ta}:{tb}", "tip_a": ta, "tip_b": tb, "ev": ev,
        "runner_up": f"{r2a}:{r2b}", "runner_up_ev": ev2,
        "f_a": f_a, "f_b": f_b, "roof": roof,
        "temp_c": t, "humidity": h, "wbgt": wbgt,
        "lam_a": la, "lam_b": lb,                     # heat-reduced goals-for / -against
        "lam_a_base": float(lambda_a_adj), "lam_b_base": float(lambda_b_adj),
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
    }
