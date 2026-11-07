"""MCP server: lets AI assistants and other MCP clients use MA-PMO's agents as tools.

    pip install "ma-pmo[mcp]"
    ma-pmo mcp                       # stdio transport (for Claude Desktop, Claude Code, IDEs)

Read-only tools report status, schedules, risks, approvals, evaluation results and lessons
learned. `run_scenario` runs agents and may queue new approvals. Approving or rejecting is
deliberately *not* a tool: HITL decisions stay with a person, in the dashboard or the API.

The stdio server runs with the permissions of the local user who starts it, so it does not go
through the HTTP API's authentication (see docs/AUTH.md); it uses the same database settings
(`DB_URL`) as the API.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ma_pmo import __version__
from ma_pmo.core.i18n import normalize, use_lang
from ma_pmo.core.scope import DEFAULT_SCOPE

INSTRUCTIONS = (
    "MA-PMO is a multi-agent project management office. Use portfolio_status first to see "
    "projects, then schedule, risks and pending_approvals for details. run_scenario runs a "
    "lifecycle scenario end to end (plan, execute, complete, insight). Approvals are made by a "
    "person, never by a tool. Pass lang='ko' for Korean output."
)


@contextmanager
def _lang(lang: str | None) -> Iterator[None]:
    with use_lang(normalize(lang)):
        yield


def create_server() -> Any:
    """Build the MCP server. Raises ImportError with an install hint if the SDK is missing."""
    try:
        from mcp.server import MCPServer
        from mcp_types import ToolAnnotations
    except ImportError as e:  # optional dependency
        raise ImportError('the MCP server needs the extra: pip install "ma-pmo[mcp]"') from e

    server: Any = MCPServer(
        name="ma-pmo", title="MA-PMO", version=__version__, instructions=INSTRUCTIONS
    )
    read_only = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                                open_world_hint=False)

    @server.tool(annotations=read_only)
    def portfolio_status(portfolio_id: str = DEFAULT_SCOPE) -> dict:
        """Projects in a portfolio with status colour, dates, progress and tasks."""
        from ma_pmo.integrations.registry import get_tracker

        return get_tracker().get_portfolio_status(portfolio_id)

    @server.tool(annotations=read_only)
    def schedule(project_id: str, portfolio_id: str = DEFAULT_SCOPE) -> dict:
        """Critical-path schedule for one project: early start/finish per task, the critical
        path and the projected finish date (A2's CPM, deterministic, no side effects)."""
        from ma_pmo.agents.cpm import CpmResult, compute_cpm
        from ma_pmo.integrations.registry import get_tracker

        status = get_tracker().get_portfolio_status(portfolio_id)
        project = next((p for p in status.get("projects", []) if p["project_id"] == project_id),
                       None)
        if project is None:
            known = [p["project_id"] for p in status.get("projects", [])]
            return {"error": f"unknown project '{project_id}'", "projects": known}
        start = project.get("planned_start")
        cpm = compute_cpm(project.get("tasks", []))
        return {
            "project_id": project_id,
            "critical_path": cpm.critical_path,
            "duration_days": cpm.project_duration,
            "projected_finish": cpm.projected_finish(start),
            "deadline": project.get("deadline"),
            "tasks": [
                {"task_id": t.task_id, "early_start": CpmResult.offset_date(start, t.early_start),
                 "early_finish": CpmResult.offset_date(start, t.early_finish),
                 "slack_days": t.slack, "critical": t.is_critical}
                for t in cpm.tasks
            ],
        }

    @server.tool(annotations=read_only)
    def risks(project_id: str | None = None, limit: int = 20) -> list[dict]:
        """Risks detected by the risk agent (A4), newest first."""
        from ma_pmo.api.routers.risks import list_risks

        return list_risks(project_id=project_id, limit=max(1, min(limit, 100)))

    @server.tool(annotations=read_only)
    def pending_approvals(lang: str | None = None) -> list[dict]:
        """High-risk or low-confidence agent proposals waiting for a person to decide."""
        from ma_pmo.core import hitl

        with _lang(lang):
            return hitl.list_pending()

    @server.tool(annotations=read_only)
    def list_scenarios(lang: str | None = None) -> list[dict]:
        """The 20 project-lifecycle scenarios: id, title, agents and hypotheses."""
        from ma_pmo.core.scenarios import list_scenarios as _list

        with _lang(lang):
            return _list()

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                             idempotent_hint=False, open_world_hint=False))
    def run_scenario(scenario_id: str, portfolio_id: str = DEFAULT_SCOPE,
                     lang: str | None = None) -> dict:
        """Run a scenario through the agents (plan → execute → complete → insight).
        Messages are written to the audit log; risky proposals wait in the approval queue."""
        from ma_pmo.core.scenarios import run_scenario as _run
        from ma_pmo.core.scenarios import workflows

        known = [spec.id for spec in workflows()]  # includes this workspace's own
        if scenario_id not in known:
            return {"error": f"unknown scenario '{scenario_id}'", "scenarios": known}
        with _lang(lang):
            trace = _run(scenario_id, portfolio_id)
        trace.pop("paper_markdown", None)  # long; available from the API with ?format=markdown
        return trace

    @server.tool(annotations=read_only)
    def evaluation(lang: str | None = None) -> dict:
        """H1–H5 hypothesis verdicts on the current data (supported, partly supported, not
        supported, insufficient data) with the evidence for each."""
        from ma_pmo.eval.harness import run_all
        from ma_pmo.eval.report import summarize

        with _lang(lang):
            return {"verdicts": summarize(run_all(populate=False))}

    @server.tool(annotations=read_only)
    def search_lessons(query: str, k: int = 3, lang: str | None = None) -> dict:
        """Lessons learned relevant to a question, always with citations (A7 retrieval)."""
        from ma_pmo.agents.knowledge import KnowledgeAgent

        with _lang(lang):
            citations = KnowledgeAgent().retrieve(query, k=max(1, min(k, 10)))
        return {"query": query, "citations": citations}

    return server


def main() -> int:
    from ma_pmo.core.obs import configure_logging

    configure_logging()  # logs go to stderr; stdout belongs to the MCP protocol
    create_server().run("stdio")
    return 0
