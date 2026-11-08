"""Agent registry — the one place that says which worker agents exist.

An `AgentSpec` describes a worker: its id, its name, how the orchestrator should route to it
(a line for the LLM prompt, keywords for the rule-based fallback), the payload it produces and a
factory. Routing, the graph and scenarios all read from here, so adding an agent means adding
a spec. Agents are built on first use, not at import time.

Other packages add agents through the `ma_pmo.agents` entry-point group (see docs/PLUGINS.md and
`ma_pmo.sdk`). Plugin ids are namespaced (`vendor.name`), and a plugin that cannot load is
logged, reported by `problems()` and skipped: it never stops the app.
"""
from __future__ import annotations

import importlib
import re
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib.metadata import entry_points
from typing import Any

from pydantic import BaseModel

from ma_pmo.agents.base import BaseAgent
from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import get_logger
from ma_pmo.core.schemas.payloads import PAYLOAD_REGISTRY

ENTRY_POINT_GROUP = "ma_pmo.agents"
_PLUGIN_ID = re.compile(r"^[a-z0-9_-]+\.[a-z0-9_-]+$")
_log = get_logger("agents")


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: tuple[str, str]  # (English, Korean), e.g. ("Planning", "계획")
    version: str
    capability: str  # one line for the orchestrator's prompt
    keywords: tuple[str, ...]  # rule-based routing, English and Korean
    default_task: tuple[str, str]  # (English, Korean) task when routed by keyword
    output_schema: str  # payload schema it publishes, e.g. "schedule.v1"
    factory: Callable[[], BaseAgent[Any]]
    payload: type[BaseModel] | None = None  # plugins: model that validates `output_schema`
    source: str = "builtin"  # set to the distribution name for plugins
    routable: bool = True  # False: runs only where a workflow puts it, never chosen by A1

    @property
    def title(self) -> str:
        return tr(*self.name)


def _lazy(module: str, cls: str) -> Callable[[], BaseAgent[Any]]:
    def build() -> BaseAgent[Any]:
        agent: BaseAgent[Any] = getattr(importlib.import_module(module), cls)()
        return agent

    return build


# order matters: keyword routing delegates in this order
BUILTINS: tuple[AgentSpec, ...] = (
    AgentSpec(
        id="A5", name=("Reporting", "보고"), version="1",
        capability="Reporting (executive reports/Q&A): report, status, executive summary",
        keywords=("보고", "현황", "리포트", "경영", "report", "status", "executive", "briefing"),
        default_task=("Generate portfolio executive report", "포트폴리오 경영 보고 생성"),
        output_schema="report.v1",
        factory=_lazy("ma_pmo.agents.reporting", "ReportingAgent"),
    ),
    AgentSpec(
        id="A4", name=("Risk", "리스크"), version="1",
        capability="Risk (early detection): risk, early warning, delay check",
        keywords=("리스크", "위험", "조기경보", "지연", "risk", "delay", "warning", "escalat"),
        default_task=("Early risk detection", "리스크 조기탐지"),
        output_schema="risk_alert.v1",
        factory=_lazy("ma_pmo.agents.risk", "RiskAgent"),
    ),
    AgentSpec(
        id="A2", name=("Planning", "계획"), version="1",
        capability="Planning (schedule/CPM): schedule, critical path, CPM",
        keywords=("일정", "스케줄", "임계경로", "cpm", "plan", "schedule", "critical path",
                  "baseline"),
        default_task=("Compute CPM schedule", "CPM 일정 산출"),
        output_schema="schedule.v1",
        factory=_lazy("ma_pmo.agents.planning", "PlanningAgent"),
    ),
    AgentSpec(
        id="A3", name=("Resources", "자원"), version="1",
        capability="Resources (allocation/load): resource, allocation, staffing, load, idle",
        keywords=("자원", "배분", "인력", "부하", "유휴", "resource", "allocat", "capacity",
                  "staff"),
        default_task=("Allocate resources", "자원 배분"),
        output_schema="allocation.v1",
        factory=_lazy("ma_pmo.agents.resource", "ResourceAgent"),
    ),
    AgentSpec(
        id="A6", name=("Governance", "거버넌스"), version="1",
        capability="Governance (gates/quality): gate, quality, governance, methodology compliance",
        keywords=("게이트", "품질", "거버넌스", "방법론", "준수", "gate", "quality", "governance",
                  "compliance"),
        default_task=("Gate review", "게이트 심사"),
        output_schema="gate_review.v1",
        factory=_lazy("ma_pmo.agents.governance", "GovernanceAgent"),
    ),
    AgentSpec(
        id="A7", name=("Knowledge", "지식"), version="1",
        capability="Knowledge (RAG): knowledge, lessons learned, similar cases, estimate evidence",
        keywords=("지식", "교훈", "유사", "사례", "견적", "knowledge", "lesson", "similar",
                  "estimat"),
        default_task=("Search knowledge and lessons learned", "지식·교훈 검색"),
        output_schema="knowledge.v1",
        factory=_lazy("ma_pmo.agents.knowledge", "KnowledgeAgent"),
    ),
    AgentSpec(
        id="A8", name=("Auditor", "감사"), version="1",
        capability="Auditor (dedicated review): checks other agents' decisions against the board",
        keywords=(),
        default_task=("Review decisions against the board", "게시판 근거로 결정 검토"),
        output_schema="review.v1",
        factory=_lazy("ma_pmo.agents.auditor", "AuditorAgent"),
        routable=False,
    ),
)

