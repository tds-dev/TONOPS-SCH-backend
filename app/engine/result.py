"""エンジン共通の結果型（純粋 Python）。"""
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from app.engine.problem import Problem


@dataclass
class SAssignment:
    task_id: int
    resource_id: int
    start: int  # 計画期間開始からの分（作業開始時刻）
    end: int
    setup: int = 0  # `start` の直前に置く順序依存の段取り時間
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
    """分オフセット -> 拠点時刻の 'MM/DD HH:MM'（メッセージ用）。"""
    local = problem.to_dt(minute).replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(problem.tz))
    return local.strftime("%m/%d %H:%M")


def fmt_duration(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}時間{m:02d}分" if h else f"{m}分"
