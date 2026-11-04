"""Lab 1: a notifier that appends events to a JSON Lines file.

Fill in every TODO, then run `ma-pmo learn check 1`. The lab guide is README.md.
"""
from __future__ import annotations

from pathlib import Path

from ma_pmo.core.config import Settings
from ma_pmo.integrations.base import Event, IntegrationSpec

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class FileNotifier:
    name = "file"

    def __init__(self, path: str | Path, *, min_severity: str = "info") -> None:
        self.path = Path(path)
        self.min_severity = min_severity
        # TODO (step 4): reject a min_severity that is not in SEVERITY_ORDER with ValueError

    @classmethod
    def from_settings(cls, settings: Settings) -> FileNotifier:
        # TODO (step 5): read the path from the MA_PMO_NOTIFY_FILE environment variable
        # (default "ma-pmo-events.jsonl") and min_severity from
        # MA_PMO_NOTIFY_FILE_MIN_SEVERITY (default "info").
        raise NotImplementedError

    def send(self, event: Event) -> None:
        # TODO (steps 2-4): skip events below min_severity; otherwise append
        # event.as_dict() as one JSON line. Let write errors raise.
        raise NotImplementedError


# TODO (step 1): describe the integration so the registry can find it.
SPEC = IntegrationSpec(
    name="TODO",
    kind="tracker",
    description="TODO",
    required_settings=(),
    factory=FileNotifier.from_settings,
)
