"""The scheduling problem as plain data. Times are integer minutes from the
plan's horizon start (0 .. horizon). No database or OR-Tools imports here."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


@dataclass
class PResource:
    id: int
    code: str
    name: str
    capacity: int  # 1 = one task at a time
    windows: list[tuple[int, int]]  # working time, minutes [start, end)
    group_id: int | None = None


@dataclass
class POption:
    resource_id: int
    duration: int  # minutes, includes the option's fixed setup
    priority: int = 1


@dataclass
class PLock:
    resource_id: int
    start: int
    end: int


@dataclass
class PTask:
    id: int
    job_id: int
    name: str
    attrs: dict[str, Any]
    options: list[POption]
    release: int = 0  # earliest start (minutes)
    deadline: int | None = None  # task-level deadline (minutes)
    lock: PLock | None = None  # fixed position (locked / frozen / in progress)
    hint: PLock | None = None  # previous position, for warm start and stability


@dataclass
class PDependency:
    pred: int
    succ: int
    type: str = "FS"  # FS / SS / FF / SF
    lag: int = 0
    max_lag: int | None = None


@dataclass
class PJob:
    id: int
    no: str
    due: int | None  # minutes, may be negative (already late)
    priority: int = 50  # 1 = highest


@dataclass
class PChangeover:
    """Sequence-dependent setup on a set of resources, keyed by one attribute."""

    id: int
    attribute: str
    resource_ids: set[int]
    default: int
    entries: dict[tuple[str, str], tuple[int, bool]]  # (from, to) -> (minutes, forbidden)

    def lookup(self, frm: Any, to: Any) -> tuple[int, bool]:
        f, t = str(frm), str(to)
        if f == t:
            return self.entries.get((f, t), (0, False))
        for key in ((f, t), (f, "*"), ("*", t), ("*", "*")):
            if key in self.entries:
                return self.entries[key]
        return (self.default, False)


@dataclass
class PRule:
    id: int
    type_key: str
    name: str
    selector: dict[str, Any]
    params: dict[str, Any]
    hard: bool = True
    weight: int = 100


@dataclass
class Problem:
    horizon_start: datetime  # naive UTC
    horizon: int  # minutes
    tz: str
    resources: dict[int, PResource]
    tasks: dict[int, PTask]
    jobs: dict[int, PJob]
    dependencies: list[PDependency] = field(default_factory=list)
    changeovers: list[PChangeover] = field(default_factory=list)
    rules: list[PRule] = field(default_factory=list)
    weights: dict[str, int] = field(default_factory=dict)
    time_limit_sec: int = 60

    def to_dt(self, minute: int) -> datetime:
        return self.horizon_start + timedelta(minutes=minute)

    def to_min(self, dt: datetime) -> int:
        return int((dt - self.horizon_start).total_seconds() // 60)

    def local_days(self) -> list[tuple[date, int, int]]:
        """Each local calendar day overlapping the horizon: (date, start_min, end_min)."""
        zone = ZoneInfo(self.tz)
        utc = ZoneInfo("UTC")
        start_local = self.horizon_start.replace(tzinfo=utc).astimezone(zone)
        day = start_local.date()
        out = []
        while True:
            d0 = datetime.combine(day, datetime.min.time(), tzinfo=zone).astimezone(utc).replace(tzinfo=None)
            d1 = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone)
            d1 = d1.astimezone(utc).replace(tzinfo=None)
            s, e = max(0, self.to_min(d0)), min(self.horizon, self.to_min(d1))
            if s >= self.horizon:
                break
            if e > s:
                out.append((day, s, e))
            day += timedelta(days=1)
        return out


def matches(selector: dict[str, Any], attrs: dict[str, Any]) -> bool:
    """Rule selector against task attributes.

    {"family": "A"}                       equality
    {"family": {"in": ["A", "B"]}}        membership
    {"family": {"ne": "C"}}               not equal
    {"family": {"notIn": ["C"]}}          not a member
    {}                                    matches every task
    """
    for key, cond in (selector or {}).items():
        value = attrs.get(key)
        if isinstance(cond, dict):
            if "in" in cond and value not in cond["in"]:
                return False
            if "notIn" in cond and value in cond["notIn"]:
                return False
            if "ne" in cond and value == cond["ne"]:
                return False
            if "eq" in cond and value != cond["eq"]:
                return False
        elif value != cond:
            return False
    return True
