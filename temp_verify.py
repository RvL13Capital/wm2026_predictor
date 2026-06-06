import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import predictor
from solver import get_points

TEAM_STATS = {
    "Qatar": {"off": 0.8, "def": 1.4}, "Ecuador": {"off": 1.1, "def": 1.0}, "Senegal": {"off": 1.2, "def": 1.1}, "Netherlands": {"off": 1.5, "def": 0.8}, "England": {"off": 1.8, "def": 0.7}, "Iran": {"off": 0.9, "def": 1.2}, "USA": {"off": 1.1, "def": 0.9}, "Wales": {"off": 0.8, "def": 1.3}, "Argentina": {"off": 1.9, "def": 0.7}, "Saudi Arabia": {"off": 0.9, "def": 1.3}, "Mexico": {"off": 1.1, "def": 1.0}, "Poland": {"off": 1.0, "def": 1.1}, "France": {"off": 2.0, "def": 0.8}, "Australia": {"off": 1.0, "def": 1.1}, "Denmark": {"off": 1.2, "def": 0.9}, "Tunisia": {"off": 0.9, "def": 1.0}, "Spain": {"off": 1.7, "def": 0.8}, "Costa Rica": {"off": 0.7, "def": 1.5}, "Germany": {"off": 1.6, "def": 1.0}, "Japan": {"off": 1.3, "def": 1.0}, "Belgium": {"off": 1.3, "def": 1.0}, "Canada": {"off": 1.0, "def": 1.3}, "Morocco": {"off": 1.3, "def": 0.6}, "Croatia": {"off": 1.4, "def": 0.8}, "Brazil": {"off": 2.0, "def": 0.7}, "Serbia": {"off": 1.2, "def": 1.3}, "Switzerland": {"off": 1.2, "def": 1.0}, "Cameroon": {"off": 1.1, "def": 1.2}, "Portugal": {"off": 1.7, "def": 0.9}, "Ghana": {"off": 1.1, "def": 1.4}, "Uruguay": {"off": 1.1, "def": 0.9}, "South Korea": {"off": 1.1, "def": 1.1}
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

def make_context(row, suffix):
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

def run(model_type):
    total = 0
    for row in FALLBACK_MATCHES:
        ta, tb = row["team_a"], row["team_b"]
        ga, gb = row["goals_a"], row["goals_b"]
        sa, sb = TEAM_STATS[ta], TEAM_STATS[tb]
        mu_a = sa["off"] * sb["def"]
        mu_b = sb["off"] * sa["def"]
        if model_type == "baseline":
            config = predictor.MatchModelConfig(
                dist_type=predictor.ModelDistribution.POISSON,
                mu_a=mu_a, mu_b=mu_b, alpha_a=0.0, alpha_b=0.0, rho=0.0
            )
        else:
            ctx_a = make_context(row, "a")
            ctx_b = make_context(row, "b")
            mu_a_adj, mu_b_adj = predictor.get_adjusted_lambdas(mu_a, mu_b, ctx_a, ctx_b)
            dist = predictor.ModelDistribution.NEGATIVE_BINOMIAL if (row["alpha_a"] > 0 or row["alpha_b"] > 0) else predictor.ModelDistribution.POISSON
            config = predictor.MatchModelConfig(
                dist_type=dist,
                mu_a=mu_a_adj, mu_b=mu_b_adj, alpha_a=row["alpha_a"], alpha_b=row["alpha_b"], rho=row["rho"]
            )
        tips, _, _ = predictor.solve_optimal_tip(config)
        tip = tips[0][0]
        pts = get_points(tip[0], tip[1], ga, gb)
        total += pts
        print(f"{model_type}: {ta}-{tb} (act {ga}:{gb}) -> tip {tip[0]}:{tip[1]} | pts: {pts} | mus: {config.mu_a:.3f}, {config.mu_b:.3f}")
    print(f"Total for {model_type}: {total}")

run("baseline")
run("optimized")
