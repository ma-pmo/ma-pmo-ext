"""Integration contracts.

Two kinds of integration plug into MA-PMO:

- **Notifiers** (outbound): receive `Event`s such as "approval requested" or "risk detected"
  and deliver them somewhere (Slack, a webhook, ...).
- **Trackers** (inbound): implement `IssueTrackerConnector.get_portfolio_status` so agents
  read real project data (Jira, ...) instead of the bundled demo fixtures.

An `IntegrationSpec` describes one integration: its name, kind, the settings it needs and a
factory that builds it from `Settings`. Built-ins are registered in `registry.py`; third-party
packages add their own through the `ma_pmo.integrations` entry-point group.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable

from ma_pmo.core.config import Settings


class EventType(str, Enum):
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    RISK_DETECTED = "risk.detected"
    GATE_FAILED = "gate.failed"
    REPORT_GENERATED = "report.generated"
    BUDGET_WARNING = "budget.warning"
    TEST = "integration.test"


@dataclass(frozen=True)
class Event:
    """A user-facing happening that notifiers can deliver."""

    type: EventType
    title: str
    summary: str
    severity: Literal["info", "warning", "critical"] = "info"
    task_ref: str = ""
    url: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "task_ref": self.task_ref,
            "url": self.url,
            "data": self.data,
            "occurred_at": self.occurred_at.isoformat(),
        }


@runtime_checkable
class Notifier(Protocol):
    name: str

    def send(self, event: Event) -> None:
        """Deliver the event. Raise on failure; the dispatcher isolates errors."""
        ...


Kind = Literal["notifier", "tracker"]


@dataclass(frozen=True)
class IntegrationSpec:
    name: str
    kind: Kind
    description: str
    # Settings attribute names that must be non-empty for the integration to work
    required_settings: tuple[str, ...]
    factory: Callable[[Settings], Any]

    def missing_settings(self, settings: Settings) -> list[str]:
        return [s for s in self.required_settings if not getattr(settings, s, "")]
