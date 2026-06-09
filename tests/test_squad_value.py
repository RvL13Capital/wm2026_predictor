import unittest
import math
import sys
import os

# Add parent directory to path so we can import predictor
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import predictor
from predictor import get_adjusted_lambdas

class TestSquadValue(unittest.TestCase):
    
    def test_backward_compatibility(self):
        """Verify that default contexts with no team names or matching team names result in no squad adjustments."""
        # Scenario 1: Empty contexts (no team name)
        lambda_A, lambda_B = get_adjusted_lambdas(1.5, 1.5, {}, {})
        # With default team names (unknowns) falling back to 100.0 XI and 50.0 Bench,
        # the log ratios log(100/100) and log(50/50) are both 0.0.
        # Thus, squad adjustments are 0.0.
        # Since temp/humidity default to 20/0, elevation to 0, travel/rest is neutral, etc.,
        # the output should be exactly 1.5.
        self.assertAlmostEqual(lambda_A, 1.5)
        self.assertAlmostEqual(lambda_B, 1.5)
        
        # Scenario 2: Explicit unknown teams
        lambda_A_unkn, lambda_B_unkn = get_adjusted_lambdas(1.5, 1.5, {"team_name": "Atlantis"}, {"team_name": "Valhalla"})
        self.assertAlmostEqual(lambda_A_unkn, 1.5)
        self.assertAlmostEqual(lambda_B_unkn, 1.5)

    def test_squad_value_log_linear_advantage(self):
        """Verify that France (high squad value) has an advantage over Haiti (low squad value)."""
        # France total squad: 1550M, Haiti total squad: 56M
        # With ELO lambdas at 1.5 for both, France should get adjusted upwards, and Haiti downwards.
        lambda_FRA, lambda_HAI = get_adjusted_lambdas(
            1.5, 1.5,
            {"team_name": "France"},
            {"team_name": "Haiti"}
        )
        self.assertTrue(lambda_FRA > 1.5, f"France expected goals {lambda_FRA} should be > 1.5")
        self.assertTrue(lambda_HAI < 1.5, f"Haiti expected goals {lambda_HAI} should be < 1.5")

    def test_vorp_missing_starter_replacement(self):
        """Verify VORP replacement logic: injuries to starters reduce effective squad value and goals."""
        # Case A: France vs Haiti with no injuries
        lam_fra_healthy, _ = get_adjusted_lambdas(
            1.5, 1.5,
            {"team_name": "France"},
            {"team_name": "Haiti"}
        )
        
        # Case B: France vs Haiti with France missing 2 starters worth 120M total
        lam_fra_injured, _ = get_adjusted_lambdas(
            1.5, 1.5,
            {"team_name": "France", "missing_value": 120.0, "missing_count": 2},
            {"team_name": "Haiti"}
        )
        
        # Expected: France's expected goals should decline under injury, but still be above Haiti's base
        self.assertTrue(lam_fra_injured < lam_fra_healthy, "France xG should decline due to starter injuries")
        self.assertTrue(lam_fra_injured > 1.5, "France should still retain squad value advantage over Haiti")

    def test_thermal_shock_depth_scaling(self):
        """Verify that high WBGT increases the importance of bench depth."""
        # Team A has a better bench but worse starters than Team B
        # Team A: XI = 100.0, Bench = 200.0
        # Team B: XI = 200.0, Bench = 50.0
        ctx_A_cool = {"team_name": "Team A", "temp": 15.0, "humidity": 30.0}
        ctx_B_cool = {"team_name": "Team B", "temp": 15.0, "humidity": 30.0}
        
        # Inject custom squad values temporarily by patching predictor.SQUAD_VALUES
        orig_squad = predictor.SQUAD_VALUES
        predictor.SQUAD_VALUES = {
            "Team A": {"xi": 100.0, "bench": 200.0},
            "Team B": {"xi": 200.0, "bench": 50.0}
        }
        
        try:
            # Under cool conditions (wbgt < 20.0), thermal shock multiplier = 0
            lam_A_cool, lam_B_cool = get_adjusted_lambdas(1.5, 1.5, ctx_A_cool, ctx_B_cool)
            
            # Under hot conditions (wbgt > 20.0), thermal shock multiplier > 0
            # E.g., temp=38.0, humidity=80.0
            ctx_A_hot = {"team_name": "Team A", "temp": 38.0, "humidity": 80.0}
            ctx_B_hot = {"team_name": "Team B", "temp": 38.0, "humidity": 80.0}
            
            lam_A_hot, lam_B_hot = get_adjusted_lambdas(1.5, 1.5, ctx_A_hot, ctx_B_hot)
            
            # Heat causes general expected goals to drop (due to f_therm < 1.0)
            # But let's look at the relative ratio A / B.
            # Under hot conditions, Team A's bench advantage should be magnified, so the ratio A / B should improve for A.
            ratio_cool = lam_A_cool / lam_B_cool
            ratio_hot = lam_A_hot / lam_B_hot
            
            self.assertTrue(ratio_hot > ratio_cool, f"Bench-rich Team A should perform relatively better in extreme heat: ratio_hot={ratio_hot:.4f} vs ratio_cool={ratio_cool:.4f}")
            
        finally:
            predictor.SQUAD_VALUES = orig_squad

if __name__ == '__main__':
    unittest.main()
