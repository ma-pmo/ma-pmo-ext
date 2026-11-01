"""Pluggable integrations: notifiers (Slack, webhooks, …) and trackers (Jira, …).

See docs/INTEGRATIONS.md for setup and for writing your own integration.
"""
from ma_pmo.integrations.base import Event, EventType, IntegrationSpec, Notifier
from ma_pmo.integrations.dispatch import emit
from ma_pmo.integrations.registry import available, build_notifiers, get_tracker, status

__all__ = [
    "Event",
    "EventType",
    "IntegrationSpec",
    "Notifier",
    "available",
    "build_notifiers",
    "emit",
    "get_tracker",
    "status",
]
