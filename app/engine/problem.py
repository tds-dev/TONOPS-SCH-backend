"""スケジューリング問題を素のデータで表す。時刻は計画期間開始からの
整数分（0 .. horizon）。DB や OR-Tools はここでは import しない。"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


@dataclass
class PResource:
    id: int
    code: str
    name: str
    capacity: int  # 1 = 同時に 1 タスクのみ
    windows: list[tuple[int, int]]  # 稼働時間（分）[開始, 終了)
    group_id: int | None = None


@dataclass
class POption:
    resource_id: int
    duration: int  # 分。候補ごとの固定段取りを含む
    priority: int = 1


@dataclass
class PLock:
    resource_id: int
    start: int
    end: int


@dataclass
class PTask:
    id: int
    order_id: int  # この工程作業が所属するオーダーのID。
    name: str
    attrs: dict[str, Any]
    options: list[POption]
    release: int = 0  # 最早開始（分）
    deadline: int | None = None  # タスク単位の期限（分）
    lock: PLock | None = None  # 固定位置（ロック・確定期間・作業中）
    hint: PLock | None = None  # 前回の位置（初期解と安定性に使用）


@dataclass
class PDependency:
    pred: int
    succ: int
    type: str = "FS"  # FS / SS / FF / SF
    lag: int = 0
    max_lag: int | None = None


@dataclass
class POrder:
    """納期と優先度を持つ、計算対象のオーダー。"""

    id: int
    no: str
    due: int | None  # 分。負の値もありうる（既に遅れている）
    priority: int = 50  # 1 = 最優先


@dataclass
class PChangeover:
    """リソース群に対する順序依存の段取り。1 つの属性をキーとする。"""

    id: int
    attribute: str
    resource_ids: set[int]
    default: int
    entries: dict[tuple[str, str], tuple[int, bool]]  # (切替前, 切替後) -> (分, 禁止)

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
    horizon_start: datetime  # naive な UTC
    horizon: int  # 分
    tz: str
    resources: dict[int, PResource]
    tasks: dict[int, PTask]
    orders: dict[int, POrder]  # オーダーIDをキーに、案件全体の計算条件を保持する。
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
        """計画期間に重なる現地の各暦日: (日付, 開始分, 終了分)。"""
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
    """ルールのセレクターをタスク属性と照合する。

    {"family": "A"}                       一致
    {"family": {"in": ["A", "B"]}}        いずれかに一致
    {"family": {"ne": "C"}}               不一致
    {"family": {"notIn": ["C"]}}          いずれにも不一致
    {}                                    すべてのタスクに一致
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
