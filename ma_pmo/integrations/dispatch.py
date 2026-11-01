"""Deliver events to the enabled notifiers.

Delivery is best effort: a notifier that fails (network error, bad webhook URL, plugin bug)
is logged and skipped, so integrations can never break the agent pipeline.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from ma_pmo.core.config import Settings, get_settings
from ma_pmo.core.obs import get_logger
from ma_pmo.integrations.base import Event, EventType, Notifier
from ma_pmo.integrations.registry import build_notifiers

_log = get_logger("integrations")


def wanted_types(settings: Settings) -> set[str]:
    return {t.strip() for t in settings.notify_events.split(",") if t.strip()}


def emit(events: Iterable[Event], *, notifiers: Sequence[Notifier] | None = None,
         settings: Settings | None = None) -> list[dict]:
    """Send each event to each notifier. Returns one result row per delivery attempt."""
    events = list(events)
    if not events:
        return []
    settings = settings or get_settings()
    try:
        targets = list(notifiers) if notifiers is not None else build_notifiers(settings)
    except Exception as e:  # a misconfigured integration must not break the caller
        _log.warning("integration_build_failed", error=str(e))
        return []
    if not targets:
        return []

    wanted = wanted_types(settings)
    results = []
    for event in events:
        if wanted and event.type.value not in wanted and event.type is not EventType.TEST:
            continue
        for notifier in targets:
            try:
                notifier.send(event)
                results.append({"integration": notifier.name, "event": event.type.value,
                                "ok": True})
                _log.info("integration_sent", integration=notifier.name,
                          event_type=event.type.value)
            except Exception as e:
                results.append({"integration": notifier.name, "event": event.type.value,
                                "ok": False, "error": str(e)[:200]})
                _log.warning("integration_failed", integration=notifier.name,
                             event_type=event.type.value, error=str(e)[:200])
    return results
