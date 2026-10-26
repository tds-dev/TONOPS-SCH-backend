"""Load calendars from the database and expand them to working intervals.

Inheritance: a calendar without its own patterns uses its parent's patterns.
Exceptions from the whole chain (child and parents) all apply.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.masters import Calendar
from app.services.worktime import ExceptionSpec, Interval, PatternSpec, expand_working_time


def calendar_specs(db: Session, calendar_id: int) -> tuple[list[PatternSpec], list[ExceptionSpec]]:
    """Load patterns and exceptions for a calendar, following ParentCalendarID."""
    patterns: list[PatternSpec] = []
    exceptions: list[ExceptionSpec] = []
    seen: set[int] = set()
    cal = db.get(Calendar, calendar_id)
    while cal is not None and cal.CalendarID not in seen:
        seen.add(cal.CalendarID)
        if not patterns and cal.patterns:
            patterns = [
                PatternSpec(p.DayOfWeek, p.StartTime, p.EndTime, p.ValidFrom, p.ValidTo)
                for p in cal.patterns
            ]
        exceptions.extend(
            ExceptionSpec(x.StartAt, x.EndAt, bool(x.IsWorking)) for x in cal.exceptions
        )
        cal = cal.parent
    return patterns, exceptions


def working_time(
    db: Session, calendar_id: int, start: datetime, end: datetime, tz: str
) -> list[Interval]:
    patterns, exceptions = calendar_specs(db, calendar_id)
    return expand_working_time(patterns, exceptions, start, end, tz)
