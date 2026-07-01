#!/usr/bin/env python3
"""O/U-Total tip engine — a SEPARATE, read-only derivative of the main tip engine.

Operator request (2026-06-20): the main tip's exact score is set by the **1X2**
line, which fixes the winner and the goal *difference* but lets the goal *total*
fall out of the model's own lambdas. This engine KEEPS the main model's winner /
margin (the signed difference d = lambda_a_adj - lambda_b_adj) but re-slaves the
TOTAL number of goals to Polymarket's **Over/Under** market — specifically to
`market_total`, the E[goals] implied by the O/U ladder (odds_client computes it
as the Poisson mean whose survival reproduces the over/under prices).

So a main tip of 1:0 (margin +1) under a strong Over 2.5 (market_total ~3.0)
becomes 2:1 — same +1 margin, more goals. Where the market sees fewer goals AND
the model margin still fits inside that total, the score is trimmed too. But the
model's goal DIFFERENCE is NEVER capped (operator directive): a lopsided favourite
whose margin is wider than the market total keeps its margin — the O/U cannot
shrink a 4-goal edge into a 3-goal game, so e.g. Spain/France stay at the model's
4:0 / 5:0 rather than being trimmed.

ISOLATION CONTRACT (why this is safe to bolt on):
  * INPUT  — the main model's lambda_a_adj, lambda_b_adj, its MatchModelConfig,
             and the market O/U total. ALL read-only; never mutated.
  * OUTPUT — its own tip dict, returned to the caller's display layer only.
  * This module imports ONLY `predictor` (for the grid builder + EV solver +
    MatchModelConfig). It is never imported by the core prediction path, and
    nothing downstream consumes its result. One-directional: main -> O/U. No
    feedback into any other tip.
"""
import math
from typing import Optional

import predictor


# Minimum each side's expected goals must stay above for the market-total rescale
# to be applied. If the model margin is so wide that a side would fall below EPS,
# the market total is incompatible with the model's verdict and we keep the model's
# own lambdas untouched (operator directive 2026-06-20: never cap the difference —
# not even at the tip level, so a model 5:0 stays 5:0 rather than being trimmed).
EPS = 0.05


def rescale_lambdas_to_total(lambda_a: float, lambda_b: float,
                             market_total: float, eps: float = EPS):
    """Preserve the signed goal difference d = la - lb EXACTLY; set the sum to
    market_total when that total can physically hold the margin.

        la' = (S + d) / 2     lb' = (S - d) / 2     with S = market_total

    The goal DIFFERENCE is never capped — not even at the tip level. If the model
    margin is wider than the whole market total (a lopsided favourite the O/U
    prices as low-scoring), the total cannot contain the full margin, so the market
    total is incompatible with the model's verdict: we KEEP THE MODEL'S OWN lambdas
    unchanged. So d is preserved exactly in every branch; the sum equals S whenever
    S >= |d| (the rescale fires), and stays at the model total otherwise (a model
    5:0 stays 5:0, never trimmed to 4:0).

    Pure function: returns (la', lb'); mutates nothing.
    """
    d = float(lambda_a) - float(lambda_b)
    S = max(float(market_total), 2.0 * eps)
    la = (S + d) / 2.0
    lb = (S - d) / 2.0
    # Never cap the difference: if either side would fall below eps the market total
    # cannot hold the model's margin, so fall back to the model's own lambdas rather
    # than shrink the margin or trim the favourite's scoreline.
    if lb < eps or la < eps:
        return float(lambda_a), float(lambda_b)
    return la, lb


def _clone_config_with_lambdas(config, la: float, lb: float):
    """Rebuild the main model's MatchModelConfig with new lambdas, everything else
    (distribution, dispersion alpha, Dixon-Coles rho, max_goals, max_tip, scoring)
    identical — so the ONLY difference vs the main tip is the goal total."""
    return predictor.MatchModelConfig(
        dist_type=config.dist_type,
        mu_a=la,
        mu_b=lb,
        alpha_a=getattr(config, "alpha_a", 0.0),
        alpha_b=getattr(config, "alpha_b", 0.0),
        rho=getattr(config, "rho", -0.05),
        max_goals=getattr(config, "max_goals", 12),
        max_tip=getattr(config, "max_tip", 6),
        pts_exact=getattr(config, "pts_exact", 4),
        pts_diff=getattr(config, "pts_diff", 3),
        pts_tend=getattr(config, "pts_tend", 2),
    )


