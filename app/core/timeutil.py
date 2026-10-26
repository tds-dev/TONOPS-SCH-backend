"""Time helpers. All datetimes in the database are naive UTC (datetime2(0))."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Current time as naive UTC, truncated to seconds."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def to_utc_naive(dt: datetime, tz: str | None = None) -> datetime:
    """Convert an aware datetime (or a naive one in `tz`) to naive UTC."""
    if dt.tzinfo is None:
        if tz is None:
            return dt  # already naive UTC by convention
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(dt: datetime, tz: str) -> datetime:
    """Naive UTC -> aware local time in `tz`."""
    return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
