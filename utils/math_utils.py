import math
from typing import Tuple

def strip_vig_shin(pi_h: float, pi_d: float, pi_a: float) -> Tuple[Tuple[float, float, float], float]:
    """
    De-vigs 1X2 implied probabilities using the exact analytic solution to Shin's Method.
    
    Shin's Method accounts for the Favorite-Longshot Bias by modeling a market 
    consisting of typical bettors and a proportion z of insider (sharp) bettors.
    
    Args:
        pi_h: Implied probability of home win (e.g. 1.0 / decimal_odds_home)
        pi_d: Implied probability of draw (e.g. 1.0 / decimal_odds_draw)
        pi_a: Implied probability of away win (e.g. 1.0 / decimal_odds_away)
        
    Returns:
        A tuple of ((p_home, p_draw, p_away), z) where:
          - p_home, p_draw, p_away are fair probabilities summing to 1.0
          - z is the estimated proportion of insider/sharp volume (z in [0, 1))
    """
    pi = [pi_h, pi_d, pi_a]
    sum_pi = sum(pi)
    sum_pi_sq = sum(p**2 for p in pi)
    
    # Fallback to basic normalization if no overround exists (e.g. arbitrage), 
    # or if extreme odds violate Shin's core assumption (sum_pi_sq >= 1.0)
    if sum_pi <= 1.0 or sum_pi_sq >= 1.0:
        p_norm = tuple(p / sum_pi if sum_pi > 0 else 1.0/3.0 for p in pi)
        return (p_norm[0], p_norm[1], p_norm[2]), 0.0
        
    # Exact analytic solution for the insider proportion z
    z = (sum_pi_sq - 1.0) / (sum_pi_sq - sum_pi)
    
    # Clamp z to [0.0, 1.0) to ensure mathematical validity
    z = max(0.0, min(0.9999, z))
    
    # Back-calculate the true probabilities
    p = tuple((1.0 - z) * (p**2) + z * p for p in pi)
    
    # Final normalization to ensure sum is exactly 1.0
    sum_p = sum(p)
    if sum_p > 0:
        p_final = tuple(x / sum_p for x in p)
    else:
        p_final = (1.0/3.0, 1.0/3.0, 1.0/3.0)
        
    return (p_final[0], p_final[1], p_final[2]), z
