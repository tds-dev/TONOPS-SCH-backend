"""日本時間の日時取得・保存値への正規化・API表現を共通化する処理。"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

# OSやDBサーバーの時差設定に依存しない日本時間。
JST = ZoneInfo("Asia/Tokyo")


# 日本時間の現在日時を、DB保存用に時差情報なしで返す。従来どおり秒単位とする。
def jst_now() -> datetime:
    return datetime.now(JST).replace(tzinfo=None, microsecond=0)


# 時差付き入力は日本時間へ揃え、時差なし入力は日本時間として保存する。
def to_jst_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(JST)
    return value.replace(tzinfo=None)


# DBの日本時間に+09:00を付ける。既に時差があれば日本時間へ揃える。
def as_jst(value: datetime) -> datetime:
    return to_jst_naive(value).replace(tzinfo=JST)


# Pythonの曜日番号を、DB・画面で共通の日曜0～土曜6へ変換する。
def weekday_number(value: date) -> int:
    return value.isoweekday() % 7
