"""SQL Server にデータベース（既定: TONOPS-SCH）がなければ作成する。

    python -m scripts.create_database

DATABASE_URL のデータベース名を使い、master に接続して CREATE DATABASE を実行する。
create_schema / seed_demo からも自動で呼ばれる。SQLite の場合は何もしない。
"""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

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
        try:
            conn = master.connect()
        except DBAPIError as exc:
            raise SystemExit(_connect_help(u, exc)) from None
        with conn:
            if conn.execute(text("SELECT DB_ID(:n)"), {"n": name}).scalar() is None:
                conn.execute(text(f"CREATE DATABASE [{name}]"))
                print(f"データベース [{name}] を作成しました")
            else:
                print(f"データベース [{name}] は作成済みです")
    finally:
        master.dispose()


def _connect_help(u, exc: DBAPIError) -> str:
    """接続エラーを、原因の目安と直し方つきのメッセージにする。"""
    msg = str(exc.orig)
    lines = [f"SQL Server（{u.host}）に接続できません: {msg}", ""]
    if "IM002" in msg:  # ドライバーが見つからない
        try:
            import pyodbc

            found = [d for d in pyodbc.drivers() if "SQL Server" in d]
        except Exception:  # noqa: BLE001
            found = []
        lines.append(f"DATABASE_URL のドライバー「{u.query.get('driver')}」がインストールされていません。")
        lines.append("インストール済み: " + (", ".join(found) if found else "（なし）"))
        lines.append(".env の DATABASE_URL の driver= を上のいずれかに変更してください（空白は + に置き換え）。")
    else:
        lines.append("サーバー名・インスタンス名（例: localhost\\SQLEXPRESS）、SQL Server サービスの起動、権限を確認してください。")
    return "\n".join(lines)


if __name__ == "__main__":
    ensure_database()
