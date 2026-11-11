"""モデルで使う列型。SQL Server では日本語を扱えるよう NVARCHAR、日時は DATETIME2 にする。

SQLite接続では通常の VARCHAR / TEXT / DATETIME として動作する。
"""
from sqlalchemy import DateTime as _DateTime
from sqlalchemy import Unicode, UnicodeText
from sqlalchemy.dialects import mssql

String = Unicode  # SQL Server: NVARCHAR(n)
Text = UnicodeText  # SQL Server: NVARCHAR(max)
# SQL Serverでは出荷日時を含めDATETIME2(7)を使い、日本時間で保存する。
DateTime = _DateTime().with_variant(mssql.DATETIME2(precision=7), "mssql")

__all__ = ["DateTime", "String", "Text"]
