"""Dynamic trust (docs/TRUST-EVAL.md): learning per organisation without using the future."""
from __future__ import annotations

from datetime import date

from ma_pmo.benchmark import trust
from ma_pmo.benchmark.run import Row


def _row(org: str, day: date, kind_score: float, label: int, n: int) -> Row:
    return Row(release=(org, f"v{n}"), collection=org, release_date=day, key=f"{org}-{n}",
               features={}, a4=kind_score, label=label)


def test_only_outcomes_known_before_the_as_of_date_are_used():
    rows = [_row("acme", date(2026, 1, 1), 0.9, 1, 1),
            _row("acme", date(2026, 1, 20), 0.9, 1, 2),
            _row("acme", date(2026, 2, 1), 0.9, 0, 3)]
    prior = {"blocked": {"rate": 0.5}, "stalled": {"rate": 0.5}, "moving": {"rate": 0.5}}
    got = trust.predict(rows, prior, trust.History(rows), k=14, w=2)
    # the third release is predicted on 2026-01-18: only the first outcome (01-02) is known
    assert got[2][1] == (2 * 0.5 + 1) / (2 + 1)
    assert trust.leaks(rows, got, 14) == 0
    # another organisation's outcomes are never used
    other = [_row("beta", date(2026, 3, 1), 0.9, 0, 4)]
    assert trust.predict(other, prior, trust.History(rows + other), k=14, w=2)[0][1] == 0.5


def test_a_leak_would_be_counted():
    rows = [_row("acme", date(2026, 1, 10), 0.9, 1, 1)]
    assert trust.leaks(rows, [(0.5, 0.6, date(2026, 1, 1))], 14) == 1  # as-of 2025-12-27
