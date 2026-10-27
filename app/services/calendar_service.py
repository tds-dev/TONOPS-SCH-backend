"""DB からカレンダーを読み込み、稼働区間に展開する。

継承: 自身のパターンを持たないカレンダーは親カレンダーのパターンを使う。
例外は継承チェーン全体（子と親）のものがすべて適用される。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.masters import Calendar
from app.services.worktime import ExceptionSpec, Interval, PatternSpec, expand_working_time


def calendar_specs(db: Session, calendar_id: int) -> tuple[list[PatternSpec], list[ExceptionSpec]]:
    """ParentCalendarID をたどってカレンダーのパターンと例外を読み込む。"""
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
