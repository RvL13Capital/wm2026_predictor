#!/usr/bin/env python3
"""
Monte Carlo Tournament Simulation Tool for WM 2026 Kicktipp Predictor.

Reads a CSV of upcoming matches (without goals_a / goals_b), runs the full
prediction pipeline from predictor.py, finds the optimal tip and EV for each
match, and optionally runs Monte Carlo simulations to estimate actual point
distributions and tournament totals with confidence intervals.
"""

import os
import sys
import csv
import json
import math
import random
import argparse
from io import StringIO
from typing import List, Dict, Tuple, Optional, Any

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so `import predictor` works.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import predictor
import tournament_bonusfragen as tbf


# ===========================================================================
# 1. CSV LOADER (prediction-mode: no goals_a / goals_b required)
# ===========================================================================

_REQUIRED_HEADERS = {"team_a", "team_b"}

_FLOAT_KEYS = {
    "elevation", "temp", "humidity",
    "fan_pct_a", "fan_pct_b",
    "rest_days_a", "rest_days_b",
    "travel_miles_a", "travel_miles_b",
    "accl_days_a", "accl_days_b",
    "heat_accl_days_a", "heat_accl_days_b",
    "alpha_a", "alpha_b", "rho",
}

_INT_KEYS = {
    "tz_crossed_a", "tz_crossed_b",
}

_STRING_KEYS = {
    "team_a", "team_b", "phase",
    "status_a", "status_b",
    "direction_a", "direction_b",
}


