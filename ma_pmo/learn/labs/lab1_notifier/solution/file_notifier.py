"""Lab 1 reference solution: a notifier that appends events to a JSON Lines file."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ma_pmo.core.config import Settings
from ma_pmo.integrations.base import Event, IntegrationSpec

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class FileNotifier:
    name = "file"

    def __init__(self, path: str | Path, *, min_severity: str = "info") -> None:
        if min_severity not in SEVERITY_ORDER:
            raise ValueError(f"min_severity must be one of {list(SEVERITY_ORDER)}")
        self.path = Path(path)
        self.min_severity = min_severity

    @classmethod
    def from_settings(cls, settings: Settings) -> FileNotifier:
        return cls(
            os.environ.get("MA_PMO_NOTIFY_FILE", "ma-pmo-events.jsonl"),
            min_severity=os.environ.get("MA_PMO_NOTIFY_FILE_MIN_SEVERITY", "info"),
        )

    def send(self, event: Event) -> None:
        if SEVERITY_ORDER[event.severity] < SEVERITY_ORDER[self.min_severity]:
            return
        # No try/except here: if the file cannot be written, the dispatcher records the
        # failure and keeps the agent pipeline running.
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")


SPEC = IntegrationSpec(
    name="file",
    kind="notifier",
    description="Append every event to a local JSON Lines file.",
    required_settings=(),
    factory=FileNotifier.from_settings,
)