_instances: dict[str, BaseAgent[Any]] = {}
_lock = threading.Lock()


def _check_plugin(spec: Any) -> str | None:
    """Why this entry point cannot be used, or None."""
    if not isinstance(spec, AgentSpec):
        return "entry point is not an AgentSpec"
    if not _PLUGIN_ID.match(spec.id):
        return f"id '{spec.id}' must look like vendor.name"
    if spec.payload is None:
        return f"{spec.id} must declare the payload model for {spec.output_schema}"
    if ".v" not in spec.output_schema:
        return f"schema '{spec.output_schema}' must include a version, e.g. acme_budget.v1"
    if spec.output_schema in {b.output_schema for b in BUILTINS}:
        return f"schema '{spec.output_schema}' belongs to a built-in agent"
    return None


@lru_cache(maxsize=1)
def _plugins() -> tuple[tuple[AgentSpec, ...], tuple[str, ...]]:
    loaded: dict[str, AgentSpec] = {}
    problems: list[str] = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            spec = ep.load()
            problem = _check_plugin(spec)
        except Exception as e:  # a broken plugin must not break the app
            problem = f"{type(e).__name__}: {e}"[:200]
        if problem is None and spec.id in loaded:
            problem = f"id '{spec.id}' is already used by {loaded[spec.id].source}"
        if problem is not None:
            problems.append(f"{ep.name}: {problem}")
            _log.warning("agent_plugin_skipped", entry_point=ep.name, problem=problem)
            continue
        source = ep.dist.name if ep.dist is not None else ep.name
        loaded[spec.id] = replace(spec, source=source)
        PAYLOAD_REGISTRY[spec.output_schema] = spec.payload
    return tuple(loaded.values()), tuple(problems)


def reload_plugins() -> None:
    """Forget loaded plugins, so the next lookup reads the entry points again."""
    for spec in _plugins()[0]:
        PAYLOAD_REGISTRY.pop(spec.output_schema, None)
        _instances.pop(spec.id, None)
    _plugins.cache_clear()


def problems() -> list[str]:
    """Plugins that could not be loaded, with the reason."""
    return list(_plugins()[1])


def specs() -> dict[str, AgentSpec]:
    """Worker specs by id, in routing order: built-ins first, then plugins."""
    return {spec.id: spec for spec in (*BUILTINS, *_plugins()[0])}


def worker_ids() -> list[str]:
    return list(specs())


def routable() -> dict[str, AgentSpec]:
    """The workers A1 may delegate a goal to (an auditor only runs where a workflow puts it)."""
    return {i: spec for i, spec in specs().items() if spec.routable}


def get(agent_id: str) -> BaseAgent[Any]:
    """The shared instance of a worker, built on first use. KeyError if unknown."""
    with _lock:
        if agent_id not in _instances:
            _instances[agent_id] = specs()[agent_id].factory()
        return _instances[agent_id]


def title(agent_id: str) -> str:
    """Display name in the current language; the id itself for an unknown agent."""
    spec = specs().get(agent_id)
    return spec.title if spec else agent_id


class _Workers(Mapping[str, BaseAgent[Any]]):
    """Read-only view of the workers that builds an agent only when it is looked up."""

    def __getitem__(self, agent_id: str) -> BaseAgent[Any]:
        return get(agent_id)

    def __iter__(self) -> Iterator[str]:
        return iter(specs())

    def __len__(self) -> int:
        return len(specs())


WORKERS: Mapping[str, BaseAgent[Any]] = _Workers()
