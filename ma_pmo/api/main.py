"""FastAPI entry point — orchestration, webhook, approval and KPI endpoints.

The Presentation/Orchestration boundary of the paper's architecture; the Next.js
dashboard consumes this API. Responses follow `?lang=en|ko` or `Accept-Language`.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ma_pmo.core.obs import configure_logging

configure_logging()

from ma_pmo.api.routers import (  # noqa: E402
    approvals,
    evaluation,
    knowledge,
    kpi,
    messages,
    orchestrate,
    planning,
    risks,
    scenarios,
    webhooks,
)
from ma_pmo.connectors.jira_mock import MockJiraConnector  # noqa: E402
from ma_pmo.core import protocol  # noqa: E402
from ma_pmo.core.i18n import from_accept_language, normalize, tr, use_lang  # noqa: E402
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload  # noqa: E402

app = FastAPI(title="MA-PMO API", version="0.1.0")


@app.middleware("http")
async def language(request: Request, call_next):
    """Pick the response language from ?lang= or Accept-Language (default: MA_PMO_LANG)."""
    lang = normalize(request.query_params.get("lang")) or from_accept_language(
        request.headers.get("accept-language")
    )
    with use_lang(lang):
        return await call_next(request)


# CORS for the Next.js dashboard (localhost:3000) in development
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",  # development: allow any local port
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orchestrate.router)
app.include_router(approvals.router)
app.include_router(kpi.router)
app.include_router(risks.router)
app.include_router(planning.router)
app.include_router(knowledge.router)
app.include_router(evaluation.router)
app.include_router(scenarios.router)
app.include_router(messages.router)
app.include_router(webhooks.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/portfolio/{portfolio_id}")
def portfolio_status(portfolio_id: str) -> dict:
    """Portfolio and project progress for the dashboard."""
    return MockJiraConnector().get_portfolio_status(portfolio_id)


@app.post("/demo/gated-message")
def demo_gated_message(task_ref: str = "PORTFOLIO#2026-Q1") -> dict:
    """HITL demo: publish a high-risk (external communication) message into the approval queue."""
    msg = AgentMessage(
        sender="A5",
        receiver="A1",
        intent=Intent.PROPOSE,
        task_ref=task_ref,
        payload=MessagePayload(
            schema_="report.v1",
            data={
                "scope": task_ref,
                "executive_summary": tr(
                    "Draft report awaiting release to external stakeholders",
                    "외부 이해관계자 발송 대기 보고 초안",
                ),
                "project_status": [],
            },
        ),
        confidence=0.55,  # below threshold -> automatic gate
        human_gate_required=True,
    )
    protocol.publish(msg)
    return {"published": msg.message_id, "gated": True}
