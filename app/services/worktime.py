"""稼働時間の計算（純粋関数、DB 非依存）。

`expand_working_time` は週次勤務（拠点の現地時間）と停止例外（日本時間）から、
重なりのない 日本時間の区間のソート済みリストを作る。スケジューリングエンジンでも使う。
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from app.core.timeutil import to_jst_naive, weekday_number

Interval = tuple[datetime, datetime]  # 時差情報なしの日本時間、[開始, 終了)


# DBの勤務1行から取り出した、曜日と現地時刻の組合せ。
@dataclass(frozen=True)
class WorkSpec:
    day_of_week: int  # 0 = 日 … 6 = 土
    start: time
    end: time


# 稼働時間から除外する休日・停止の日本時間の日時。
@dataclass(frozen=True)
class ExceptionSpec:
    start: datetime  # 時差情報なしの日本時間
    end: datetime  # 時差情報なしの日本時間


# 重なる勤務時間や連続した勤務時間をまとめる。
def merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for s, e in sorted(i for i in intervals if i[1] > i[0]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


# 勤務時間から休日・停止時間を差し引く。
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


# 確認・計画期間からはみ出す部分を切り取る。
def clip(intervals: list[Interval], start: datetime, end: datetime) -> list[Interval]:
    return [(max(s, start), min(e, end)) for s, e in intervals if e > start and s < end]


# 週次勤務を実際の日付へ展開し、停止例外と指定期間を反映する。
def expand_working_time(
    work_rows: list[WorkSpec],
    exceptions: list[ExceptionSpec],
    start: datetime,
    end: datetime,
    tz: str,
) -> list[Interval]:
    """`start` から `end` まで（時差情報なしの日本時間）の稼働区間（時差情報なしの日本時間）。"""
    # 確認期間の開始日から、同じ日付内の勤務だけを展開する。
    first_local = to_jst_naive(start).date()
    last_local = to_jst_naive(end).date()
    base: list[Interval] = []
    day = first_local
    while day <= last_local:
        for p in work_rows:
            if p.day_of_week != weekday_number(day):
                continue
            local_start = datetime.combine(day, p.start)
            local_end = datetime.combine(day, p.end)
            base.append((to_jst_naive(local_start), to_jst_naive(local_end)))
        day += timedelta(days=1)
    # 例外はすべて休日・停止として扱い、追加稼働には使わない。
    working = subtract(base, [(x.start, x.end) for x in exceptions])
    return clip(working, start, end)


def gaps(windows: list[tuple[int, int]], horizon: int) -> list[tuple[int, int]]:
    """稼働枠（分）の補集合 = 0..horizon の非稼働区間（分）。"""
    out, cursor = [], 0
    for s, e in sorted(windows):
        s, e = max(0, s), min(horizon, e)
        if s > cursor:
            out.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < horizon:
        out.append((cursor, horizon))
    return out
