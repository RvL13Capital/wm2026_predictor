#!/usr/bin/env python3
"""Quick smoke test for tournament_sim.py – verifies the tool runs end-to-end."""
import os, sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import tournament_sim as ts

# --- Test 1: CSV loader ---
print("=== Test 1: CSV Loader ===")
rows = ts.load_prediction_csv(os.path.join(_DIR, "data", "test_3matches.csv"))
assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
assert rows[0]["team_a"] == "Germany"
assert rows[0]["team_b"] == "Japan"
print(f"  Loaded {len(rows)} rows: OK")

# --- Test 2: Single-match prediction ---
print("\n=== Test 2: Single-match prediction ===")
pred = ts.predict_match(rows[0])
assert pred["team_a"] == "Germany"
assert isinstance(pred["optimal_tip"], tuple)
assert pred["ev"] > 0.0
tip = pred["optimal_tip"]
print(f"  Germany vs Japan → tip {tip[0]}:{tip[1]}, EV={pred['ev']:.3f}")
print(f"  P(Home)={pred['prob_home']:.1%}  P(Draw)={pred['prob_draw']:.1%}  P(Away)={pred['prob_away']:.1%}")
print("  OK")

# --- Test 3: Monte Carlo per match ---
print("\n=== Test 3: Monte Carlo (1000 sims) ===")
mc = ts.monte_carlo_match(pred["grid"], pred["optimal_tip"], n_simulations=1000, rng_seed=42)
assert 0.0 <= mc["mean_points"] <= 4.0
assert mc["std_points"] >= 0.0
total_p = mc["p0"] + mc["p2"] + mc["p3"] + mc["p4"]
assert abs(total_p - 1.0) < 0.01, f"Point probabilities sum to {total_p}, expected ~1.0"
print(f"  μ={mc['mean_points']:.3f}  σ={mc['std_points']:.3f}")
print(f"  P(0)={mc['p0']:.1%}  P(2)={mc['p2']:.1%}  P(3)={mc['p3']:.1%}  P(4)={mc['p4']:.1%}")
print("  OK")

# --- Test 4: Full pipeline with run_simulation ---
print("\n=== Test 4: Full pipeline (3 matches, 1000 sims) ===")
results, agg = ts.run_simulation(
    csv_path=os.path.join(_DIR, "data", "test_3matches.csv"),
    n_simulations=1000,
    rng_seed=42,
)
assert len(results) == 3
assert agg is not None
assert agg["n_matches"] == 3
assert agg["total_ev"] > 0
print(f"  Total EV: {agg['total_ev']:.3f}")
print(f"  MC mean: {agg['total_mc_mean']:.3f}, std: {agg['total_mc_std']:.3f}")
print(f"  Percentiles: 5th={agg['p5']:.0f}  50th={agg['p50']:.0f}  95th={agg['p95']:.0f}")
print("  OK")

# --- Test 5: JSON output ---
print("\n=== Test 5: JSON serialisation ===")
import json
j = ts.build_json_output(results, agg)
json_str = json.dumps(j, indent=2)
assert "matches" in j
assert "tournament" in j
assert len(j["matches"]) == 3
print(f"  JSON output: {len(json_str)} chars, {len(j['matches'])} matches")
print("  OK")

# --- Test 6: Text table ---
print("\n=== Test 6: Text table ===")
table = ts.format_table(results, show_mc=True)
print(table)
print("  OK")

# --- Test 7: Tournament summary ---
print("\n=== Test 7: Tournament summary ===")
summary = ts.format_tournament_summary(agg)
print(summary)
print("  OK")

print("\n✅ All tests passed!")
