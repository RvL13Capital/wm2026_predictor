#!/usr/bin/env python3
"""
Context-magnitude calibration log (read-only; does NOT touch the sealed engine).

Why: the goal-total flag showed our deterministic context layer (altitude/WBGT/travel) systematically
predicts MORE goals than the market O/U, worst on altitude games. Before we *re-scale* that layer we
need EVIDENCE, accumulated over many matches/snapshots — not one screenshot. This tool logs, per
match per snapshot, the model's expected goals vs the market's, DECOMPOSED so the residual can be
attributed to its driver:

    elo_base  --(+context)-->  ctx_total  --(+market blend)-->  model_total   vs   market_total(O/U)
              ctx_effect                    blend_effect              residual = model_total - market_total

`residual - ctx_effect` = what the residual WOULD be with the context layer removed. If that is ~0,
the context over-boost is the whole story and the fix is to shrink it; if not, dispersion/Elo is.

Run it each matchday (and at T-24h / T-1h as the line sharpens) to accumulate. When N is large the
summary's altitude breakdown + context-attribution slope tell us the retain factor to fit — properly,
on real data, the way the rest of this repo earns its numbers.

    python3 validation/context_calibration_log.py --md 1 --odds-snapshot data/polymarket_match_odds.json
    python3 validation/context_calibration_log.py --summary-only      # just analyze the accumulated log

The submitted tips are untouched — this only *reads* model + market and appends rows.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import matchday_tips as M
import tournament_bonusfragen as tbf

DEFAULT_LOG = os.path.join(os.path.dirname(__file__), "..", "data", "context_calibration_log.jsonl")


def _is_altitude(home, away):
    """True if this fixture is at a >1000m venue (the headline context driver)."""
    return (home, away) in tbf.HIGH_ALTITUDE_MATCHES or (away, home) in tbf.HIGH_ALTITUDE_MATCHES


def observe(md, snapshot_path, label):
    """Run the matchday with and without the market blend; emit one decomposed row per match."""
    mp, mx = M.load_market_snapshot(snapshot_path)
    no_blend = {(r["team_a"], r["team_b"]): r for r in M.run_matchday(md, 0, 42, None, None)}
    blended = M.run_matchday(md, 0, 42, mp, mx)

    rows = []
    for b in blended:
        if b.get("market_total") is None:
            continue                                  # no O/U line for this fixture — skip
        key = (b["team_a"], b["team_b"])
        nb = no_blend.get(key)
        if not nb:
            continue
        elo_base = nb["lambda_base_a"] + nb["lambda_base_b"]
        ctx_total = nb["lambda_adj_a"] + nb["lambda_adj_b"]      # Elo + context (no blend)
        model_total = b["lambda_adj_a"] + b["lambda_adj_b"]      # final, blended (what we submit on)
        market_total = b["market_total"]
        rows.append({
            "label": label, "md": md, "home": b["team_a"], "away": b["team_b"],
            "elo_base": round(elo_base, 4),
            "ctx_total": round(ctx_total, 4),
            "model_total": round(model_total, 4),
            "market_total": round(market_total, 4),
            "ctx_effect": round(ctx_total - elo_base, 4),         # pure context move
            "blend_effect": round(model_total - ctx_total, 4),    # pure market-blend move
            "residual": round(model_total - market_total, 4),     # what we want to drive to 0
            "altitude": _is_altitude(b["team_a"], b["team_b"]),
        })
    return rows


def append_log(rows, log_path):
    """Append, deduping on (label, md, home, away) so re-running a snapshot can't double-count."""
    existing, seen = [], set()
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                existing.append(r)
                seen.add((r["label"], r["md"], r["home"], r["away"]))
    new = [r for r in rows if (r["label"], r["md"], r["home"], r["away"]) not in seen]
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        for r in new:
            f.write(json.dumps(r) + "\n")
    return len(new), len(existing) + len(new)


def _ols(xs, ys):
    """Pure-stdlib slope + Pearson r of ys ~ xs."""
    n = len(xs)
    if n < 2:
        return None, None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    slope = sxy / sxx if sxx > 0 else 0.0
    r = sxy / ((sxx * syy) ** 0.5) if sxx > 0 and syy > 0 else 0.0
    return slope, r


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def summarize(log_path):
    if not os.path.exists(log_path):
        print(f"(no log yet at {log_path})")
        return
    rows = [json.loads(l) for l in open(log_path, encoding="utf-8") if l.strip()]
    if not rows:
        print("(log is empty)")
        return
    labels = sorted({r["label"] for r in rows})
    res = [r["residual"] for r in rows]
    ctx = [r["ctx_effect"] for r in rows]
    alt = [r for r in rows if r["altitude"]]
    non = [r for r in rows if not r["altitude"]]

    print("=" * 72)
    print(f"CONTEXT CALIBRATION LOG  —  {len(rows)} obs over {len(labels)} snapshot(s) [{labels[0]}..{labels[-1]}]")
    print("=" * 72)
    print(f"  mean residual (model E[goals] - market O/U):  {_mean(res):+.3f} goals   (target 0)")
    print(f"     of which mean context move:                {_mean(ctx):+.3f}   blend move: {_mean([r['blend_effect'] for r in rows]):+.3f}")
    print(f"  residual with context REMOVED (resid-ctx):    {_mean([r['residual']-r['ctx_effect'] for r in rows]):+.3f}   "
          f"(near 0 => context is the whole over-prediction)")
    print(f"  altitude games  (n={len(alt):2d}):  mean residual {_mean([r['residual'] for r in alt]):+.3f}   "
          f"mean context {_mean([r['ctx_effect'] for r in alt]):+.3f}")
    print(f"  non-altitude    (n={len(non):2d}):  mean residual {_mean([r['residual'] for r in non]):+.3f}   "
          f"mean context {_mean([r['ctx_effect'] for r in non]):+.3f}")
    slope, r = _ols(ctx, res)
    if slope is not None:
        print(f"  residual ~ context_effect:  slope {slope:+.2f}  (r={r:+.2f})  "
              f"-- slope>0 means more context => more over-prediction")
        if _mean(ctx) > 0.05:
            retain = max(0.0, 1.0 - _mean(res) / _mean(ctx))
            print(f"  directional context-retain hint: ~{retain:.0%} "
                  f"(scale needed for mean residual->0 IF context is the driver; FIT, don't ship, until N is large)")
    print("=" * 72)
    if len(labels) < 3:
        print("  NOTE: thin sample — keep logging each matchday/refresh before fitting anything.")


def main():
    ap = argparse.ArgumentParser(description="Accumulate model-vs-market goal-total deltas for context calibration")
    ap.add_argument("--md", type=int, choices=[1, 2, 3], help="Matchday to observe")
    ap.add_argument("--odds-snapshot", type=str, help="Polymarket JSON snapshot (with O/U extras)")
    ap.add_argument("--label", type=str, default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    help="Snapshot label (default: today UTC). One observation per (label, match).")
    ap.add_argument("--log", type=str, default=DEFAULT_LOG, help="JSONL log path")
    ap.add_argument("--summary-only", action="store_true", help="Just analyze the accumulated log")
    args = ap.parse_args()

    if not args.summary_only:
        if not (args.md and args.odds_snapshot):
            ap.error("--md and --odds-snapshot are required unless --summary-only")
        rows = observe(args.md, args.odds_snapshot, args.label)
        n_new, n_total = append_log(rows, args.log)
        print(f"[calib] md{args.md} {args.label}: {len(rows)} matches observed, {n_new} new appended "
              f"({n_total} total in log)", file=sys.stderr)
    summarize(args.log)


if __name__ == "__main__":
    main()
