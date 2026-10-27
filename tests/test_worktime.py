"""稼働時間の展開（純粋関数）。"""
from datetime import datetime, time

from app.services.worktime import ExceptionSpec, PatternSpec, expand_working_time, merge, subtract

TZ = "Asia/Tokyo"  # UTC+9、夏時間なし


def test_two_shifts_on_a_weekday():
    # 2026-10-27（火）06:00–12:00 と 13:00–22:00 JST
    patterns = [PatternSpec(2, time(6), time(12)), PatternSpec(2, time(13), time(22))]
    start = datetime(2026, 10, 26, 15, 0)  # 火 00:00 JST
    end = datetime(2026, 10, 27, 15, 0)  # 水 00:00 JST
    got = expand_working_time(patterns, [], start, end, TZ)
    assert got == [
        (datetime(2026, 10, 26, 21, 0), datetime(2026, 10, 27, 3, 0)),
        (datetime(2026, 10, 27, 4, 0), datetime(2026, 10, 27, 13, 0)),
    ]


def test_night_shift_crosses_midnight():
    patterns = [PatternSpec(1, time(22), time(6))]  # 月 22:00 -> 火 06:00
    start = datetime(2026, 10, 25, 15, 0)  # 月 00:00 JST
    end = datetime(2026, 10, 27, 15, 0)
    got = expand_working_time(patterns, [], start, end, TZ)
    assert got == [(datetime(2026, 10, 26, 13, 0), datetime(2026, 10, 26, 21, 0))]


def test_holiday_and_overtime_exceptions():
    patterns = [PatternSpec(2, time(6), time(22))]
    start = datetime(2026, 10, 26, 15, 0)
    end = datetime(2026, 10, 27, 15, 0)
    exceptions = [
        ExceptionSpec(datetime(2026, 10, 27, 1, 0), datetime(2026, 10, 27, 2, 0), False),  # 10–11 停止
        ExceptionSpec(datetime(2026, 10, 27, 13, 0), datetime(2026, 10, 27, 14, 0), True),  # 22–23 残業
    ]
    got = expand_working_time(patterns, exceptions, start, end, TZ)
    assert got == [
        (datetime(2026, 10, 26, 21, 0), datetime(2026, 10, 27, 1, 0)),
        (datetime(2026, 10, 27, 2, 0), datetime(2026, 10, 27, 14, 0)),
    ]


def test_merge_and_subtract():
    a = datetime(2026, 1, 1, 0)
    h = lambda n: a.replace(hour=n)  # noqa: E731
    assert merge([(h(1), h(3)), (h(2), h(5)), (h(6), h(7))]) == [(h(1), h(5)), (h(6), h(7))]
    assert subtract([(h(1), h(9))], [(h(2), h(3)), (h(5), h(6))]) == [
        (h(1), h(2)), (h(3), h(5)), (h(6), h(9)),
    ]
