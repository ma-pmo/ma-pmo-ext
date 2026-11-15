"""Time values as the API returns them."""
from __future__ import annotations

from datetime import datetime


def iso(value: datetime | None) -> str | None:
    """ISO 8601 text of a timestamp, or None when there is none."""
    return value.isoformat() if value else None
