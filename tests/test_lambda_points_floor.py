"""Points-floor regression for the production Elo->lambda calibration (S10).

The EV-optimal-tip yield of the PRODUCTION constants on the frozen 192-match
set (WC2014+2018+2022, pre-tournament Elo) under the operator-VERIFIED pool
scoring is measured at 289 points. This test pins a >= 285 floor so no config
edit can silently regress the points objective.

SCORING CORRECTION (2026-06-27): a non-exact draw tip on a draw result scores
the TENDENCY points (2), NOT pts_diff (3) — the operator verified this against
real Kicktipp results, correcting the earlier G1 "Tordifferenz includes draws"
assumption. The fix (get_points + solve_optimal_tip_from_grid draw branch) cost
~10 pts vs the old (wrong) 299/floor-295 figures. CAVEAT: elo_baseline_goals=1.0
was calibrated to EXPLOIT the wrong draws=3 rule (low lambda -> 0:0 tips); under
draws=2 it may no longer be points-optimal — flagged for the post-tournament
recalibration (validation/points_recalibration.md).

If you change the calibration DELIBERATELY: re-measure, beat the floor or update
it here together with a new measurement in validation/points_recalibration.md.
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
POINTS_FLOOR = 285   # was 295 under the wrong draws=3 rule; production now 289 (draws=2)

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
              f"(floor {POINTS_FLOOR}, measured baseline 289 under draws=2)")
        self.assertGreaterEqual(
            total, POINTS_FLOOR,
            f"Production calibration scores {total} < {POINTS_FLOOR} on the frozen "
            f"192-match set. A config change regressed the points objective — see "
            f"validation/points_recalibration.md before touching the floor.")


if __name__ == '__main__':
    unittest.main()
