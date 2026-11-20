"""`ma-pmo benchmark run DIR`: score every issue scheduled at T, compare scorers, report metrics.

Each row is an issue scheduled for a usable release at T = release date − k days, labelled 1 if it
slipped (moved out, or still open) and 0 if it was resolved in time (`history.py`; late closures
are left out). Scorers see only what was known at T.

| scorer | score |
|---|---|
| `all_slip` | 1 for every issue (the majority class) |
| `progress` | 1 if not started at T, 0.5 if started, 0.2 if in review or resolved-pending |
| `a4_signals` | A4's rule signals on the replayed release, per task: blocked 0.9, stalled 0.7, |
|              | else 0.3 |
| `forest` | a random forest on the literature features (`features.py`), fitted on earlier |
|          | releases |

Releases are split by date: the earliest 70% train the forest, every scorer is measured on the
latest 30%. Metrics: PR-AUC (with a 95% bootstrap interval over releases), ROC-AUC, F1 at 0.5,
Brier score and ECE (10 bins), the share that slipped, and PR-AUC for the reverse question "which
issues make it". The same metrics are given on informative releases (10–90% slipped) and on
issues already started at T, and PR-AUC per collection.

Needs scikit-learn: pip install "ma-pmo[benchmark]".
"""
from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ma_pmo.agents.risk_signals import compute_signals
from ma_pmo.benchmark.coverage import INFORMATIVE, MIN_ISSUES
from ma_pmo.benchmark.features import NAMES, release_features
from ma_pmo.benchmark.history import SLIPPED
from ma_pmo.benchmark.replay import ReplayTracker, as_of, portfolio_id

TRAIN_SHARE = 0.7
BOOTSTRAP = 200


@dataclass
class Row:
    release: tuple[str, str]
    collection: str
    release_date: date
    key: str
    features: dict[str, float]
    a4: float
    label: int


def a4_scores(tracker: ReplayTracker, pid: str) -> dict[str, float]:
    """A4's rule signals on the replayed release, per task."""
    status = tracker.get_portfolio_status(pid)
    if not status["projects"]:
        return {}
    sig = compute_signals(status["projects"][0])
    blocked, stalled = set(sig.blocked_tasks), set(sig.stalled_tasks)
    return {t["task_id"]: 0.9 if t["task_id"] in blocked else 0.7 if t["task_id"] in stalled
            else 0.3 for t in status["projects"][0]["tasks"]}


def rows_at(tracker: ReplayTracker, k: int, min_issues: int | None = None) -> list[Row]:
    min_issues = MIN_ISSUES if min_issues is None else min_issues
    out = []
    for ref, release in sorted(tracker.releases.items()):
        t = as_of(release.release_date - timedelta(days=k))
        issues = tracker.issues[ref]
        feats = release_features(issues, release.version_id, release.release_date, t)
        labels = {}
        for h in issues:
            if h.key in feats:
                outcome = h.outcome(release.version_id, release.release_date)
                if outcome != "late":
                    labels[h.key] = int(outcome in SLIPPED)
        if len(labels) < min_issues:
            continue
        a4 = a4_scores(tracker, portfolio_id(release, k))
        out += [Row(ref, release.collection, release.release_date, key, feats[key],
                    a4.get(key, 0.3), label) for key, label in sorted(labels.items())]
    return out


def split(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    """Train on the earliest releases, test on the latest."""
    dates = sorted({(r.release_date, r.release) for r in rows})
    train = {ref for _, ref in dates[:int(len(dates) * TRAIN_SHARE)]}
    return [r for r in rows if r.release in train], [r for r in rows if r.release not in train]


def _sklearn() -> Any:
    try:
        from sklearn import ensemble, metrics
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise ImportError('the benchmark needs scikit-learn: pip install "ma-pmo[benchmark]"') \
            from e
    return ensemble, metrics


def scorers(train: list[Row], test: list[Row]) -> dict[str, Callable[[Row], float]]:
    """Every scorer, as a function of a test row (the forest is fitted on `train`)."""
    ensemble, _ = _sklearn()
    forest = ensemble.RandomForestClassifier(n_estimators=200, min_samples_leaf=20,
                                             random_state=0, n_jobs=-1)
    if not train or not test:
        raise ValueError("no releases to train or test on")
    forest.fit([[r.features[n] for n in NAMES] for r in train], [r.label for r in train])
    proba = forest.predict_proba([[r.features[n] for n in NAMES] for r in test])
    slipped = list(forest.classes_).index(1) if 1 in forest.classes_ else None
    predicted = {id(r): float(p[slipped]) if slipped is not None else 0.0
                 for r, p in zip(test, proba, strict=True)}
    return {
        "all_slip": lambda r: 1.0,
        "progress": lambda r: 0.2 if r.features["in_review"] else
        0.5 if r.features["started"] else 1.0,
        "a4_signals": lambda r: r.a4,
        "forest": lambda r: predicted[id(r)],
    }


def _ece(y: list[int], p: list[float], bins: int = 10) -> float:
    total, err = len(y), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, v in enumerate(p) if lo <= v < hi or (b == bins - 1 and v == 1.0)]
        if idx:
            acc = sum(y[i] for i in idx) / len(idx)
            conf = sum(p[i] for i in idx) / len(idx)
            err += len(idx) / total * abs(acc - conf)
    return round(err, 3)


