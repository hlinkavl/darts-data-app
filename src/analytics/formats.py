"""Convert a "typical match" win probability into any match format (first to N legs, or first to N sets).

The PI model predicts matches in the typical data format, first to 6 legs. We back out the probability of
winning a single leg from that, then build any longer or shorter format from legs:

    P(win a race to n) = sum_{k=0}^{n-1} C(n-1+k, k) * p^n * (1-p)^k      (opponent wins k < n units first)

A set is a race to 3 legs (World Championship, World Grand Prix). Simplifications, documented in
docs/TOURNAMENT_PREDICTIONS.md: legs are independent with the same p (the advantage of throwing first is
averaged out) and "win by two clear legs" in deciding sets/legs is ignored.
"""

from math import comb

TYPICAL_FIRST_TO = 6
LEGS_PER_SET = 3


def race(p: float, n: int) -> float:
    """Probability of reaching n won units (legs or sets) before the opponent."""
    q = 1.0 - p
    return sum(comb(n - 1 + k, k) * p**n * q**k for k in range(n))


def leg_probability(p_typical: float, typical_first_to: int = TYPICAL_FIRST_TO) -> float:
    """Leg win probability that reproduces p_typical in a race to typical_first_to legs (bisection)."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if race(mid, typical_first_to) < p_typical:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def match_probability(p_typical: float, first_to: int, unit: str = "legs") -> float:
    """P(win) in a match of `first_to` legs or sets, given P(win) in a typical match."""
    p_leg = leg_probability(p_typical)
    if unit == "legs":
        return race(p_leg, first_to)
    if unit == "sets":
        return race(race(p_leg, LEGS_PER_SET), first_to)
    raise ValueError(f"unknown unit {unit!r}")
