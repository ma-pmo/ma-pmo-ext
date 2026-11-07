"""FastAPI entry point — orchestration, webhook, approval and KPI endpoints.

The Presentation/Orchestration boundary of the paper's architecture; the Next.js
dashboard consumes this API. Responses follow `?lang=en|ko` or `Accept-Language`.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from ma_pmo.core.obs import configure_logging, get_logger
from ma_pmo.core.tracing import configure_tracing

configure_logging()
configure_tracing()

from ma_pmo import __version__  # noqa: E402
from ma_pmo.agents import registry as agent_registry  # noqa: E402
from ma_pmo.api.auth import (  # noqa: E402
    ANONYMOUS,
    AuthMiddleware,
    CurrentPrincipal,
    build_authenticator,
)
from ma_pmo.api.routers import (  # noqa: E402
    approvals,
    evaluation,
    integrations,
    knowledge,
    kpi,
    messages,
    orchestrate,
    planning,
    risks,
    runs,
    scenarios,
    webhooks,
    workspaces,
)
from ma_pmo.core import protocol, workspace  # noqa: E402
from ma_pmo.core import runs as runs_core  # noqa: E402
from ma_pmo.core.config import get_settings  # noqa: E402
from ma_pmo.core.i18n import from_accept_language, normalize, tr, use_lang  # noqa: E402
from ma_pmo.core.scenarios import workflow_problems  # noqa: E402
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload  # noqa: E402
from ma_pmo.core.scope import DEFAULT_SCOPE  # noqa: E402
from ma_pmo.integrations.registry import get_tracker  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """On startup, surface runs a stopped process left behind (see core/runs.py)."""
    try:
        recovered = runs_core.recover_interrupted()
        if recovered:
            get_logger("api").warning("runs_interrupted", runs=recovered)
    except SQLAlchemyError as e:  # schema not created yet: `ma-pmo init-db`
        get_logger("api").warning("run_recovery_skipped", error=str(e)[:200])
    yield


app = FastAPI(title="MA-PMO API", version=__version__, lifespan=lifespan)



# Added first so it runs inside the language and CORS middleware: auth errors are translated
# and still carry CORS headers. Misconfigured auth fails here, at startup, not per request.
app.add_middleware(AuthMiddleware, authenticator=build_authenticator(get_settings()))


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
app.include_router(runs.router)
app.include_router(webhooks.router)
app.include_router(integrations.router)
app.include_router(workspaces.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/agents")
def list_agents() -> dict:
    """Worker agents, including installed plugins, and plugins that failed to load."""
    return {
        "agents": [
            {"id": s.id, "name": s.title, "version": s.version, "source": s.source,
             "capability": s.capability, "output_schema": s.output_schema}
            for s in agent_registry.specs().values()
        ],
        "problems": agent_registry.problems(),
        "workflow_problems": workflow_problems,
    }


@app.get("/system")
def system_status() -> dict:
    """Which platform features are on — never secret values."""
    import importlib.util

    from ma_pmo.core import tracing

    s = get_settings()
    retriever = s.retriever.strip().lower() or "lexical"
    return {
        "version": __version__,
        "auth": {"mode": s.auth_mode.strip().lower() or "off"},
        "tracing": {"enabled": tracing._tracer is not None,
                    "exporter": "otlp" if tracing._global_mode == "otlp" else
                    "console" if tracing._tracer is not None else None},
        "retriever": {"mode": retriever,
                      "model": (s.embedding_model or "char-ngrams") if retriever == "vector"
                      else None},
        "calendar": {"configured": bool(s.calendar_dir)},
        "mcp": {"installed": importlib.util.find_spec("mcp") is not None},
        "hitl_threshold": s.hitl_confidence_threshold,
    }


@app.get("/auth/whoami")
def whoami(principal: CurrentPrincipal) -> dict:
    """Who the API thinks you are, and with which roles in this workspace."""
    return {"subject": principal.subject, "roles": sorted(principal.roles),
            "workspace": workspace.current(), "auth_enabled": principal is not ANONYMOUS}


@app.get("/portfolio/{portfolio_id}")
def portfolio_status(portfolio_id: str) -> dict:
    """Portfolio and project progress for the dashboard."""
    return get_tracker().get_portfolio_status(portfolio_id)


@app.post("/demo/gated-message")
def demo_gated_message(task_ref: str = DEFAULT_SCOPE) -> dict:
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
