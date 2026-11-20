"""`ma-pmo benchmark calibrate DIR --out FILE`: fit A4's confidence table on the benchmark.

For each kind of evidence A4 computes per task (`agents/risk_calibration.py`), the share of
scheduled issues that slipped in the training releases (the earliest 70%, as in `run.py`), with
a 95% Wilson interval. The table is then checked on the latest releases: ECE and Brier of A4's
old fixed scores against the calibrated ones.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from ma_pmo.agents.risk_calibration import KINDS
from ma_pmo.benchmark.replay import ReplayTracker
from ma_pmo.benchmark.run import Row, _ece, rows_at, split

# the score `run.a4_scores` gives each kind of evidence
RAW = {"blocked": 0.9, "stalled": 0.7, "moving": 0.3}
KIND_OF_SCORE = {v: k for k, v in RAW.items()}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(centre - half, 3), round(centre + half, 3)


def _brier(y: list[int], p: list[float]) -> float:
    return round(sum((a - b) ** 2 for a, b in zip(y, p, strict=True)) / len(y), 3)


def fit(train: list[Row]) -> dict[str, dict[str, Any]]:
    kinds = {}
    for kind in KINDS:
        rs = [r for r in train if KIND_OF_SCORE[r.a4] == kind]
        slipped = sum(r.label for r in rs)
        kinds[kind] = {"n": len(rs), "slipped": slipped,
                       "rate": round(slipped / len(rs), 3) if rs else 0.5,
                       "ci95": list(wilson(slipped, len(rs)))}
    return kinds


def calibrate(tracker: ReplayTracker, k: int = 14) -> dict[str, Any]:
    train, test = split(rows_at(tracker, k))
    kinds = fit(train)
    y = [r.label for r in test]
    raw = [r.a4 for r in test]
    cal = [kinds[KIND_OF_SCORE[r.a4]]["rate"] for r in test]
    return {
        "description": "A4 task evidence -> share of issues that slipped (public Jira benchmark)",
        "fitted": date.today().isoformat(),
        "as_of_days": k,
        "train": {"issues": len(train), "releases": len({r.release for r in train}),
                  "until": max(r.release_date for r in train).isoformat()},
        "kinds": kinds,
        "test": {"issues": len(test), "releases": len({r.release for r in test}),
                 "slipped": round(sum(y) / len(y), 3),
                 "ece_fixed": _ece(y, raw), "ece_calibrated": _ece(y, cal),
                 "brier_fixed": _brier(y, raw), "brier_calibrated": _brier(y, cal),
                 "rate_by_kind": {kind: round(sum(r.label for r in test
                                                  if KIND_OF_SCORE[r.a4] == kind)
                                              / max(1, sum(KIND_OF_SCORE[r.a4] == kind
                                                           for r in test)), 3)
                                  for kind in KINDS}},
    }
