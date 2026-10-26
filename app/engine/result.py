"""Shared result types for the engine (pure Python)."""
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from app.engine.problem import Problem


@dataclass
class SAssignment:
    task_id: int
    resource_id: int
    start: int  # minutes from horizon start (processing start)
    end: int
    setup: int = 0  # sequence-dependent setup immediately before `start`
    locked: bool = False


@dataclass
class Violation:
    severity: str  # HARD / SOFT / INFO
    code: str
    message: str
    task_id: int | None = None
    rule_id: int | None = None
    penalty: float | None = None


def fmt(problem: Problem, minute: int) -> str:
    """Minute offset -> 'MM/DD HH:MM' in site time (for messages)."""
    local = problem.to_dt(minute).replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(problem.tz))
    return local.strftime("%m/%d %H:%M")


def fmt_duration(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}時間{m:02d}分" if h else f"{m}分"
