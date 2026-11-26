"""日次バケット方式のスケジューリング問題データ（純粋Python、DB・OR-Tools非依存）。

時刻は計画期間内の稼働日インデックス（0 .. num_days - 1）で表す。
数量は小数第3位まで誤差なく整数演算するため QTY_SCALE（1000倍）で保持する。
"""
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

# 数量・1日作業台数上限（NUMERIC(18,3)）を整数で扱うための倍率。
QTY_SCALE = 1000


# Decimalやfloatの数量を整数スケール値（1000倍）へ変換する。
def scale_qty(value: Decimal | float | int | None) -> int:
    if value is None:
        return 0
    return int(round(Decimal(str(value)) * QTY_SCALE))


# 整数スケール値（1000倍）を表示用の文字列へ整える（整数なら小数部省略）。
def fmt_qty(scaled: int) -> str:
    if scaled % QTY_SCALE == 0:
        return str(scaled // QTY_SCALE)
    return f"{scaled / QTY_SCALE:.3f}".rstrip("0").rstrip(".")


@dataclass
class DayWorker:
    """日単位計算で割付先となる作業者と、1日上限・出勤可能日。"""

    id: int
    name: str
    # 1日の作業台数上限（QTY_SCALE倍）。Noneは上限なし。
    max_daily_qty: int | None
    # 計画期間内で出勤可能な稼働日インデックスの集合。
    available_days: set[int] = field(default_factory=set)
    # 計画期間と後続バッファを含む出勤可能日の昇順一覧（連休前制限の判定に使用）。
    available_dates: list[date] = field(default_factory=list)


@dataclass
class DayOrder:
    """日単位計算の対象オーダー。出荷日と台数・日上限除外フラグを保持する。"""

    id: int
    no: str
    name: str
    quantity_scaled: int
    exclude_from_daily_cap: bool = False
    # 出荷基準日の拡張稼働日インデックス（計画期間外も含む）。Noneは出荷日未指定。
    shipping_day_idx: int | None = None
    shipping_date: date | None = None
    priority: int = 50
    product_id: int | None = None
    # T_OrderWorkersで事前指定された担当作業者ID群。
    preferred_worker_ids: set[int] = field(default_factory=set)


@dataclass
class DayLock:
    """ロック済みまたは前回計画の割付位置（作業者と開始・終了の稼働日番号）。"""

    worker_id: int
    start_day: int
    end_day: int  # 終了日を含む閉区間（duration_days=1ならstart_day==end_day）


@dataclass
class DayTask:
    """日単位計算で日バケットと作業者を決定するタスク。"""

    id: int
    order_id: int
    name: str
    process_name: str
    product_process_id: int | None
    sequence_number: int
    # 同一オーダー内で同一作業者とする工程区分ID。Noneは単独区分扱い。
    process_group_id: int | None = None
    # 工程区分の先頭工程かつ日上限対象製品の場合のみTrue。
    counts_for_daily_cap: bool = True
    # 出荷日からの標準前倒し稼働日数と、逆算した標準作業日（拡張稼働日インデックス）。
    standard_offset_days: int | None = None
    standard_day_idx: int | None = None
    duration_days: int = 1
    # 実行可能な作業者ID一覧（スキルマップ＋オーダー指定作業者で絞り込み済み）。
    eligible_worker_ids: list[int] = field(default_factory=list)
    # 計画期間内の最早着手稼働日インデックス（0以上）。
    release_day_idx: int = 0
    # 工程の許可曜日（日曜0～土曜6）。Noneは制限なし。
    allowed_weekdays: list[int] | None = None
    # 工程終了直後に許容する最大連休日数（拠点休日と担当作業者の休みを含む）。Noneは制限なし。
    max_holidays_after: int | None = None
    # タスク個別の完了期限（拡張稼働日インデックス）。
    deadline_day_idx: int | None = None
    lock: DayLock | None = None
    hint: DayLock | None = None


@dataclass
class DayDependency:
    """同一オーダー内の隣接工程の順序と稼働日間隔制約。"""

    pred: int
    succ: int
    # 前工程の終了稼働日から次工程の開始稼働日までの最小・最大稼働日間隔。
    min_lag_days: int = 0
    max_lag_days: int | None = None


@dataclass
class DayProblem:
    """日次バケット計算・検証・手動編集で共用する問題定義。"""

    horizon_start: datetime
    horizon_end: datetime
    tz: str
    # 計画期間内の稼働日一覧（インデックス 0 .. num_days-1）。
    working_days: list[date]
    # 計画期間の前後バッファを含む拡張稼働日（日付→拡張インデックス。計画初日の稼働日が0）。
    date_to_ext_idx: dict[date, int]
    ext_idx_to_date: dict[int, date]
    workers: dict[int, DayWorker]
    orders: dict[int, DayOrder]
    tasks: dict[int, DayTask]
    dependencies: list[DayDependency] = field(default_factory=list)
    weights: dict[str, int] = field(default_factory=dict)
    # 後続バッファの最終日。作業者の出勤日が後続バッファ内に存在しない場合の連続休業日数算出に使う。
    buffer_end_date: date | None = None

    @property
    def num_days(self) -> int:
        return len(self.working_days)

    # 指定作業者が終了稼働日 end_day に作業を終えた直後に続く連休日数を返す（算出不可時はNone）。
    def worker_holidays_after(self, worker_id: int, end_day: int) -> int | None:
        worker = self.workers.get(worker_id)
        end_date = self.ext_idx_to_date.get(end_day)
        if worker is None or end_date is None or not worker.available_dates:
            return None
        # end_date より後で最初に出勤可能な日を探し、間の暦休日数を求める。
        idx = bisect_right(worker.available_dates, end_date)
        if idx < len(worker.available_dates):
            return max(0, (worker.available_dates[idx] - end_date).days - 1)
        # 後続バッファ末尾まで出勤日がない場合は、バッファ末尾まで連続休業とみなす。
        if self.buffer_end_date is not None and self.buffer_end_date > end_date:
            return (self.buffer_end_date - end_date).days
        return None

    # 稼働日インデックスからDB保存用の開始日時（当日 00:00:00）を返す。
    def day_to_start_dt(self, day_idx: int) -> datetime:
        d = self.ext_idx_to_date[day_idx]
        return datetime.combine(d, time(0, 0))

    # 終了稼働日インデックス（閉区間）からDB保存用の終了日時（翌日 00:00:00）を返す。
    def day_to_end_dt(self, end_day_idx: int) -> datetime:
        d = self.ext_idx_to_date[end_day_idx] + timedelta(days=1)
        return datetime.combine(d, time(0, 0))

    # DBの開始日時を稼働日インデックスへ変換する。非稼働日の場合はNoneを返す。
    def dt_to_day_idx(self, dt: datetime) -> int | None:
        return self.date_to_ext_idx.get(dt.date())

    # DBの終了日時（翌日00:00など半開区間）を終了稼働日インデックス（閉区間）へ変換する。
    def end_dt_to_day_idx(self, dt: datetime) -> int | None:
        # 00:00:00ちょうどは前日の終了を表すため1秒戻して日付を求める。
        end_date = (dt - timedelta(seconds=1)).date() if dt.time() == time(0, 0) else dt.date()
        return self.date_to_ext_idx.get(end_date)

    # 指定した稼働日インデックスを 'MM/DD' 形式で返す。
    def fmt_day(self, day_idx: int) -> str:
        d = self.ext_idx_to_date.get(day_idx)
        return d.strftime("%m/%d") if d else f"稼働日#{day_idx}"