def ou_total_tip(lambda_a_adj: float, lambda_b_adj: float, config,
                 market_total: Optional[float]) -> Optional[dict]:
    """O/U-total-adjusted tip, or None when no market O/U total is available.

    Clones `config`, swaps in the rescaled lambdas, rebuilds the joint grid with
    the SAME generator the main model uses (Poisson/NB + Dixon-Coles), and runs
    the SAME 4/3/2 EV solver. Returns the engine's own tip plus the rescaled
    goals-for / goals-against expectation (the "Tore / Gegentore" view).
    """
    if market_total is None:
        return None
    # Input hygiene: the market_total comes from an external feed. Reject a
    # non-finite or non-positive total (a malformed/zero/NaN feed) rather than
    # let it slip past the max() floor and propagate a degenerate grid.
    try:
        mt = float(market_total)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(mt) or mt <= 0.0:
        return None

    la, lb = rescale_lambdas_to_total(lambda_a_adj, lambda_b_adj, mt)
    cfg = _clone_config_with_lambdas(config, la, lb)

    grid = predictor.generate_joint_grid(cfg)
    max_tip = getattr(config, "max_tip", 6)
    tips, scores, (p_home, p_draw, p_away) = predictor.solve_optimal_tip_from_grid(
        grid, max_tip,
        pts_exact=getattr(config, "pts_exact", 4),
        pts_diff=getattr(config, "pts_diff", 3),
        pts_tend=getattr(config, "pts_tend", 2),
    )

    (ta, tb), ev = tips[0]
    (r2a, r2b), ev2 = tips[1] if len(tips) > 1 else tips[0]
    model_total = float(lambda_a_adj) + float(lambda_b_adj)
    ev_by_tip = {f"{a}:{b}": e for (a, b), e in tips}   # EV of every tip under THIS grid
    return {
        "ev_by_tip": ev_by_tip,
        "tip": f"{ta}:{tb}",
        "tip_a": ta,
        "tip_b": tb,
        "ev": ev,
        "runner_up": f"{r2a}:{r2b}",
        "runner_up_ev": ev2,
        "lam_a": la,                 # rescaled goals-FOR expectation (Tore)
        "lam_b": lb,                 # rescaled goals-AGAINST expectation (Gegentore)
        "market_total": float(market_total),
        "model_total": model_total,
        "total_delta": float(market_total) - model_total,  # >0: market sees MORE goals
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
    }


# ── Coin-flip-line O/U integration (TENDENCY-PRESERVING) — added 2026-07-01 ──────
# Backtest verdict (T-45 market totals from the daemon logs): the NAIVE market-total
# rescale (ou_total_tip above, which lets the re-solve flip the tip's tendency) LOSES
# in the group stage (-3 over 31 games) — it pushes off points-rich draw tips (a model
# 0:0 -> 1:0 forfeits an exact 0:0). The TENDENCY-PRESERVING rescale below (a draw stays
# a draw, a winner stays that winner; only the scoreline WITHIN the tendency moves to the
# market total) turns that to +1/31 in the group AND keeps +1/6 in the KO. Fires only
# with sufficient O/U liquidity at the coin-flip line. Read-only; one-directional.
OU_MIN_LINE_LIQUIDITY = 40000.0   # USD depth required at the coin-flip line


def coinflip_total(totals):
    """The market's COIN-FLIP (median) total: interpolate the O/U line where P(over)
    crosses 0.5. `totals` = the O/U ladder [{'line','over','liq'}, ...]. Returns
    (line, liq_at_line) or (None, None) if the curve never crosses 0.5.

    The operator's framing: if the ~1.5 line is the coin-flip the total is low; if the
    ~3.5 line is the coin-flip the total is high."""
    if not totals:
        return None, None
    t = sorted((x for x in totals if "line" in x and "over" in x), key=lambda x: x["line"])
    for i in range(len(t) - 1):
        if t[i]["over"] >= 0.5 >= t[i + 1]["over"]:
            lo, hi = t[i], t[i + 1]
            span = lo["over"] - hi["over"]
            frac = (lo["over"] - 0.5) / span if span else 0.0
            line = lo["line"] + frac * (hi["line"] - lo["line"])
            return line, min(lo.get("liq", 0.0), hi.get("liq", 0.0))
    return None, None


