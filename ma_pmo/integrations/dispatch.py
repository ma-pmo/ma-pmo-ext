"""Deliver events to the enabled notifiers.

Delivery is best effort: a notifier that fails (network error, bad webhook URL, plugin bug)
is logged and skipped, so integrations can never break the agent pipeline.

The pipeline does not wait for delivery either: `emit_later` (used by message publishing,
approvals and budgets) hands the events to a background sender, so a slow or dead webhook costs
an agent run nothing. `emit` delivers at once and returns one row per attempt (tests, the
integration test endpoint). After `BREAKER_FAILURES` failures in a row a notifier is skipped for
`BREAKER_COOLDOWN_SEC`, so a dead endpoint is not waited on for every event.
"""
from __future__ import annotations

import atexit
import queue
import threading
import time
from collections.abc import Iterable, Sequence

from ma_pmo.core.config import Settings, get_settings
from ma_pmo.core.obs import get_logger
from ma_pmo.integrations.base import Event, EventType, Notifier
from ma_pmo.integrations.registry import build_notifiers, is_demo_only

_log = get_logger("integrations")

BREAKER_FAILURES = 3
BREAKER_COOLDOWN_SEC = 60.0
_failures: dict[str, tuple[int, float]] = {}  # notifier name -> (failures in a row, last at)
_lock = threading.Lock()


def wanted_types(settings: Settings) -> set[str]:
    return {t.strip() for t in settings.notify_events.split(",") if t.strip()}


def emit(events: Iterable[Event], *, notifiers: Sequence[Notifier] | None = None,
         settings: Settings | None = None) -> list[dict]:
    """Send each event to each notifier. Returns one result row per delivery attempt."""
    events = list(events)
    if not events or is_demo_only():  # a dry run tells nobody
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
            if _open(notifier.name):
                results.append({"integration": notifier.name, "event": event.type.value,
                                "ok": False, "error": "skipped: failing repeatedly"})
                continue
            try:
                notifier.send(event)
                _record(notifier.name, ok=True)
                results.append({"integration": notifier.name, "event": event.type.value,
                                "ok": True})
                _log.info("integration_sent", integration=notifier.name,
                          event_type=event.type.value)
            except Exception as e:
                _record(notifier.name, ok=False)
                results.append({"integration": notifier.name, "event": event.type.value,
                                "ok": False, "error": str(e)[:200]})
                _log.warning("integration_failed", integration=notifier.name,
                             event_type=event.type.value, error=str(e)[:200])
    return results


def _open(name: str) -> bool:
    """True while a notifier that keeps failing is being skipped."""
    with _lock:
        failures, last = _failures.get(name, (0, 0.0))
    return failures >= BREAKER_FAILURES and time.monotonic() - last < BREAKER_COOLDOWN_SEC


def _record(name: str, *, ok: bool) -> None:
    with _lock:
        if ok:
            _failures.pop(name, None)
        else:
            failures, _ = _failures.get(name, (0, 0.0))
            _failures[name] = (failures + 1, time.monotonic())
            if failures + 1 == BREAKER_FAILURES:
                _log.warning("integration_paused", integration=name,
                             seconds=BREAKER_COOLDOWN_SEC)


def reset_breakers() -> None:
    with _lock:
        _failures.clear()


# ── background delivery ────────────────────────────────────────────────────────────────

_queue: queue.Queue[tuple[list[Event], list[Notifier], Settings]] = queue.Queue()
_worker: threading.Thread | None = None


def emit_later(events: Iterable[Event]) -> None:
    """Deliver in the background; the caller never waits for a notifier.

    The targets are resolved now, in the caller's context (a dry run's sandbox tells nobody, and
    the settings of this request apply); only the sending happens later.
    """
    global _worker
    events = list(events)
    if not events or is_demo_only():
        return
    settings = get_settings()
    try:
        targets = build_notifiers(settings)
    except Exception as e:  # a misconfigured integration must not break the caller
        _log.warning("integration_build_failed", error=str(e))
        return
    if not targets:
        return
    _queue.put((events, list(targets), settings))
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_send_queued, name="ma-pmo-notify", daemon=True)
            _worker.start()


def _send_queued() -> None:
    while True:
        events, targets, settings = _queue.get()
        try:
            emit(events, notifiers=targets, settings=settings)
        except Exception as e:  # never let the sender die
            _log.warning("integration_failed", error=str(e)[:200])
        finally:
            _queue.task_done()


def flush(timeout: float = 30.0) -> bool:
    """Wait until queued events are delivered (or given up on); False if `timeout` ran out."""
    done = threading.Event()

    def wait() -> None:
        _queue.join()
        done.set()

    threading.Thread(target=wait, daemon=True).start()
    return done.wait(timeout)


@atexit.register
def _flush_at_exit() -> None:  # a CLI run should not drop its last notifications
    if _queue.unfinished_tasks:
        flush(timeout=get_settings().integration_timeout_sec * 2)
