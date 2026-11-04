"""Lab 5: a read-only MCP tool that summarizes one project's health.

Fill in every TODO, then run `ma-pmo learn check 5`. The lab guide is README.md.
Look at `ma_pmo/mcp_server.py` for how the built-in tools are written.
"""
from __future__ import annotations

from typing import Any

from ma_pmo.agents.cpm import compute_cpm  # noqa: F401  (you will need it)
from ma_pmo.integrations.registry import get_tracker  # noqa: F401  (you will need it)


def project_health(project_id: str, portfolio_id: str = "PORTFOLIO#2026-Q1") -> dict:
    """Status colour, progress, critical path and the smallest slack of one project."""
    # TODO (step 1): read the portfolio with get_tracker().get_portfolio_status(portfolio_id)
    # TODO (step 2): unknown project -> {"error": "unknown project '<id>'", "projects": [ids]}
    # TODO (step 3): run compute_cpm(project["tasks"]) and return
    #   project_id, status, percent_complete, critical_path and min_slack_days
    #   (the smallest slack among tasks that have slack > 0; 0 if none)
    raise NotImplementedError


def register(server: Any) -> None:
    # TODO (step 4): register project_health with server.tool(...), marked read-only with
    #   mcp_types.ToolAnnotations(read_only_hint=True, ...)
    raise NotImplementedError
