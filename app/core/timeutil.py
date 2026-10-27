"""時刻ユーティリティ。DB の日時はすべて naive な UTC（datetime2(0)）で保存する。"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """現在時刻を naive な UTC で返す（秒未満は切り捨て）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def to_utc_naive(dt: datetime, tz: str | None = None) -> datetime:
    """aware な日時（または `tz` の naive な日時）を naive な UTC に変換する。"""
    if dt.tzinfo is None:
        if tz is None:
            return dt  # 規約により既に naive な UTC
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(dt: datetime, tz: str) -> datetime:
    """naive な UTC を `tz` の aware なローカル時刻に変換する。"""
    return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
