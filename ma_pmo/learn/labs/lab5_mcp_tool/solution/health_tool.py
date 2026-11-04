"""Lab 5 reference solution: a read-only MCP tool that summarizes one project's health."""
from __future__ import annotations

from typing import Any

from ma_pmo.agents.cpm import compute_cpm
from ma_pmo.integrations.registry import get_tracker


def project_health(project_id: str, portfolio_id: str = "PORTFOLIO#2026-Q1") -> dict:
    """Status colour, progress, critical path and the smallest slack of one project."""
    status = get_tracker().get_portfolio_status(portfolio_id)
    project = next((p for p in status.get("projects", []) if p["project_id"] == project_id), None)
    if project is None:
        return {"error": f"unknown project '{project_id}'",
                "projects": [p["project_id"] for p in status.get("projects", [])]}
    cpm = compute_cpm(project.get("tasks", []))
    open_tasks = [t for t in cpm.tasks if t.slack > 0]
    return {
        "project_id": project_id,
        "status": project["status"],
        "percent_complete": project["percent_complete"],
        "critical_path": cpm.critical_path,
        "min_slack_days": min((t.slack for t in open_tasks), default=0),
    }


def register(server: Any) -> None:
    from mcp_types import ToolAnnotations

    server.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                            idempotent_hint=True, open_world_hint=False))(
        project_health)
