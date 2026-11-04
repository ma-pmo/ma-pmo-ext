"""Lab 4: a tracker that reads portfolio data from CSV files.

Fill in every TODO, then run `ma-pmo learn check 4`. The lab guide is README.md.
The CSV files in ./data use the same layout as the evaluation data template.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from ma_pmo.core.config import Settings
from ma_pmo.integrations.base import IntegrationSpec


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


class CsvTracker:
    name = "csv"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    @classmethod
    def from_settings(cls, settings: Settings) -> CsvTracker:
        return cls(os.environ.get("MA_PMO_CSV_TRACKER_DIR", "tracker-data"))

    def get_portfolio_status(self, portfolio_id: str) -> dict:
        # TODO (step 1): find the portfolio row; if it is missing return
        #   {"portfolio_id": portfolio_id, "found": False, "projects": []}
        # TODO (step 2): turn every tasks.csv row into
        #   {"task_id", "wbs", "effort" (float), "deps" (list of ids split on ";"),
        #    "percent_complete" (float)}
        # TODO (step 3): one dict per project with project_id, skill, status, planned_start,
        #   planned_finish, deadline, tasks and percent_complete — weighted by effort,
        #   rounded to 1 decimal
        # TODO (step 4): return {"portfolio_id", "name", "period", "found": True, "projects"}
        raise NotImplementedError


# TODO (step 5): this integration is a tracker, not a notifier
SPEC = IntegrationSpec(
    name="csv",
    kind="notifier",
    description="Read projects and tasks from CSV files (evaluation template layout).",
    required_settings=(),
    factory=CsvTracker.from_settings,
)
