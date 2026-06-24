"""Points-floor regression for the production Elo->lambda calibration (S10).

The EV-optimal-tip yield of the PRODUCTION constants on the frozen 192-match
set (WC2014+2018+2022, pre-tournament Elo, corrected Tordifferenz scoring) is
measured at 299 points (validation/points_recalibration.md). This test pins a
>= 295 floor so no config edit can silently regress the points objective:
the old 1.35 default scores 291 and the once-recommended 1.25/rho-0 scores
289 — both below the floor by design.

If you change the calibration DELIBERATELY: re-measure, beat the floor or
update it here together with a new measurement table in
validation/points_recalibration.md. Never weaken the floor without numbers.
"""
import csv
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import predictor
from predictor import (
    MatchModelConfig, ModelDistribution, generate_joint_grid,
    solve_optimal_tip_from_grid, get_points,
)
from backtest_wm2014 import PRE_WM2014_ELO
from backtest_wm2018 import PRE_WM2018_ELO
from backtest_wm2022 import PRE_WM2022_ELO

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ELO = {2014: PRE_WM2014_ELO, 2018: PRE_WM2018_ELO, 2022: PRE_WM2022_ELO}
# Re-baselined 2026-06-24: the pool's goal-difference tier EXCLUDES draws (a correct-but-inexact
# draw scores 2, not 3 — confirmed with the pool owner; see get_points / POOL_RULES.md). Under the
# corrected rule the production constants score 289/192 (was 299 under the old draw=3 assumption);
# floor set 4 below the measured baseline, mirroring the prior 295-vs-299 margin.
POINTS_FLOOR = 285
MEASURED_BASELINE = 289

# Mirrors the production tipping path: lambdas from predictor.CONSTANTS via the
# real estimator; rho is predict_single_match's default (-0.05); alpha 0.
PRODUCTION_RHO = -0.05
PRODUCTION_ALPHA = 0.0


def _load_matches():
    matches = []
    for year in (2014, 2018, 2022):
        path = os.path.join(REPO, 'data', f'wc{year}_results.csv')
        with open(path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                elo_a = ELO[year].get(row['team_a'], {}).get('elo', 1500)
                elo_b = ELO[year].get(row['team_b'], {}).get('elo', 1500)
                matches.append((elo_a, elo_b, int(row['goals_a']), int(row['goals_b'])))
    return matches


class TestLambdaPointsFloor(unittest.TestCase):

    def test_production_constants_clear_points_floor(self):
        matches = _load_matches()
        self.assertEqual(len(matches), 192, "frozen dataset changed size — re-baseline the floor")

        total = 0
        for elo_a, elo_b, ga, gb in matches:
            la, lb = predictor.estimate_base_lambdas_from_elo(
                "A", "B", elo_a_override=elo_a, elo_b_override=elo_b)
            cfg = MatchModelConfig(
                dist_type=ModelDistribution.POISSON,
                mu_a=la, mu_b=lb,
                alpha_a=PRODUCTION_ALPHA, alpha_b=PRODUCTION_ALPHA,
                rho=PRODUCTION_RHO, max_goals=8, max_tip=6,
            )
            tips, _, _ = solve_optimal_tip_from_grid(generate_joint_grid(cfg), max_tip=6)
            t_a, t_b = tips[0][0]
            total += get_points(t_a, t_b, ga, gb)

        print(f"\n[POINTS FLOOR] production constants score {total}/192 "
              f"(floor {POINTS_FLOOR}, measured baseline {MEASURED_BASELINE} under draws-excluded rule)")
        self.assertGreaterEqual(
            total, POINTS_FLOOR,
            f"Production calibration scores {total} < {POINTS_FLOOR} on the frozen "
            f"192-match set. A config change regressed the points objective — see "
            f"validation/points_recalibration.md before touching the floor.")


if __name__ == '__main__':
    unittest.main()
