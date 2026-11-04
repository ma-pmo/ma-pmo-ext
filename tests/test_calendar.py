"""Resource calendars: .ics parsing, busy-hour rules, and A3 allocating around busy weeks."""
from __future__ import annotations

from ma_pmo.agents.allocation import allocate
from ma_pmo.agents.resource import ResourceAgent
from ma_pmo.connectors.calendar import IcsCalendar, busy_hours_in_week, parse_ics, week_days

# 2026-W03 is Mon 12 Jan – Fri 16 Jan 2026
ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Workshop
DTSTART:20260112T090000Z
DTEND:20260112T120000Z
END:VEVENT
BEGIN:VEVENT
SUMMARY:Annual leave
DTSTART;VALUE=DATE:20260114
DTEND;VALUE=DATE:20260116
END:VEVENT
BEGIN:VEVENT
SUMMARY:Focus time (shown as free)
DTSTART:20260113T090000
DTEND:20260113T170000
TRANSP:TRANSPARENT
END:VEVENT
BEGIN:VEVENT
SUMMARY:Cancelled review
DTSTART:20260113T130000
DTEND:20260113T150000
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
SUMMARY:Offsite with a long description that the exporter
 folded onto a second line
DTSTART;TZID=Asia/Seoul:20260116T080000
DURATION:PT10H
END:VEVENT
BEGIN:VEVENT
SUMMARY:Saturday hackathon
DTSTART:20260117T090000
DTEND:20260117T180000
END:VEVENT
END:VCALENDAR
"""


def test_week_days():
    assert [d.isoformat() for d in week_days("2026-W03")] == [
        "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16"]


def test_parse_and_busy_rules():
    events = parse_ics(ICS)
    assert len(events) == 4  # free and cancelled events are dropped
    # Mon 3h workshop + Wed/Thu leave 2×8h + Fri 10h offsite capped at 8h; Saturday ignored
    assert busy_hours_in_week(events, "2026-W03") == 3 + 16 + 8
    assert busy_hours_in_week(events, "2026-W04") == 0


def test_allocator_takes_busy_hours_off_capacity():
    projects = [{"project_id": "P", "skill": "data", "tasks": [{"effort": 60.0}]}]
    resources = [{"id": "R", "skill": "data", "capacity": 40.0}]
    free = allocate(projects, resources)
    assert [(ln.week, ln.hours) for ln in free.lines] == [("2026-W03", 40.0), ("2026-W04", 20.0)]
    blocked = allocate(projects, resources,
                       busy=lambda rid, week: 30.0 if week == "2026-W03" else 0.0)
    assert [(ln.week, ln.hours) for ln in blocked.lines] == [("2026-W03", 10.0),
                                                            ("2026-W04", 40.0),
                                                            ("2026-W05", 10.0)]
    # utilization is measured against the hours people actually had
    assert blocked.utilization_pct == round(60 / (10 + 40 + 40) * 100, 1)


def test_resource_agent_reads_ics_folder(tmp_path):
    (tmp_path / "R-03.ics").write_text(ICS, encoding="utf-8")
    calendar = IcsCalendar(tmp_path)
    assert calendar.busy_hours("R-03", "2026-W03") == 27
    assert calendar.busy_hours("R-99", "2026-W03") == 0  # no file: fully available

    plain = ResourceAgent(calendar=None)
    plain.calendar = None  # ignore any MA_PMO_CALENDAR_DIR on the machine running the tests
    with_cal = ResourceAgent(calendar=calendar)
    base = plain.allocate_portfolio()
    busy = with_cal.allocate_portfolio()
    w03 = lambda alloc: sum(ln["hours"] for ln in alloc["plan"]  # noqa: E731
                            if ln["resource_id"] == "R-03" and ln["week"] == "2026-W03")
    assert w03(busy) < w03(base)
