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


def kelly_mutually_exclusive(probs: Sequence[float], odds: Sequence[float],
                             fraction: float = 1.0) -> List[float]:
    """Simultaneous Kelly stakes for MUTUALLY EXCLUSIVE outcomes of one book.

    Sizing several legs of the same book (e.g. three outright-winner legs, or
    the 1/X/2 legs of one match) independently with the binary Kelly formula is
    not growth-optimal: each binary formula ignores that every other stake in
    the book is lost when its leg wins, and that mutually exclusive legs hedge
    one another (so the joint optimum can stake more OR less in aggregate).
    This implements the classical simultaneous-Kelly solution (Smoczynski &
    Tomkins 2010 / Thorp): maximize E[log(1 - Σf_j + f_i·o_i)] over stake
    fractions f.

    Algorithm: order outcomes by expected revenue p·o descending; greedily
    include outcome k while p_k·o_k > R(S), where the reserve rate
        R(S) = (1 - Σ_{i∈S} p_i) / (1 - Σ_{i∈S} 1/o_i)
    is the growth-optimal wealth fraction kept back; optimal stakes are
        f_i = p_i - R(S)/o_i   for i ∈ S, else 0.

    Args:
        probs: model probabilities of each outcome (need not sum to 1 — the
               remainder is the implicit "no bet pays" mass).
        odds:  decimal payout odds for each outcome (what the book actually pays).
        fraction: fractional-Kelly multiplier applied to the optimal stakes
                  (0.25 = quarter Kelly).

    Returns:
        Stake fractions of bankroll per outcome (0.0 for excluded legs).
    """
    n = len(probs)
    if n == 0 or len(odds) != n:
        return [0.0] * n

    order = sorted(range(n), key=lambda i: probs[i] * odds[i], reverse=True)
    included: List[int] = []
    reserve = 1.0
    sum_p = 0.0
    sum_inv = 0.0
    for k in order:
        p, o = float(probs[k]), float(odds[k])
        if p <= 0.0 or o <= 1.0:
            continue
        if p * o <= reserve:
            break                       # ordered by p·o, so no later leg qualifies
        new_sum_inv = sum_inv + 1.0 / o
        if 1.0 - new_sum_inv <= 1e-12:
            break                       # sub-book Σ1/o ≥ 1: inclusion can't be growth-optimal
        included.append(k)
        sum_p, sum_inv = sum_p + p, new_sum_inv
        # For a complete +EV book Σp→1 drives the reserve to 0 (stake the whole
        # bankroll, f_i = p_i) — that IS the Kelly optimum; clamp only guards
        # invalid inputs with Σp > 1.
        reserve = max(0.0, (1.0 - sum_p) / (1.0 - sum_inv))

    stakes = [0.0] * n
    for i in included:
        f = probs[i] - reserve / odds[i]
        if f > 0.0:
            stakes[i] = f
    # Practical cap: never stake literally 100% of bankroll (model error means
    # the residual no-payout state may exist even when Σp says it doesn't).
    total = sum(stakes)
    if total > 0.999:
        stakes = [s * (0.999 / total) for s in stakes]
    return [s * fraction for s in stakes]


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
