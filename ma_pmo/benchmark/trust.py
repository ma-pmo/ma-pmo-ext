"""`ma-pmo benchmark trust DIR`: does A4's confidence improve when it learns per organisation?

Static: an issue's confidence is its evidence kind's slip rate in the training releases (the
table `calibrate.py` fits). Dynamic: the same rate as a prior worth `w` issues, updated with the
organisation's own outcomes of that kind known before the prediction:

    (w * prior + slipped) / (w + n)

An outcome is known once its release date plus the benchmark's grace has passed; no prediction
uses an outcome known on or after its as-of date (`leaks` checks it). Method and criteria were
set before the first run (docs/TRUST-EVAL.md).
"""
from __future__ import annotations

import bisect
import random
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from ma_pmo.benchmark.calibrate import KIND_OF_SCORE, fit
from ma_pmo.benchmark.history import GRACE
from ma_pmo.benchmark.replay import ReplayTracker
from ma_pmo.benchmark.run import Row, _ece, rows_at, split

WEIGHT = 20  # the prior's weight in issues: fixed before the first run
WEIGHTS = (WEIGHT, 5, 50)  # 5 and 50 are reported, not decisive
MIN_TEST_ISSUES = 100  # organisations counted in the per-organisation ECE
ALPHA, DELTA = 0.2, 0.1  # the review threshold reported alongside


class History:
    """Each organisation's outcomes per evidence kind, in the order they became known."""

    def __init__(self, rows: list[Row]) -> None:
        events: dict[tuple[str, str], list[tuple[date, int]]] = defaultdict(list)
        for r in rows:
            events[(r.collection, KIND_OF_SCORE[r.a4])].append(
                (r.release_date + GRACE, r.label))
        self.known: dict[tuple[str, str], list[date]] = {}
        self.slipped: dict[tuple[str, str], list[int]] = {}
        for key, found in events.items():
            found.sort()
            self.known[key] = [d for d, _ in found]
            running, total = [0], 0
            for _, label in found:
                total += label
                running.append(total)
            self.slipped[key] = running

    def before(self, collection: str, kind: str, day: date) -> tuple[int, int, date | None]:
        """(outcomes known strictly before `day`, of them slipped, the latest such date)."""
        known = self.known.get((collection, kind), [])
        n = bisect.bisect_left(known, day)
        return n, self.slipped.get((collection, kind), [0])[n], known[n - 1] if n else None


def as_of_day(row: Row, k: int) -> date:
    return row.release_date - timedelta(days=k)


def predict(rows: list[Row], prior: dict[str, dict[str, Any]], history: History, k: int,
            w: float) -> list[tuple[float, float, date | None]]:
    """(static, dynamic, latest outcome used) for each row."""
    out = []
    for r in rows:
        kind = KIND_OF_SCORE[r.a4]
        rate = prior[kind]["rate"]
        n, slipped, latest = history.before(r.collection, kind, as_of_day(r, k))
        out.append((rate, (w * rate + slipped) / (w + n), latest))
    return out


def leaks(rows: list[Row], predicted: list[tuple[float, float, date | None]], k: int) -> int:
    """Predictions that used an outcome known on or after their as-of date (must be 0)."""
    return sum(1 for r, (_, _, latest) in zip(rows, predicted, strict=True)
               if latest is not None and latest >= as_of_day(r, k))


def brier(y: list[int], p: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(y, p, strict=True)) / len(y)


def _bootstrap(rows: list[Row], static: list[float], dynamic: list[float], seed: int = 0,
               rounds: int = 1000) -> tuple[float, float]:
    """95% interval of Brier(dynamic) - Brier(static), resampling releases."""
    by_release: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_release[r.release].append(i)
    releases = sorted(by_release)
    rng = random.Random(seed)
    diffs = []
    for _ in range(rounds):
        idx = [i for rel in rng.choices(releases, k=len(releases)) for i in by_release[rel]]
        diffs.append(sum((dynamic[i] - rows[i].label) ** 2 - (static[i] - rows[i].label) ** 2
                         for i in idx) / len(idx))
    diffs.sort()
    return diffs[int(0.025 * rounds)], diffs[int(0.975 * rounds) - 1]


def _per_organisation_ece(rows: list[Row], p: list[float]) -> float | None:
    groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[r.collection].append(i)
    eces = [_ece([rows[i].label for i in idx], [p[i] for i in idx])
            for idx in groups.values() if len(idx) >= MIN_TEST_ISSUES]
    return round(sum(eces) / len(eces), 4) if eces else None


