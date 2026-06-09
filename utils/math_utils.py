"""Market de-vigging utilities.

Shin's Method (Shin 1992, 1993) recovers fair outcome probabilities from
bookmaker / exchange implied probabilities by modelling a market made up of
ordinary bettors plus a proportion ``z`` of insider ("sharp") traders. It
corrects the favourite–longshot bias that simple proportional normalisation
leaves in place.

IMPORTANT — there is **no** closed-form solution for ``z`` with three or more
outcomes; the 1X2 / multi-outcome estimator is solved **iteratively**
(Newton–Raphson with a bisection fallback). Earlier revisions of this module
shipped a quadratic stand-in (``p_i = (1-z)·pi_i^2 + z·pi_i``) mislabelled as the
"exact analytic solution"; it returned a meaningless ``z`` (~0.9 on normal
football odds vs. a true ~0.03). That has been removed — see
``validation/SHIN_EVALUATION.md``.
"""

import math
from typing import List, Sequence, Tuple


def _shin_probs_given_z(pi: Sequence[float], booksum: float, z: float) -> List[float]:
    """Shin true-probability for each outcome at a fixed ``z`` (unnormalised)."""
    out = []
    for p in pi:
        q = (p * p) / booksum
        u = z * z + 4.0 * (1.0 - z) * q
        out.append((math.sqrt(u) - z) / (2.0 * (1.0 - z)))
    return out


def devig_shin(pi: Sequence[float], tol: float = 1e-10, max_iter: int = 100) -> Tuple[List[float], float]:
    """De-vig an N-outcome market book with Shin's Method.

    Args:
        pi: raw implied probabilities (inverse decimal odds), summing to the
            booksum ``B = 1 + overround``.

    Returns:
        ``(probs, z)`` where ``probs`` are fair probabilities summing to 1.0 and
        ``z`` is the estimated insider proportion in ``[0, 1)``.

    Degenerate inputs fall back to proportional normalisation with ``z = 0``:
      * ``B <= 1`` (no positive overround — exact-fair books, arbitrage, and
        zero-margin prediction markets such as Polymarket): Shin is undefined,
        so we normalise.
      * all-zero input: uniform distribution.
    """
    pi = [max(0.0, float(p)) for p in pi]
    n = len(pi)
    if n == 0:
        return [], 0.0

    booksum = sum(pi)
    if booksum <= 0.0:
        return [1.0 / n] * n, 0.0

    # No (positive) overround -> Shin undefined; proportional normalisation.
    if booksum <= 1.0 + 1e-12:
        return [p / booksum for p in pi], 0.0

    def sum_minus_one(z: float) -> float:
        return sum(_shin_probs_given_z(pi, booksum, z)) - 1.0

    # Newton-Raphson on f(z) = sum_i p_i(z) - 1 (monotonically decreasing in z),
    # seeded from the overround. Analytic derivative; backtrack to stay in (0,1).
    z = min(0.5, max(1e-6, (booksum - 1.0) / booksum))
    converged = False
    for _ in range(max_iter):
        s = 0.0
        ds = 0.0
        for p in pi:
            q = (p * p) / booksum
            u = z * z + 4.0 * (1.0 - z) * q
            su = math.sqrt(u)
            s += (su - z) / (2.0 * (1.0 - z))
            # d/dz p_i(z) = (2(1-z)q + z - sqrt(u)) / (2 (1-z)^2 sqrt(u))
            ds += (2.0 * (1.0 - z) * q + z - su) / (2.0 * (1.0 - z) ** 2 * su)
        f = s - 1.0
        if abs(f) < tol:
            converged = True
            break
        if abs(ds) < 1e-15:
            break
        step = f / ds
        z_new = z - step
        backtrack = 0.5
        while (z_new <= 0.0 or z_new >= 1.0) and backtrack > 1e-4:
            step *= backtrack
            z_new = z - step
            backtrack *= 0.5
        if z_new <= 0.0 or z_new >= 1.0:
            break
        z = z_new

    if not converged:
        # Bisection fallback: f(0+) = sqrt(B) - 1 > 0, decreasing in z.
        lo, hi = 0.0, 1.0 - 1e-9
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if sum_minus_one(mid) > 0.0:
                lo = mid
            else:
                hi = mid
        z = 0.5 * (lo + hi)

    z = max(0.0, min(0.9999, z))
    probs = [max(0.0, p) for p in _shin_probs_given_z(pi, booksum, z)]
    total = sum(probs)
    if total <= 0.0:
        return [1.0 / n] * n, 0.0
    return [p / total for p in probs], z


def strip_vig_shin(pi_h: float, pi_d: float, pi_a: float) -> Tuple[Tuple[float, float, float], float]:
    """De-vig 1X2 implied probabilities with Shin's Method (iterative).

    Thin 3-outcome wrapper around :func:`devig_shin` preserving the historical
    ``((p_home, p_draw, p_away), z)`` return shape used by ``odds_client`` and
    ``predictor``.

    Args:
        pi_h/pi_d/pi_a: implied probabilities (e.g. ``1.0 / decimal_odds``).

    Returns:
        ``((p_home, p_draw, p_away), z)`` with fair probabilities summing to 1.0
        and the estimated insider proportion ``z in [0, 1)``.
    """
    probs, z = devig_shin([pi_h, pi_d, pi_a])
    if len(probs) != 3:
        return (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0), 0.0
    return (probs[0], probs[1], probs[2]), z


def devig_book(implied: Sequence[float], method: str = "shin") -> List[float]:
    """De-vig a complete mutually-exclusive market book; returns probs summing to 1.

    Args:
        implied: raw implied probabilities (inverse decimal odds) for every
            outcome in the book.
        method: ``"shin"`` (favourite–longshot aware) or ``"basic"``
            (proportional / multiplicative normalisation).

    Books with no positive overround are normalised proportionally regardless of
    ``method``.
    """
    vals = [max(0.0, float(x)) for x in implied]
    n = len(vals)
    if n == 0:
        return []
    total = sum(vals)
    if total <= 0.0:
        return [1.0 / n] * n
    if method == "basic" or total <= 1.0 + 1e-12:
        return [v / total for v in vals]
    probs, _z = devig_shin(vals)
    return probs
