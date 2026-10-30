r"""
--------------------------------------------------------------------------------------------------------------

DB新規作成・テーブル作成・デモデータ登録実行方法

1.ルートフォルダに移行。
Set-Location -LiteralPath 'C:\Users\taisei_fujita\Desktop\TONOPS-SCH-backend\TONOPS-SCH-backend'

2.初期設定スクリプトを実行。
python -m DataBase.setup_database

--------------------------------------------------------------------------------------------------------------
DataBase配下のDB・テーブル作成とデモデータ登録を行う初期設定用プログラム。

バックエンドのルートで python -m DataBase.setup_database を実行する。
query配下のSQLはSSMS用として保持し、この処理ではモデルから直接DBを操作する。
拠点はLocationモデルを使い、M_LocationsとLocationID等の定義で作成・登録する。
計算実行の保存先は、SolverRunモデルのT_SolverRunResultとして作成する。
"""
import argparse

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from app import models  # noqa: F401  全テーブルの定義を登録する。
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.models.masters import Organization
from app.services.demo_seed import seed_demo


def ensure_database() -> None:
    """設定されたSQL ServerのDBが存在しない場合だけ作成する。"""
    # アプリ本体と同じ接続設定を使い、別のDBを作らないようにする。
    url = make_url(get_settings().database_url)
    if not url.drivername.startswith("mssql"):
        return
    # DB名をSQLの識別子として扱えるか確認する。
    name = url.database
    if not name or "]" in name:
        raise SystemExit(f"DATABASE_URL のデータベース名が不正: {name!r}")
    # 対象DBを作る前に、管理用のmasterへ接続する。
    master = create_engine(url.set(database="master"), isolation_level="AUTOCOMMIT")
    try:
        try:
            connection = master.connect()
        except DBAPIError as exc:
            raise SystemExit(connection_help(url, exc)) from None
        with connection:
            if connection.execute(text("SELECT DB_ID(:name)"), {"name": name}).scalar() is None:
                connection.execute(text(f"CREATE DATABASE [{name}]"))
    finally:
        master.dispose()


def connection_help(url: URL, exc: DBAPIError) -> str:
    """SQL Serverへの接続失敗時に、原因と設定の確認箇所を案内する。"""
    # DBドライバーが返したエラーを判別し、操作する人向けの説明を組み立てる。
    message = str(exc.orig)
    lines = [f"SQL Server（{url.host}）に接続できません: {message}", ""]
    if "IM002" in message:
        try:
            import pyodbc

            # インストール済みのSQL Server用ドライバー名を取得する。
            drivers = [driver for driver in pyodbc.drivers() if "SQL Server" in driver]
        except Exception:  # noqa: BLE001  診断情報を取得できなくても元のエラーを案内する。
            drivers = []
        lines.append(f"DATABASE_URL のドライバー「{url.query.get('driver')}」が見つかりません。")
        lines.append("インストール済み: " + (", ".join(drivers) if drivers else "（なし）"))
        lines.append("接続設定のdriver=を、インストール済みの名前に変更してください。空白は+に置き換えます。")
    else:
        lines.append("サーバー名、SQL Serverサービスの起動状態、接続権限を確認してください。")
    return "\n".join(lines)


def setup_database() -> None:
    """DB作成、Location形式の未作成テーブル追加、未登録デモデータ追加を順に行う。"""
    ensure_database()
    # M_Locations・T_SolverRunResult等の現在のモデル定義を使い、既存のテーブルとデータは保持する。
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        # 既存の登録済み判定を維持し、デモ組織があれば重複登録しない。
        demo_id = db.scalar(select(Organization.OrganizationID).where(Organization.OrganizationCode == "DEMO"))
        if demo_id is None:
            seed_demo(db)


def main() -> None:
    """コマンドから初期設定を実行し、完了メッセージだけを表示する。"""
    # 未定義のオプションで誤って実行しないよう、引数を確認する。
    parser = argparse.ArgumentParser(prog="python -m DataBase.setup_database", description=__doc__)
    parser.parse_args()
    setup_database()
    print("DB・テーブル・デモデータの準備が完了しました。")


if __name__ == "__main__":
    main()
