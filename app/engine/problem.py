"""スケジューリング問題を素のデータで表す。時刻は計画期間開始からの
整数分（0 .. horizon）。DB や OR-Tools はここでは import しない。"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


@dataclass
class PResource:
    # 計算で使う設備の識別番号・表示名・同時処理能力と稼働時間帯。
    id: int
    name: str
    capacity: int  # 1 = 同時に 1 タスクのみ
    windows: list[tuple[int, int]]  # 稼働時間（分）[開始, 終了)
    group_id: int | None = None


@dataclass
class POption:
    resource_id: int
    duration: int  # 分。候補ごとの固定段取りを含む


@dataclass
class PLock:
    resource_id: int
    start: int
    end: int


@dataclass
class PTask:
    id: int
    order_id: int  # このタスクが所属するオーダーのID。
    name: str
    attrs: dict[str, Any]
    options: list[POption]
    release: int = 0  # 最早開始（分）
    deadline: int | None = None  # タスク単位の期限（分）
    lock: PLock | None = None  # 固定位置（ロック・確定期間・作業中）
    hint: PLock | None = None  # 前回の位置（初期解と安定性に使用）
    # 最新の製品工程から取得した許可曜日。Noneは制限無効または適用期間外。
    allowed_weekdays: list[int] | None = None
    # 段取り替えの判定元となる製品工程。作業属性の有無に依存しない。
    product_process_id: int | None = None


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
    # ボードの製品単位の色分けに使う製品ID。
    product_id: int | None = None


@dataclass
class PChangeover:
    """リソース群に対する製品工程の順序依存の段取り。"""

    id: int
    resource_ids: set[int]
    default: int
    # (切替前工程ID, 切替後工程ID)→(分, 禁止)。キー内のNoneは任意指定。
    entries: dict[tuple[int | None, int | None], tuple[int, bool]]

    # 個別指定、切替前のみ、切替後のみ、両方任意の順に条件を探す。
    def lookup(self, frm: int | None, to: int | None) -> tuple[int, bool]:
        # 元工程が不明な既存作業には、任意指定を誤って当てはめない。
        if frm is None or to is None:
            return (0, False)
        if frm == to:
            return self.entries.get((frm, to), (0, False))
        for key in ((frm, to), (frm, None), (None, to), (None, None)):
            if key in self.entries:
                return self.entries[key]
        return (self.default, False)


@dataclass
class Problem:
    horizon_start: datetime  # 時差情報なしの日本時間
    horizon: int  # 分
    tz: str
    resources: dict[int, PResource]
    tasks: dict[int, PTask]
    orders: dict[int, POrder]  # オーダーIDをキーに、案件全体の計算条件を保持する。
    dependencies: list[PDependency] = field(default_factory=list)
    changeovers: list[PChangeover] = field(default_factory=list)
    weights: dict[str, int] = field(default_factory=dict)

    # 設備に適用する切替設定を、自動計算と手動編集で共用する。
    def changeover_for(self, resource_id: int) -> PChangeover | None:
        return next((changeover for changeover in self.changeovers if resource_id in changeover.resource_ids), None)

    def to_dt(self, minute: int) -> datetime:
        return self.horizon_start + timedelta(minutes=minute)

    def to_min(self, dt: datetime) -> int:
        return int((dt - self.horizon_start).total_seconds() // 60)

    def local_days(self) -> list[tuple[date, int, int]]:
        """計画期間に重なる現地の各暦日: (日付, 開始分, 終了分)。"""
        # 計画開始も暦日の境界も、保存値と同じ日本時間で扱う。
        start_local = self.horizon_start
        day = start_local.date()
        out = []
        while True:
            d0 = datetime.combine(day, datetime.min.time())
            d1 = datetime.combine(day + timedelta(days=1), datetime.min.time())
            s, e = max(0, self.to_min(d0)), min(self.horizon, self.to_min(d1))
            if s >= self.horizon:
                break
            if e > s:
                out.append((day, s, e))
            day += timedelta(days=1)
        return out

