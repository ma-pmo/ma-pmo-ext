"""Resource calendars — how many hours a person is already busy in a week (used by A3).

A calendar connector answers one question: `busy_hours(resource_id, week)` for an ISO week
such as "2026-W03". A3 subtracts it from the person's weekly capacity before allocating work.

Built in: `IcsCalendar`, which reads one iCalendar file per resource from a folder
(`MA_PMO_CALENDAR_DIR/<resource_id>.ics`). Every calendar app exports .ics (Google Calendar,
Outlook, Apple Calendar), so this works without OAuth. Counting rules:

- only Monday–Friday count, at most `hours_per_day` (8) busy hours per day;
- all-day events (holidays, leave) block the whole working day;
- events marked free (`TRANSP:TRANSPARENT`) or cancelled are ignored;
- times are counted as written in the file (time zones are not converted);
- recurring events (`RRULE`) count only their first occurrence — export a date range with the
  occurrences expanded, which most calendar apps do for .ics exports.

A resource without a file is treated as fully available.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Protocol

HOURS_PER_DAY = 8.0


class CalendarConnector(Protocol):
    def busy_hours(self, resource_id: str, week: str) -> float:
        """Busy working hours of `resource_id` in ISO week `week` ("YYYY-Www")."""
        ...


@dataclass(frozen=True)
class Event:
    start: datetime
    end: datetime
    all_day: bool


def week_days(week: str) -> list[date]:
    """Monday–Friday of an ISO week label such as "2026-W03"."""
    year, _, num = week.partition("-W")
    return [date.fromisocalendar(int(year), int(num), d) for d in range(1, 6)]


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw.rstrip("\r"))
    return lines


def _parse_value(prop: str, value: str) -> tuple[datetime, bool]:
    """(moment, is_date) from DTSTART/DTEND; time zones are dropped."""
    value, params = value.strip(), prop.upper()
    is_date = len(value) == 8 or ("VALUE=DATE" in params and "VALUE=DATE-TIME" not in params)
    if is_date:
        return datetime.strptime(value[:8], "%Y%m%d"), True
    return datetime.strptime(value[:15], "%Y%m%dT%H%M%S"), False


def _parse_duration(value: str) -> timedelta:
    """The common subset of RFC 5545 durations: P#W, P#D, PT#H#M#S."""
    value = value.strip().lstrip("+")
    sign = -1 if value.startswith("-") else 1
    value = value.lstrip("-").lstrip("P")
    total, number = timedelta(), ""
    in_time = False
    units = {"W": timedelta(weeks=1), "D": timedelta(days=1), "H": timedelta(hours=1),
             "M": timedelta(minutes=1), "S": timedelta(seconds=1)}
    for ch in value:
        if ch == "T":
            in_time = True
        elif ch.isdigit():
            number += ch
        elif ch in units and number:
            if ch == "M" and not in_time:
                raise ValueError("month durations are not supported")
            total += int(number) * units[ch]
            number = ""
    return sign * total


def parse_ics(text: str) -> list[Event]:
    events: list[Event] = []
    current: dict[str, tuple[str, str]] | None = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT" and current is not None:
            event = _to_event(current)
            if event is not None:
                events.append(event)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        prop, value = line.split(":", 1)
        name = prop.split(";", 1)[0].upper()
        current[name] = (prop, value)
    return events


def _to_event(props: dict[str, tuple[str, str]]) -> Event | None:
    if "DTSTART" not in props:
        return None
    if props.get("TRANSP", ("", ""))[1].strip().upper() == "TRANSPARENT":
        return None
    if props.get("STATUS", ("", ""))[1].strip().upper() == "CANCELLED":
        return None
    start, all_day = _parse_value(*props["DTSTART"])
    if "DTEND" in props:
        end, _ = _parse_value(*props["DTEND"])
    elif "DURATION" in props:
        end = start + _parse_duration(props["DURATION"][1])
    else:
        end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
    return Event(start, end, all_day) if end > start else None


def busy_hours_in_week(events: list[Event], week: str,
                       hours_per_day: float = HOURS_PER_DAY) -> float:
    total = 0.0
    for day in week_days(week):
        day_start = datetime.combine(day, time())
        day_end = day_start + timedelta(days=1)
        busy = 0.0
        for ev in events:
            if ev.end <= day_start or ev.start >= day_end:
                continue
            if ev.all_day:
                busy = hours_per_day
                break
            overlap = min(ev.end, day_end) - max(ev.start, day_start)
            busy += overlap.total_seconds() / 3600
        total += min(busy, hours_per_day)
    return round(total, 2)


@lru_cache(maxsize=256)
def _events_of(path: str, mtime: float) -> tuple[Event, ...]:
    return tuple(parse_ics(Path(path).read_text(encoding="utf-8", errors="replace")))


class IcsCalendar:
    def __init__(self, directory: str | Path, hours_per_day: float = HOURS_PER_DAY) -> None:
        self.directory = Path(directory)
        self.hours_per_day = hours_per_day

    def busy_hours(self, resource_id: str, week: str) -> float:
        path = self.directory / f"{resource_id}.ics"
        if not path.is_file():
            return 0.0
        events = _events_of(str(path), path.stat().st_mtime)
        return busy_hours_in_week(list(events), week, self.hours_per_day)


def get_calendar() -> CalendarConnector | None:
    """The configured calendar (`MA_PMO_CALENDAR_DIR`), or None when not configured."""
    from ma_pmo.core.config import get_settings

    directory = get_settings().calendar_dir
    return IcsCalendar(directory) if directory else None
