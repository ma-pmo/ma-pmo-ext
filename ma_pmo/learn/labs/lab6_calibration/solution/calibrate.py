"""Lab 6 reference solution: measure calibration and choose an approval threshold."""
from __future__ import annotations


def brier(pairs: list[tuple[float, bool]]) -> float:
    """Mean squared gap between confidence and outcome (1 = right, 0 = wrong)."""
    return sum((c - ok) ** 2 for c, ok in pairs) / len(pairs)


def ece(pairs: list[tuple[float, bool]], bins: int = 10) -> float:
    """Expected calibration error over equal-width bins of confidence."""
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        members = [(c, ok) for c, ok in pairs
                   if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if members:
            conf = sum(c for c, _ in members) / len(members)
            acc = sum(ok for _, ok in members) / len(members)
            total += len(members) / len(pairs) * abs(acc - conf)
    return total


def choose_threshold(pairs: list[tuple[float, bool]], max_review: int,
                     candidates: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)) -> float:
    """The threshold that lets the fewest wrong outputs through without sending more than
    `max_review` messages to a person (ties: the lower threshold, i.e. less review)."""
    best: tuple[int, float] | None = None
    for t in sorted(candidates):
        if sum(c < t for c, _ in pairs) > max_review:
            continue
        slipped = sum(c >= t and not ok for c, ok in pairs)
        if best is None or slipped < best[0]:
            best = (slipped, t)
    if best is None:
        raise ValueError("no threshold fits the review budget")
    return best[1]