def ou_tendency_preserving_tip(lambda_a_adj, lambda_b_adj, config, market_total,
                               model_tip, ko_convention=None, team_a="", team_b=""):
    """Re-slave the goal TOTAL to `market_total` (preserving the signed lambda
    difference) but NEVER change the model's TENDENCY: a draw tip stays a draw, a
    home/away win stays that winner — only the scoreline WITHIN the tendency moves.

    model_tip is (tip_a, tip_b). ko_convention: None -> 90' grid (group, draws valid);
    'shootout_total' -> KO grid (no draws). Returns the O/U-adjusted (ta, tb); falls
    back to model_tip on an unusable total. Pure/read-only."""
    if market_total is None:
        return (int(model_tip[0]), int(model_tip[1]))
    try:
        mt = float(market_total)
    except (TypeError, ValueError):
        return (int(model_tip[0]), int(model_tip[1]))
    if not math.isfinite(mt) or mt <= 0.0:
        return (int(model_tip[0]), int(model_tip[1]))

    a0, b0 = int(model_tip[0]), int(model_tip[1])
    tend = 0 if a0 == b0 else (1 if a0 > b0 else -1)

    la, lb = rescale_lambdas_to_total(lambda_a_adj, lambda_b_adj, mt)
    cfg = _clone_config_with_lambdas(config, la, lb)

    if str(ko_convention or "").strip().lower() == "shootout_total":
        base = predictor.CONSTANTS["pen_conversion_rate"]
        grid = predictor.generate_ko_final_grid(
            cfg, max_final_goals=15,
            pen_conv_a=base * predictor.PENALTY_STRENGTH.get(team_a, 1.0),
            pen_conv_b=base * predictor.PENALTY_STRENGTH.get(team_b, 1.0))
        max_tip = max(getattr(cfg, "max_tip", 10), 10)
    else:
        grid = predictor.generate_joint_grid(cfg)
        max_tip = getattr(cfg, "max_tip", 6)

    tips, _, _ = predictor.solve_optimal_tip_from_grid(
        grid, max_tip, pts_exact=getattr(cfg, "pts_exact", 4),
        pts_diff=getattr(cfg, "pts_diff", 3), pts_tend=getattr(cfg, "pts_tend", 2))
    for (ta, tb), _ev in tips:
        if (0 if ta == tb else (1 if ta > tb else -1)) == tend:
            return (ta, tb)
    return (a0, b0)


def ou_adjusted_from_extras(lambda_a_adj, lambda_b_adj, config, extras, model_tip,
                            min_liquidity=OU_MIN_LINE_LIQUIDITY,
                            ko_convention=None, team_a="", team_b=""):
    """Full pipeline: coin-flip line from the O/U ladder + LIQUIDITY GUARD +
    tendency-preserving rescale. `extras` = the snapshot's per-game extras
    ({'totals': [...]}). Returns (tip, meta) with meta = {eligible, shifted,
    coinflip_line, liq}. No coin-flip crossing or depth < min_liquidity -> model tip
    unchanged (eligible=False)."""
    line, liq = coinflip_total((extras or {}).get("totals"))
    mtip = (int(model_tip[0]), int(model_tip[1]))
    if line is None or liq is None or liq < float(min_liquidity):
        return mtip, {"eligible": False, "shifted": False, "coinflip_line": line, "liq": liq}
    tip = ou_tendency_preserving_tip(lambda_a_adj, lambda_b_adj, config, line,
                                     mtip, ko_convention, team_a, team_b)
    return tip, {"eligible": True, "shifted": tip != mtip,
                 "coinflip_line": round(line, 2), "liq": liq}
