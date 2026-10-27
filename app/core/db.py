"""データベースエンジン、セッションファクトリ、宣言的ベースクラス。

SQL Server（mssql+pyodbc、DB 名 TONOPS-SCH）で動作する。テストはインメモリの SQLite を使う。
SQL Server のマイグレーションが安定するよう、制約名は固定の命名規則に従う。
"""
from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "IX_%(table_name)s_%(column_0_N_name)s",
    "uq": "UQ_%(table_name)s_%(column_0_N_name)s",
    "ck": "CK_%(table_name)s_%(constraint_name)s",
    "fk": "FK_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "PK_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str, **kwargs) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False}, **kwargs)

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite は明示しないと外部キーを無視する
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    # fast_executemany で SQL Server への計画割付の一括登録を高速化
    if url.startswith("mssql+pyodbc"):
        kwargs.setdefault("fast_executemany", True)
    return create_engine(url, pool_pre_ping=True, **kwargs)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
