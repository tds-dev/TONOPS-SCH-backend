"""Working-time calculation (pure functions, no database).

`expand_working_time` turns weekly patterns (site local time) plus exceptions
(UTC) into a sorted list of non-overlapping UTC intervals. The scheduling
engine reuses it.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.timeutil import to_utc_naive

Interval = tuple[datetime, datetime]  # naive UTC, [start, end)


@dataclass(frozen=True)
class PatternSpec:
    day_of_week: int  # 1 = Mon ... 7 = Sun
    start: time
    end: time
    valid_from: date | None = None
    valid_to: date | None = None


@dataclass(frozen=True)
class ExceptionSpec:
    start: datetime  # naive UTC
    end: datetime  # naive UTC
    is_working: bool


def merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for s, e in sorted(i for i in intervals if i[1] > i[0]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract(intervals: list[Interval], holes: list[Interval]) -> list[Interval]:
    result: list[Interval] = []
    holes = merge(holes)
    for s, e in intervals:
        pieces = [(s, e)]
        for hs, he in holes:
            nxt: list[Interval] = []
            for ps, pe in pieces:
                if he <= ps or hs >= pe:
                    nxt.append((ps, pe))
                    continue
                if hs > ps:
                    nxt.append((ps, hs))
                if he < pe:
                    nxt.append((he, pe))
            pieces = nxt
        result.extend(pieces)
    return merge(result)


def clip(intervals: list[Interval], start: datetime, end: datetime) -> list[Interval]:
    return [(max(s, start), min(e, end)) for s, e in intervals if e > start and s < end]


def expand_working_time(
    patterns: list[PatternSpec],
    exceptions: list[ExceptionSpec],
    start: datetime,
    end: datetime,
    tz: str,
) -> list[Interval]:
    """Working intervals (naive UTC) between `start` and `end` (naive UTC)."""
    zone = ZoneInfo(tz)
    # Walk local dates, one day before start (night shifts crossing midnight)
    first_local = start.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).date() - timedelta(days=1)
    last_local = end.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).date()
    base: list[Interval] = []
    day = first_local
    while day <= last_local:
        for p in patterns:
            if p.day_of_week != day.isoweekday():
                continue
            if p.valid_from and day < p.valid_from:
                continue
            if p.valid_to and day > p.valid_to:
                continue
            local_start = datetime.combine(day, p.start)
            end_day = day + timedelta(days=1) if p.end <= p.start else day
            local_end = datetime.combine(end_day, p.end)
            base.append((to_utc_naive(local_start, tz), to_utc_naive(local_end, tz)))
        day += timedelta(days=1)
    working = merge(base + [(x.start, x.end) for x in exceptions if x.is_working])
    working = subtract(working, [(x.start, x.end) for x in exceptions if not x.is_working])
    return clip(working, start, end)