def load_prediction_csv(csv_path: str) -> List[Dict[str, Any]]:
    """Load a prediction-mode CSV (no goals columns required).

    Returns a list of row dicts with parsed types.  Unknown numeric-looking
    columns are cast to int or float automatically; everything else stays str.
    """
    if not csv_path or not isinstance(csv_path, str):
        raise ValueError("Invalid CSV path")
    if os.path.isdir(csv_path):
        raise IsADirectoryError(f"Path is a directory: {csv_path}")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"File not found: {csv_path}")
    if os.path.getsize(csv_path) == 0:
        raise ValueError("File is empty")

    with open(csv_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    if not content.strip():
        raise ValueError("File is empty")

    reader = csv.DictReader(StringIO(content.strip()))
    if not reader.fieldnames:
        raise ValueError("Missing headers")

    fieldnames_set = set(reader.fieldnames)
    missing = _REQUIRED_HEADERS - fieldnames_set
    if missing:
        raise ValueError(f"Missing required headers: {missing}")

    data: List[Dict[str, Any]] = []
    for row_num, row in enumerate(reader, start=2):
        team_a = (row.get("team_a") or "").strip()
        team_b = (row.get("team_b") or "").strip()
        if not team_a or not team_b:
            raise ValueError(f"Row {row_num}: Missing team names")
        if team_a == team_b:
            raise ValueError(f"Row {row_num}: team_a == team_b ({team_a})")

        parsed: Dict[str, Any] = {"team_a": team_a, "team_b": team_b}

        for key, val in row.items():
            if key in ("team_a", "team_b"):
                continue
            if val is None or val.strip() == "":
                continue
            val_s = val.strip()

            if key in _STRING_KEYS:
                parsed[key] = val_s
                continue
            if key in _FLOAT_KEYS:
                try:
                    parsed[key] = float(val_s)
                except ValueError:
                    raise ValueError(f"Row {row_num}: malformed float for {key}: {val_s}")
                continue
            if key in _INT_KEYS:
                try:
                    parsed[key] = int(val_s)
                except ValueError:
                    raise ValueError(f"Row {row_num}: malformed int for {key}: {val_s}")
                continue

            # Auto-detect type for unknown columns
            try:
                parsed[key] = int(val_s)
            except ValueError:
                try:
                    parsed[key] = float(val_s)
                except ValueError:
                    parsed[key] = val_s

        data.append(parsed)

    if not data:
        raise ValueError("CSV contains no data rows")
    return data


# ===========================================================================
# 2. CONTEXT BUILDER (mirrors backtest.py logic)
# ===========================================================================

def _make_context(row: Dict[str, Any], suffix: str) -> Dict[str, Any]:
    """Build a predictor-compatible context dict from a CSV row.

    ``suffix`` is ``'a'`` or ``'b'``.
    """
    ctx: Dict[str, Any] = {}

    # Shared environment keys (same for both teams)
    for key in ("elevation", "temp", "humidity"):
        if key in row:
            ctx[key] = row[key]

    # Per-team keys mapped into context keys the predictor expects
    mapping = {
        "status": f"status_{suffix}",
        "fan_support_pct": f"fan_pct_{suffix}",
        f"fan_pct_{'A' if suffix == 'a' else 'B'}": f"fan_pct_{suffix}",
        "rest_days": f"rest_days_{suffix}",
        "travel_miles": f"travel_miles_{suffix}",
        "tz_crossed": f"tz_crossed_{suffix}",
        "direction": f"direction_{suffix}",
        "accl_days": f"accl_days_{suffix}",
        f"accl_days_{'A' if suffix == 'a' else 'B'}": f"accl_days_{suffix}",
        "heat_accl_days": f"heat_accl_days_{suffix}",
        f"heat_accl_days_{'A' if suffix == 'a' else 'B'}": f"heat_accl_days_{suffix}",
    }
    for ctx_key, row_key in mapping.items():
        if row_key in row:
            ctx[ctx_key] = row[row_key]

    return ctx


# ===========================================================================
# 3. SINGLE-MATCH PREDICTION PIPELINE
# ===========================================================================

def predict_match(row: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full prediction pipeline for one match.

    Returns a dict with:
        team_a, team_b, phase, lambda_base_a/b, lambda_adj_a/b,
        optimal_tip (tuple), ev, prob_home/draw/away,
        top5_tips, top5_scores, grid (for MC sampling).
    """
    team_a = row["team_a"]
    team_b = row["team_b"]
    phase = row.get("phase", "group")

    # 1) Base lambdas from Elo + Injuries + Squad Value
    elo_a = predictor.WORLD_CUP_2026_TEAMS.get(team_a, {}).get("elo", 1500)
    elo_b = predictor.WORLD_CUP_2026_TEAMS.get(team_b, {}).get("elo", 1500)
    
    # Apply injury and squad value adjustments
    squad_elo_adj = tbf.compute_squad_elo_adjustments()
    elo_a += squad_elo_adj.get(team_a, 0.0)
    elo_b += squad_elo_adj.get(team_b, 0.0)
    elo_a += tbf.INJURY_ELO_ADJUSTMENTS.get(team_a, 0.0)
    elo_b += tbf.INJURY_ELO_ADJUSTMENTS.get(team_b, 0.0)
    
    lambda_base_a = 1.2 + (elo_a - 1700) / 800.0
    lambda_base_b = 1.2 + (elo_b - 1700) / 800.0

    # 2) Context dicts
    ctx_a = _make_context(row, "a")
    ctx_b = _make_context(row, "b")

    # Add host status to ctx from HOST_TEAMS
    if team_a in tbf.HOST_TEAMS:
        ctx_a["status_a"] = "host"
    if team_b in tbf.HOST_TEAMS:
        ctx_b["status_b"] = "host"
        
    # Get stadium elevation and acclimation days if phase is group
    elevation, accl_a, accl_b = tbf._get_match_elevation(team_a, team_b)
    ctx_a["elevation"] = elevation
    ctx_b["elevation"] = elevation
    ctx_a["accl_days"] = accl_a
    ctx_b["accl_days"] = accl_b

    # Apply xG form multipliers
    form_a, form_b = tbf.compute_xg_form_multipliers(team_a, team_b)
    lambda_base_a *= form_a
    lambda_base_b *= form_b

    # 3) Adjusted lambdas
    lambda_adj_a, lambda_adj_b = predictor.get_adjusted_lambdas(
        lambda_base_a, lambda_base_b, ctx_a, ctx_b

    )

    # 4) Distribution config
    alpha_a = row.get("alpha_a", 0.0)
    alpha_b = row.get("alpha_b", 0.0)
    rho = row.get("rho", -0.05)

    dist_type = (
        predictor.ModelDistribution.NEGATIVE_BINOMIAL
        if (alpha_a > 0.0 or alpha_b > 0.0)
        else predictor.ModelDistribution.POISSON
    )

    config = predictor.MatchModelConfig(
        dist_type=dist_type,
        mu_a=lambda_adj_a,
        mu_b=lambda_adj_b,
        alpha_a=alpha_a,
        alpha_b=alpha_b,
        rho=rho,
    )

    # 5) Generate probability grid
    grid = predictor.generate_joint_grid(config)

    # 6) Solve optimal tip
    sorted_tips, sorted_scores, outcomes = predictor.solve_optimal_tip(config)
    optimal_tip = sorted_tips[0][0]
    optimal_ev = sorted_tips[0][1]

    return {
        "team_a": team_a,
        "team_b": team_b,
        "phase": phase,
        "lambda_base_a": lambda_base_a,
        "lambda_base_b": lambda_base_b,
        "lambda_adj_a": lambda_adj_a,
        "lambda_adj_b": lambda_adj_b,
        "optimal_tip": optimal_tip,
        "ev": optimal_ev,
        "prob_home": outcomes[0],
        "prob_draw": outcomes[1],
        "prob_away": outcomes[2],
        "top5_tips": sorted_tips[:5],
        "top5_scores": sorted_scores[:5],
        "grid": grid,
        "config": config,
    }


# ===========================================================================
# 4. MONTE CARLO SIMULATION
# ===========================================================================

def _flatten_grid_for_sampling(
    grid: Dict[int, Dict[int, float]],
) -> Tuple[List[Tuple[int, int]], List[float]]:
    """Convert a probability grid into parallel outcome/weight lists for
    ``random.choices``.
    """
    outcomes: List[Tuple[int, int]] = []
    weights: List[float] = []
    for ga in sorted(grid.keys()):
        for gb in sorted(grid[ga].keys()):
            p = grid[ga][gb]
            if p > 0.0:
                outcomes.append((ga, gb))
                weights.append(p)
    return outcomes, weights


def monte_carlo_match(
    grid: Dict[int, Dict[int, float]],
    tip: Tuple[int, int],
    n_simulations: int = 10_000,
    pts_exact: int = 4,
    pts_diff: int = 3,
    pts_tend: int = 2,
    rng_seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Simulate *n_simulations* match outcomes drawn from *grid*, score each
    against *tip*, and report descriptive statistics.

    Returns dict with:
        mean_points, std_points, p0/p2/p3/p4, point_samples (list[int]).
    """
    outcomes, weights = _flatten_grid_for_sampling(grid)
    if not outcomes:
        return {
            "mean_points": 0.0,
            "std_points": 0.0,
            "p0": 1.0,
            "p2": 0.0,
            "p3": 0.0,
            "p4": 0.0,
            "point_samples": [0] * n_simulations,
        }

    rng = random.Random(rng_seed)
    samples = rng.choices(outcomes, weights=weights, k=n_simulations)

    point_samples: List[int] = []
    counts = {0: 0, 2: 0, 3: 0, 4: 0}

    for ga, gb in samples:
        pts = predictor.get_points(tip[0], tip[1], ga, gb,
                                   pts_exact=pts_exact,
                                   pts_diff=pts_diff,
                                   pts_tend=pts_tend)
        point_samples.append(pts)
        counts[pts] = counts.get(pts, 0) + 1

    n = float(n_simulations)
    mean_pts = sum(point_samples) / n
    var_pts = sum((p - mean_pts) ** 2 for p in point_samples) / n
    std_pts = math.sqrt(var_pts)

    return {
        "mean_points": mean_pts,
        "std_points": std_pts,
        "p0": counts.get(0, 0) / n,
        "p2": counts.get(2, 0) / n,
        "p3": counts.get(3, 0) / n,
        "p4": counts.get(4, 0) / n,
        "point_samples": point_samples,
    }


# ===========================================================================
# 5. TOURNAMENT-LEVEL AGGREGATION
# ===========================================================================

def aggregate_tournament(
    match_results: List[Dict[str, Any]],
    n_simulations: int,
) -> Dict[str, Any]:
    """Aggregate per-match MC samples into tournament totals and confidence
    intervals.

    Each entry in *match_results* must have a ``"mc"`` key whose value is
    the dict returned by :func:`monte_carlo_match`.

    Returns dict with:
        total_ev, total_mc_mean, total_mc_std,
        percentiles (5, 25, 50, 75, 95).
    """
    # Build per-simulation tournament totals
    n_matches = len(match_results)
    tournament_totals = [0] * n_simulations

    for m in match_results:
        mc = m.get("mc")
        if mc is None:
            continue
        samples = mc["point_samples"]
        for i in range(n_simulations):
            tournament_totals[i] += samples[i]

    total_ev = sum(m["ev"] for m in match_results)

    sorted_totals = sorted(tournament_totals)

    def percentile(pct: float) -> float:
        idx = int(pct / 100.0 * (n_simulations - 1))
        idx = max(0, min(n_simulations - 1, idx))
        return float(sorted_totals[idx])

    n = float(n_simulations)
    mc_mean = sum(tournament_totals) / n
    mc_var = sum((t - mc_mean) ** 2 for t in tournament_totals) / n
    mc_std = math.sqrt(mc_var)

    return {
        "n_matches": n_matches,
        "total_ev": total_ev,
        "total_mc_mean": mc_mean,
        "total_mc_std": mc_std,
        "p5": percentile(5),
        "p25": percentile(25),
        "p50": percentile(50),
        "p75": percentile(75),
        "p95": percentile(95),
    }


# ===========================================================================
# 6. FORMATTERS
# ===========================================================================

def format_table(match_results: List[Dict[str, Any]], show_mc: bool) -> str:
    """Pretty-print a text table of match predictions."""
    lines: List[str] = []

    header = (
        f"{'#':>3}  {'Match':<35} {'Tip':>5}  {'EV':>6}"
    )
    if show_mc:
        header += f"  {'MC μ':>6}  {'MC σ':>6}  {'P(0)':>6}  {'P(2)':>6}  {'P(3)':>6}  {'P(4)':>6}"
    lines.append(header)
    lines.append("-" * len(header))

    for i, m in enumerate(match_results, start=1):
        tip = m["optimal_tip"]
        match_label = f"{m['team_a']} vs {m['team_b']}"
        if len(match_label) > 33:
            match_label = match_label[:33] + ".."
        row = f"{i:>3}  {match_label:<35} {tip[0]}:{tip[1]:>2}  {m['ev']:>6.3f}"

        if show_mc and m.get("mc"):
            mc = m["mc"]
            row += (
                f"  {mc['mean_points']:>6.3f}"
                f"  {mc['std_points']:>6.3f}"
                f"  {mc['p0']:>6.1%}"
                f"  {mc['p2']:>6.1%}"
                f"  {mc['p3']:>6.1%}"
                f"  {mc['p4']:>6.1%}"
            )
        lines.append(row)

    return "\n".join(lines)


def format_tournament_summary(agg: Dict[str, Any]) -> str:
    """Pretty-print tournament aggregate summary."""
    lines = [
        "",
        "=" * 60,
        "TOURNAMENT SUMMARY",
        "=" * 60,
        f"  Matches:              {agg['n_matches']}",
        f"  Total EV (analytic):  {agg['total_ev']:.3f} pts",
        f"  Total MC mean:        {agg['total_mc_mean']:.3f} pts",
        f"  Total MC std:         {agg['total_mc_std']:.3f} pts",
        "",
        "  Confidence intervals (Monte Carlo):",
        f"     5th percentile:   {agg['p5']:.0f} pts",
        f"    25th percentile:   {agg['p25']:.0f} pts",
        f"    50th percentile:   {agg['p50']:.0f} pts  (median)",
        f"    75th percentile:   {agg['p75']:.0f} pts",
        f"    95th percentile:   {agg['p95']:.0f} pts",
        "=" * 60,
    ]
    return "\n".join(lines)


def build_json_output(
    match_results: List[Dict[str, Any]],
    agg: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a JSON-serialisable output dict."""
    matches_out = []
    for m in match_results:
        entry: Dict[str, Any] = {
            "team_a": m["team_a"],
            "team_b": m["team_b"],
            "phase": m.get("phase", ""),
            "lambda_base_a": round(m["lambda_base_a"], 4),
            "lambda_base_b": round(m["lambda_base_b"], 4),
            "lambda_adj_a": round(m["lambda_adj_a"], 4),
            "lambda_adj_b": round(m["lambda_adj_b"], 4),
            "optimal_tip": f"{m['optimal_tip'][0]}:{m['optimal_tip'][1]}",
            "ev": round(m["ev"], 4),
            "prob_home": round(m["prob_home"], 4),
            "prob_draw": round(m["prob_draw"], 4),
            "prob_away": round(m["prob_away"], 4),
            "top5_tips": [
                {"tip": f"{t[0]}:{t[1]}", "ev": round(e, 4)}
                for (t, e) in m.get("top5_tips", [])
            ],
        }
        if m.get("mc"):
            mc = m["mc"]
            entry["mc"] = {
                "mean_points": round(mc["mean_points"], 4),
                "std_points": round(mc["std_points"], 4),
                "p0": round(mc["p0"], 4),
                "p2": round(mc["p2"], 4),
                "p3": round(mc["p3"], 4),
                "p4": round(mc["p4"], 4),
            }
        matches_out.append(entry)

    result: Dict[str, Any] = {"matches": matches_out}
    if agg is not None:
        result["tournament"] = {
            "n_matches": agg["n_matches"],
            "total_ev": round(agg["total_ev"], 4),
            "total_mc_mean": round(agg["total_mc_mean"], 4),
            "total_mc_std": round(agg["total_mc_std"], 4),
            "percentiles": {
                "p5": agg["p5"],
                "p25": agg["p25"],
                "p50": agg["p50"],
                "p75": agg["p75"],
                "p95": agg["p95"],
            },
        }
    return result


# ===========================================================================
# 7. MAIN DRIVER
# ===========================================================================

def run_simulation(
    csv_path: str,
    n_simulations: int = 10_000,
    config_path: Optional[str] = None,
    rng_seed: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """High-level API: load CSV, predict all matches, run MC, aggregate.

    Returns (match_results, tournament_aggregate).  ``tournament_aggregate``
    is ``None`` when *n_simulations* is 0.
    """
    if config_path:
        predictor.load_config(config_path)

    rows = load_prediction_csv(csv_path)
    match_results: List[Dict[str, Any]] = []

    for row in rows:
        pred = predict_match(row)
        if n_simulations > 0:
            mc = monte_carlo_match(
                grid=pred["grid"],
                tip=pred["optimal_tip"],
                n_simulations=n_simulations,
                pts_exact=pred["config"].pts_exact,
                pts_diff=pred["config"].pts_diff,
                pts_tend=pred["config"].pts_tend,
                rng_seed=rng_seed,
            )
            pred["mc"] = mc
        match_results.append(pred)

    agg: Optional[Dict[str, Any]] = None
    if n_simulations > 0:
        agg = aggregate_tournament(match_results, n_simulations)

    return match_results, agg


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Monte Carlo Tournament Simulator – WM 2026 Kicktipp Predictor",
    )
    parser.add_argument(
        "--csv", type=str, required=True,
        help="Path to the prediction-mode CSV (no goals columns).",
    )
    parser.add_argument(
        "--simulations", type=int, default=10_000,
        help="Number of Monte Carlo simulations per match (default: 10000, 0 to skip MC).",
    )
    parser.add_argument(
        "--json", action="store_true", default=False,
        help="Output structured JSON instead of human-readable table.",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config.json with predictor constants.",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write output to file instead of stdout.",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="RNG seed for reproducible Monte Carlo runs.",
    )
    args = parser.parse_args()

    match_results, agg = run_simulation(
        csv_path=args.csv,
        n_simulations=args.simulations,
        config_path=args.config,
        rng_seed=args.seed,
    )

    # ------- Format output -------
    if args.json:
        output_text = json.dumps(
            build_json_output(match_results, agg), indent=2, ensure_ascii=False,
        )
    else:
        parts: List[str] = []
        parts.append(f"Loaded {len(match_results)} matches from {args.csv}")
        parts.append("")

        # Per-match detail lines
        for i, m in enumerate(match_results, start=1):
            tip = m["optimal_tip"]
            parts.append(
                f"Match {i}: {m['team_a']} vs {m['team_b']} "
                f"[{m.get('phase', '')}]"
            )
            parts.append(
                f"  λ_base: {m['lambda_base_a']:.3f} / {m['lambda_base_b']:.3f}  "
                f"→  λ_adj: {m['lambda_adj_a']:.3f} / {m['lambda_adj_b']:.3f}"
            )
            parts.append(
                f"  P(Home)={m['prob_home']:.1%}  P(Draw)={m['prob_draw']:.1%}  "
                f"P(Away)={m['prob_away']:.1%}"
            )
            parts.append(f"  ★ Optimal tip: {tip[0]}:{tip[1]}  (EV = {m['ev']:.3f} pts)")
            if m.get("mc"):
                mc = m["mc"]
                parts.append(
                    f"  MC ({args.simulations:,} sims): "
                    f"μ={mc['mean_points']:.3f}  σ={mc['std_points']:.3f}  "
                    f"P(0)={mc['p0']:.1%}  P(2)={mc['p2']:.1%}  "
                    f"P(3)={mc['p3']:.1%}  P(4)={mc['p4']:.1%}"
                )
            parts.append("")

        # Summary table
        show_mc = args.simulations > 0
        parts.append(format_table(match_results, show_mc=show_mc))

        if agg is not None:
            parts.append(format_tournament_summary(agg))

        output_text = "\n".join(parts)

    # ------- Write -------
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output_text)
            fh.write("\n")
        print(f"Output written to {args.output}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