def _committed(train: list[Row], train_p: list[float], test: list[Row],
               test_p: list[float]) -> dict[str, Any]:
    """The α threshold fitted on the training predictions, applied to the test: how many alerts
    commit without a person and how many of those did not slip."""
    from ma_pmo.core.risk_control import Group, threshold

    groups: dict[float, list[int]] = defaultdict(list)
    for r, p in zip(train, train_p, strict=True):
        groups[round(p, 2)].append(r.label)
    tau = threshold([Group(c, len(ls), len(ls) - sum(ls)) for c, ls in groups.items()],
                    ALPHA, DELTA)
    chosen = [r.label for r, p in zip(test, test_p, strict=True) if round(p, 2) >= tau]
    return {"threshold": tau, "committed": len(chosen),
            "wrong": len(chosen) - sum(chosen),
            "wrong_rate": round(1 - sum(chosen) / len(chosen), 4) if chosen else None}


def compare(train: list[Row], test: list[Row], k: int, w: float) -> dict[str, Any]:
    prior = fit(train)
    history = History(train + test)
    on_test = predict(test, prior, history, k, w)
    on_train = predict(train, prior, history, k, w)
    y = [r.label for r in test]
    static = [p[0] for p in on_test]
    dynamic = [p[1] for p in on_test]
    lo, hi = _bootstrap(test, static, dynamic)
    return {
        "k": k, "w": w, "test_issues": len(test),
        "test_releases": len({r.release for r in test}),
        "organisations": len({r.collection for r in test}),
        "leaks": leaks(test, on_test, k) + leaks(train, on_train, k),
        "brier": {"static": round(brier(y, static), 4), "dynamic": round(brier(y, dynamic), 4),
                  "difference_ci95": [round(lo, 4), round(hi, 4)]},
        "ece": {"static": _ece(y, static), "dynamic": _ece(y, dynamic)},
        "ece_per_organisation": {"static": _per_organisation_ece(test, static),
                                 "dynamic": _per_organisation_ece(test, dynamic)},
        "review": {"static": _committed(train, [p[0] for p in on_train], test, static),
                   "dynamic": _committed(train, [p[1] for p in on_train], test, dynamic)},
    }


def verdict(main: dict[str, Any]) -> dict[str, bool]:
    b, e, o = main["brier"], main["ece"], main["ece_per_organisation"]
    return {"brier": b["difference_ci95"][1] < 0,
            "ece": e["dynamic"] <= e["static"],
            "ece_per_organisation": (o["dynamic"] is not None and o["static"] is not None
                                     and o["dynamic"] <= o["static"]),
            "no_leakage": main["leaks"] == 0}


def evaluate(tracker: ReplayTracker) -> dict[str, Any]:
    runs = []
    for k in (14, 28):
        train, test = split(rows_at(tracker, k))
        for w in WEIGHTS:
            if k == 14 or w == WEIGHT:
                runs.append(compare(train, test, k, w))
    main = runs[0]
    criteria = verdict(main)
    return {"weight": WEIGHT, "main": main, "criteria": criteria, "pass": all(criteria.values()),
            "other": runs[1:]}


def to_markdown(result: dict[str, Any]) -> str:
    lines = ["# Dynamic trust (A4, public Jira benchmark)", "",
             "| k | w | Brier static | Brier dynamic | difference 95% | ECE static | "
             "ECE dynamic | ECE/org static | ECE/org dynamic | leaks |",
             "|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|"]
    for r in [result["main"], *result["other"]]:
        b, e, o = r["brier"], r["ece"], r["ece_per_organisation"]
        lines.append(f"| {r['k']} | {r['w']} | {b['static']} | {b['dynamic']} | "
                     f"{b['difference_ci95']} | {e['static']} | {e['dynamic']} | "
                     f"{o['static']} | {o['dynamic']} | {r['leaks']} |")
    rv = result["main"]["review"]
    lines += ["", f"Review threshold (α {ALPHA}): static commits {rv['static']['committed']} "
              f"(wrong {rv['static']['wrong_rate']}), dynamic commits "
              f"{rv['dynamic']['committed']} (wrong {rv['dynamic']['wrong_rate']}).", "",
              "Criteria: " + ", ".join(f"{k} {'pass' if v else 'FAIL'}"
                                      for k, v in result["criteria"].items()), ""]
    return "\n".join(lines)
