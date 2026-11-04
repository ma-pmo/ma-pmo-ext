"""Lab 6: measure calibration and choose an approval threshold.

Each pair is (confidence, was_right). Fill in every TODO, then run `ma-pmo learn check 6`.
The lab guide is README.md; `ma_pmo/eval/calibration.py` is the full version used by
`ma-pmo eval` — try it yourself before you look.
"""
from __future__ import annotations


def brier(pairs: list[tuple[float, bool]]) -> float:
    """Mean squared gap between confidence and outcome (1 = right, 0 = wrong)."""
    # TODO (step 1)
    raise NotImplementedError


def ece(pairs: list[tuple[float, bool]], bins: int = 10) -> float:
    """Expected calibration error over equal-width bins of confidence."""
    # TODO (step 2): for each bin [b/bins, (b+1)/bins) — the last bin also takes 1.0 —
    #   add (share of pairs in the bin) × |accuracy in the bin − mean confidence in the bin|
    raise NotImplementedError


def choose_threshold(pairs: list[tuple[float, bool]], max_review: int,
                     candidates: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)) -> float:
    """The threshold that lets the fewest wrong outputs through without sending more than
    `max_review` messages to a person (ties: the lower threshold, i.e. less review)."""
    # TODO (step 3): a message goes to a person when confidence < threshold;
    #   a wrong output "slips through" when confidence >= threshold.
    #   Raise ValueError if no candidate fits the budget.
    raise NotImplementedError
