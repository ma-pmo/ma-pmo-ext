"""Lab 4 reference solution: a tracker that reads portfolio data from CSV files.

It reads the same portfolio.csv / projects.csv / tasks.csv layout as the evaluation data
template, so a team can point agents at a spreadsheet export instead of Jira.
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
        portfolio = next(
            (p for p in _rows(self.directory / "portfolio.csv") if p["id"] == portfolio_id),
            None,
        )
        if portfolio is None:
            return {"portfolio_id": portfolio_id, "found": False, "projects": []}

        tasks_by_project: dict[str, list[dict]] = {}
        for t in _rows(self.directory / "tasks.csv"):
            tasks_by_project.setdefault(t["project_id"], []).append(
                {
                    "task_id": t["id"],
                    "wbs": t["wbs"],
                    "effort": float(t["effort_hours"] or 0),
                    "deps": [d.strip() for d in t["deps"].split(";") if d.strip()],
                    "percent_complete": float(t["percent_complete"] or 0),
                }
            )

        projects = []
        for p in _rows(self.directory / "projects.csv"):
            tasks = tasks_by_project.get(p["id"], [])
            total = sum(t["effort"] for t in tasks) or 1.0
            earned = sum(t["effort"] * t["percent_complete"] / 100 for t in tasks)
            projects.append(
                {
                    "project_id": p["id"],
                    "skill": p["skill"],
                    "status": p["status"] or "green",
                    "planned_start": p["planned_start"] or None,
                    "planned_finish": p["planned_finish"] or None,
                    "deadline": p["deadline"] or None,
                    "percent_complete": round(earned / total * 100, 1),
                    "tasks": tasks,
                }
            )
        return {
            "portfolio_id": portfolio["id"],
            "name": portfolio["name"],
            "period": portfolio["period"],
            "found": True,
            "projects": projects,
        }


SPEC = IntegrationSpec(
    name="csv",
    kind="tracker",
    description="Read projects and tasks from CSV files (evaluation template layout).",
    required_settings=(),
    factory=CsvTracker.from_settings,
)
