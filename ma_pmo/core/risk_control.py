"""A review threshold with a guarantee: of the decisions committed without a person, at most α
are wrong (roadmap 11, step 2).

The fixed `HITL_CONFIDENCE_THRESHOLD` (0.6) says nothing about how many wrong decisions get
through. With calibration data (held-out decisions with their confidence and whether they were
right), a threshold τ can be chosen so that the error rate among decisions at or above τ is at
most α with probability 1 − δ:

1. candidate thresholds are the confidence values seen, tested from the highest down (fixed
   sequence testing, so testing many candidates costs no extra error, as in Learn-then-Test,
   Angelopoulos et al. 2021);
2. at each τ, the errors among the decisions at or above it get a one-sided Clopper–Pearson
   upper bound at level 1 − δ;
3. the lowest τ whose bound is at most α wins; the first that fails stops the search.

If no τ passes, every decision goes to a person. Set `HITL_RISK_ALPHA` (and optionally
`HITL_RISK_DELTA`, default 0.1) to use it for A4's alerts, with A4's calibration table
(`agents/risk_calibration.py`) as the calibration data; other agents keep the fixed threshold.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

NOBODY = 1.01  # a threshold no confidence reaches: everything is reviewed


@dataclass(frozen=True)
class Group:
    confidence: float
    n: int
    errors: int


def _binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    lp, lq = math.log(p), math.log1p(-p)
    total = 0.0
    for i in range(k + 1):
        total += math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                          + i * lp + (n - i) * lq)
    return min(1.0, total)


def upper_bound(errors: int, n: int, delta: float) -> float:
    """One-sided Clopper–Pearson upper bound on an error rate, at level 1 − δ."""
    if n == 0:
        return 1.0
    if errors >= n:
        return 1.0
    lo, hi = errors / n, 1.0
    for _ in range(60):  # bisection: the p at which P(X <= errors) falls to δ
        mid = (lo + hi) / 2
        if _binom_cdf(errors, n, mid) > delta:
            lo = mid
        else:
            hi = mid
    return hi


def threshold(groups: Iterable[Group], alpha: float, delta: float = 0.1) -> float:
    """The lowest confidence threshold whose committed decisions are wrong at most α of the
    time with probability 1 − δ, or `NOBODY` if none."""
    groups = sorted(groups, key=lambda g: -g.confidence)
    best, n, errors = NOBODY, 0, 0
    for g in groups:
        n, errors = n + g.n, errors + g.errors
        if upper_bound(errors, n, delta) > alpha:
            break
        best = g.confidence
    return best


def a4_threshold(alpha: float, delta: float = 0.1) -> float:
    """The threshold for A4's alerts, from its calibration table's held-out counts."""
    from ma_pmo.agents.risk_calibration import load

    table = load()
    groups = [Group(table["kinds"][k]["rate"], c["n"], c["n"] - c["slipped"])
              for k, c in table["test"]["kinds"].items()]
    return threshold(groups, alpha, delta)


def threshold_for(sender: str, default: float) -> float:
    """The review threshold for a message from `sender`."""
    from ma_pmo.core.config import get_settings

    settings = get_settings()
    if sender == "A4" and settings.hitl_risk_alpha is not None:
        return a4_threshold(settings.hitl_risk_alpha, settings.hitl_risk_delta)
    return default
