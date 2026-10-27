"""SQL Server にデータベース（既定: TONOPS-SCH）がなければ作成する。

    python -m scripts.create_database

DATABASE_URL のデータベース名を使い、master に接続して CREATE DATABASE を実行する。
create_schema / seed_demo からも自動で呼ばれる。SQLite の場合は何もしない。
"""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def ensure_database(url: str | None = None) -> None:
    u = make_url(url or get_settings().database_url)
    if not u.drivername.startswith("mssql"):
        return
    name = u.database
    if not name or "]" in name:
        raise SystemExit(f"DATABASE_URL のデータベース名が不正です: {name!r}")
    master = create_engine(u.set(database="master"), isolation_level="AUTOCOMMIT")
    try:
        with master.connect() as conn:
            if conn.execute(text("SELECT DB_ID(:n)"), {"n": name}).scalar() is None:
                conn.execute(text(f"CREATE DATABASE [{name}]"))
                print(f"データベース [{name}] を作成しました")
            else:
                print(f"データベース [{name}] は作成済みです")
    finally:
        master.dispose()


if __name__ == "__main__":
    ensure_database()
