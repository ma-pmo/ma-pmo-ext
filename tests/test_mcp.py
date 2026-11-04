"""MCP server: tools are listed with the right hints and return MA-PMO data over the protocol.

Skipped when the optional `mcp` extra is not installed (CI installs it).
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402

from ma_pmo.mcp_server import create_server  # noqa: E402

READ_ONLY = {"portfolio_status", "schedule", "risks", "pending_approvals", "list_scenarios",
             "evaluation", "search_lessons"}


def _data(result) -> object:
    assert not result.is_error, result
    if result.structured_content is not None:
        content = result.structured_content
        return content.get("result", content) if isinstance(content, dict) else content
    return json.loads(result.content[0].text)


@pytest.mark.smoke
async def test_tools_are_listed_with_safety_hints():
    async with Client(create_server()) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == READ_ONLY | {"run_scenario"}
    for name in READ_ONLY:
        assert tools[name].annotations.read_only_hint is True, name
    assert tools["run_scenario"].annotations.read_only_hint is False
    assert not any("approve" in name or "reject" in name for name in tools)


async def test_status_schedule_and_lessons():
    async with Client(create_server()) as client:
        status = _data(await client.call_tool("portfolio_status", {}))
        assert status["found"] is True and len(status["projects"]) == 3
        sched = _data(await client.call_tool("schedule", {"project_id": "PROJ-14"}))
        assert sched["critical_path"] == ["T-1401", "T-1402", "T-1403"]
        missing = _data(await client.call_tool("schedule", {"project_id": "NOPE"}))
        assert "unknown project" in missing["error"] and "PROJ-14" in missing["projects"]
        lessons = _data(await client.call_tool("search_lessons", {"query": "estimation"}))
        assert lessons["citations"]


async def test_run_scenario_and_korean_output():
    async with Client(create_server()) as client:
        trace = _data(await client.call_tool(
            "run_scenario", {"scenario_id": "quarterly_review", "lang": "ko"}))
        phases = [p["phase"] for p in trace["phases"]]  # one execute phase per agent
        assert phases[0] == "plan" and phases[-1] == "insight"
        assert {"execute", "complete"} <= set(phases)
        assert "paper_markdown" not in trace
        assert any("가" <= ch <= "힣" for ch in trace["title"])  # Hangul title
        bad = _data(await client.call_tool("run_scenario", {"scenario_id": "nope"}))
        assert "quarterly_review" in bad["scenarios"]
        verdicts = _data(await client.call_tool("evaluation", {}))["verdicts"]
        assert len(verdicts) == 5
        assert isinstance(_data(await client.call_tool("pending_approvals", {})), list)
