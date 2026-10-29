"""`python -m ma_pmo.db.init` (or `ma-pmo init-db`) — create the schema and load fixtures."""
from __future__ import annotations

import json
from pathlib import Path

from ma_pmo.db.models import KnowledgeDoc, Portfolio, Project, Resource, Task
from ma_pmo.db.session import create_all, get_session

_FIX_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE = _FIX_DIR / "sample_portfolio.json"
LESSONS = _FIX_DIR / "lessons.json"


def load_fixtures() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with get_session() as s:
        p = data["portfolio"]
        s.merge(Portfolio(id=p["id"], name=p["name"], period=p["period"]))
        for r in data.get("resources", []):
            s.merge(Resource(id=r["id"], skill=r["skill"], capacity=r["capacity"]))
        for proj in data["projects"]:
            s.merge(
                Project(
                    id=proj["id"],
                    portfolio_id=p["id"],
                    skill=proj.get("skill", ""),
                    planned_start=proj.get("planned_start"),
                    planned_finish=proj.get("planned_finish"),
                    deadline=proj.get("deadline"),
                    status=proj.get("status", "green"),
                )
            )
            for t in proj.get("tasks", []):
                s.merge(
                    Task(
                        id=t["id"],
                        project_id=proj["id"],
                        wbs=t.get("wbs", ""),
                        effort=t.get("effort", 0.0),
                        deps=t.get("deps", []),
                        percent_complete=t.get("percent_complete", 0.0),
                    )
                )


def load_lessons() -> None:
    """Load the A7 knowledge corpus (lessons learned)."""
    docs = json.loads(LESSONS.read_text(encoding="utf-8"))
    with get_session() as s:
        for d in docs:
            s.merge(
                KnowledgeDoc(
                    id=d["id"],
                    project_ref=d.get("project_ref", ""),
                    title=d["title"],
                    text=d["text"],
                    tags=d.get("tags", []),
                    translations=d.get("translations", {}),
                )
            )


def main() -> None:
    create_all()
    load_fixtures()
    load_lessons()
    print(f"✓ schema created + fixtures loaded ({FIXTURE.name}, {LESSONS.name})")


if __name__ == "__main__":
    main()
