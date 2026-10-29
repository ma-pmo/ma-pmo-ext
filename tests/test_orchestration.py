"""A1 integration — offline (no LLM) end-to-end orchestration.

Keyword routing + deterministic worker fallbacks run A1 -> workers -> synthesis without an
API key. (conftest sets ANTHROPIC_API_KEY='test-key', so real calls fail -> fallback path.)
"""
from __future__ import annotations

from ma_pmo.agents.orchestrator import OrchestratorAgent
from ma_pmo.agents.orchestrator_rules import keyword_route
from ma_pmo.core.graph import build_graph


def test_keyword_router_maps_goals():
    assert keyword_route("compute schedule critical path").delegations[0].agent == "A2"
    assert keyword_route("allocate resources").delegations[0].agent == "A3"
    assert keyword_route("gate quality review").delegations[0].agent == "A6"
    assert keyword_route("similar cases lessons learned").delegations[0].agent == "A7"
    # Korean goals route the same way
    assert keyword_route("일정 임계경로 산출").delegations[0].agent == "A2"
    assert keyword_route("자원 배분 최적화").delegations[0].agent == "A3"
    assert keyword_route("게이트 품질 심사").delegations[0].agent == "A6"
    assert keyword_route("유사 사례 교훈").delegations[0].agent == "A7"
    # no match -> A5 fallback
    assert keyword_route("").delegations[0].agent == "A5"


def test_route_falls_back_to_rules_without_llm():
    # a real LLM call fails with test-key -> rule routing
    out = OrchestratorAgent().route(
        {"goal": "resource allocation", "task_ref": "PORTFOLIO#2026-Q1"}
    )
    assert out["routing"]["mode"] == "rule"
    assert any(d["agent"] == "A3" for d in out["routing"]["delegations"])


def test_full_graph_runs_offline():
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-integration"}}
    final = graph.invoke(
        {
            "goal": "resource allocation and schedule check",
            "task_ref": "PORTFOLIO#2026-Q1",
            "outputs": [],
            "messages": [],
        },
        config=config,
    )
    # routed to A2 and A3, producing outputs and a synthesis
    agents = {o["agent"] for o in final.get("outputs", [])}
    assert {"A2", "A3"} & agents
    assert final.get("synthesis", {}).get("summary")


def test_full_graph_report_goal_offline():
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-report"}}
    final = graph.invoke(
        {
            "goal": "generate executive report",
            "task_ref": "PORTFOLIO#2026-Q1",
            "outputs": [],
            "messages": [],
        },
        config=config,
    )
    # an A5 fallback report must be produced
    reports = [o for o in final.get("outputs", []) if o["agent"] == "A5"]
    assert reports and reports[0]["data"]["executive_summary"]
