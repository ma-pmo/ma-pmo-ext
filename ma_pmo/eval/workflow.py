"""Evaluation workflow shared by the CLI and the API: dataset → H1–H5 → report."""
from __future__ import annotations

import os
from pathlib import Path

from ma_pmo.core.i18n import tr
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.eval.dataset import Dataset, Issue, import_dataset, load_dataset

DEMO_SCOPE = DEFAULT_SCOPE


class DatasetError(ValueError):
    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        errors = [i for i in issues if i.level == "error"]
        super().__init__(f"{len(errors)} error(s) in the evaluation data")


def use_isolated_db(data_dir: str | Path) -> Path | None:
    """Point the DB at `<data_dir>/.ma-pmo-eval.db` so a dataset is never mixed with other data.

    Must run before any database module is imported. Leaves an explicit DB_URL untouched.
    """
    if os.environ.get("DB_URL"):
        return None
    path = Path(data_dir).resolve() / ".ma-pmo-eval.db"
    os.environ["DB_URL"] = f"sqlite:///{path}"
    os.environ.setdefault("CHECKPOINT_DB", str(path.with_suffix(".ckpt.sqlite")))
    return path


def evaluate_dataset(data_dir: str | Path) -> tuple[dict, Dataset, list[Issue]]:
    """Validate, import and evaluate a data folder. Raises DatasetError on errors."""
    from ma_pmo.db.init import load_lessons
    from ma_pmo.eval.harness import run_all

    ds, issues = load_dataset(data_dir)
    if any(i.level == "error" for i in issues):
        raise DatasetError(issues)
    import_dataset(ds)
    load_lessons()  # H4 needs the lessons-learned corpus
    results = run_all(populate=True, scope=ds.scope, baselines=ds.baselines, labels=ds.labels)
    return results, ds, issues


def evaluate_demo() -> dict:
    from ma_pmo.eval.harness import run_all

    return run_all(populate=True, scope=DEMO_SCOPE)


def demo_source() -> str:
    return tr("bundled demo portfolio (example values)", "기본 데모 포트폴리오(예시 값)")


def dataset_source(data_dir: str | Path) -> str:
    return tr(f"organization data from {data_dir}", f"조직 데이터: {data_dir}")
