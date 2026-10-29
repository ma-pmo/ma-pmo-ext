"""Mock issue tracker — collects portfolio status from the DB (loaded fixtures).

Replace with a real Jira/Redmine REST connector, keeping the get_portfolio_status signature.
"""
from __future__ import annotations

from sqlalchemy import select

from ma_pmo.connectors.base import IssueTrackerConnector
from ma_pmo.db.models import Portfolio, Project, Task
from ma_pmo.db.session import get_session


class MockJiraConnector(IssueTrackerConnector):
    def get_portfolio_status(self, portfolio_id: str) -> dict:
        with get_session() as s:
            portfolio = s.get(Portfolio, portfolio_id)
            if portfolio is None:
                return {"portfolio_id": portfolio_id, "found": False, "projects": []}

            projects = s.scalars(
                select(Project).where(Project.portfolio_id == portfolio_id)
            ).all()
            proj_out = []
            for p in projects:
                tasks = s.scalars(select(Task).where(Task.project_id == p.id)).all()
                total_effort = sum(t.effort for t in tasks) or 1.0
                earned = sum(t.effort * (t.percent_complete / 100.0) for t in tasks)
                proj_out.append(
                    {
                        "project_id": p.id,
                        "skill": p.skill,
                        "status": p.status,
                        "planned_start": p.planned_start,
                        "planned_finish": p.planned_finish,
                        "deadline": p.deadline,
                        "percent_complete": round(earned / total_effort * 100, 1),
                        "tasks": [
                            {
                                "task_id": t.id,
                                "wbs": t.wbs,
                                "effort": t.effort,
                                "deps": t.deps,
                                "percent_complete": t.percent_complete,
                            }
                            for t in tasks
                        ],
                    }
                )
            return {
                "portfolio_id": portfolio.id,
                "name": portfolio.name,
                "period": portfolio.period,
                "found": True,
                "projects": proj_out,
            }