def metrics(rows: list[Row], score: Callable[[Row], float], seed: int = 0) -> dict[str, Any]:
    _, m = _sklearn()
    y = [r.label for r in rows]
    p = [score(r) for r in rows]
    if not rows or len(set(y)) < 2:
        return {"n": len(rows), "slipped": round(sum(y) / len(y), 3) if y else None}
    by_release: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_release[r.release].append(i)
    groups = list(by_release.values())
    rnd, boot = random.Random(seed), []
    for _ in range(BOOTSTRAP):
        idx = [i for g in (rnd.choice(groups) for _ in groups) for i in g]
        yy = [y[i] for i in idx]
        if len(set(yy)) == 2:
            boot.append(m.average_precision_score(yy, [p[i] for i in idx]))
    boot.sort()
    return {
        "n": len(rows), "releases": len(groups), "slipped": round(sum(y) / len(y), 3),
        "pr_auc": round(m.average_precision_score(y, p), 3),
        "pr_auc_ci": [round(boot[int(0.025 * len(boot))], 3),
                      round(boot[int(0.975 * len(boot)) - 1], 3)] if boot else None,
        "roc_auc": round(m.roc_auc_score(y, p), 3),
        "f1": round(m.f1_score(y, [int(v >= 0.5) for v in p], zero_division=0), 3),
        "brier": round(m.brier_score_loss(y, p), 3),
        "ece": _ece(y, p),
        "pr_auc_made_it": round(m.average_precision_score([1 - v for v in y],
                                                          [1 - v for v in p]), 3),
    }


def informative(rows: list[Row]) -> list[Row]:
    by_release: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for r in rows:
        by_release[r.release].append(r)
    lo, hi = INFORMATIVE
    return [r for rs in by_release.values()
            if lo <= sum(x.label for x in rs) / len(rs) <= hi for r in rs]


def evaluate(tracker: ReplayTracker, ks: Iterable[int] = (14, 28)) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k in ks:
        rows = rows_at(tracker, k)
        train, test = split(rows)
        score = scorers(train, test)
        subsets = {"all": test, "informative": informative(test),
                   "started": [r for r in test if r.features["started"]]}
        by_collection: dict[str, list[Row]] = defaultdict(list)
        for r in test:
            by_collection[r.collection].append(r)
        result[f"k={k}"] = {
            "train": {"rows": len(train), "releases": len({r.release for r in train}),
                      "until": max((r.release_date for r in train), default=None)},
            "test": {"rows": len(test), "releases": len({r.release for r in test})},
            **{name: {s: metrics(rs, f) for s, rs in subsets.items()}
               for name, f in score.items()},
            "per_collection": {
                c: {name: metrics(rs, score[name]).get("pr_auc") for name in ("a4_signals",
                                                                              "forest")}
                | {"rows": len(rs), "slipped": round(sum(r.label for r in rs) / len(rs), 3)}
                for c, rs in sorted(by_collection.items(), key=lambda kv: -len(kv[1]))
                if len(rs) >= 200},
        }
    return result


def to_markdown(result: dict[str, Any]) -> str:
    lines = ["# Benchmark results", ""]
    for key, r in result.items():
        lines += [f"## As of {key[2:]} days before release", "",
                  f"Trained on {r['train']['releases']} releases up to {r['train']['until']}, "
                  f"tested on {r['test']['releases']} later releases ({r['test']['rows']} "
                  "issues).", ""]
        for subset in ("all", "informative", "started"):
            first = r["all_slip"][subset]
            lines += [f"### {subset} (n={first['n']}, slipped {first.get('slipped')})", "",
                      "| scorer | PR-AUC [95% CI] | ROC-AUC | F1 | Brier | ECE | PR-AUC made it |",
                      "|---|---|---|---|---|---|---|"]
            for name in ("all_slip", "progress", "a4_signals", "forest"):
                v = r[name][subset]
                ci = v.get("pr_auc_ci") or ["–", "–"]
                lines.append(f"| {name} | {v.get('pr_auc', '–')} [{ci[0]}, {ci[1]}] | "
                             f"{v.get('roc_auc', '–')} | {v.get('f1', '–')} | "
                             f"{v.get('brier', '–')} | {v.get('ece', '–')} | "
                             f"{v.get('pr_auc_made_it', '–')} |")
            lines.append("")
        lines += ["### PR-AUC per collection (test, ≥ 200 issues)", "",
                  "| collection | issues | slipped | a4_signals | forest |",
                  "|---|---|---|---|---|"]
        for c, v in r["per_collection"].items():
            lines.append(f"| {c} | {v['rows']} | {v['slipped']} | {v['a4_signals']} | "
                         f"{v['forest']} |")
        lines.append("")
    return "\n".join(lines)
