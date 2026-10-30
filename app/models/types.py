"""モデルで使う列型。SQL Server では日本語を扱えるよう NVARCHAR、日時は DATETIME2 にする。

SQLite接続では通常の VARCHAR / TEXT / DATETIME として動作する。
"""
from sqlalchemy import DateTime as _DateTime
from sqlalchemy import Unicode, UnicodeText
from sqlalchemy.dialects import mssql

String = Unicode  # SQL Server: NVARCHAR(n)
Text = UnicodeText  # SQL Server: NVARCHAR(max)
DateTime = _DateTime().with_variant(mssql.DATETIME2(), "mssql")  # SQL Server: DATETIME2（UTC、naive）

__all__ = ["DateTime", "String", "Text"]
