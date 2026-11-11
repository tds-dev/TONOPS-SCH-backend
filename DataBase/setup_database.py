r"""
--------------------------------------------------------------------------------------------------------------

DB新規作成・テーブル作成・デモデータ登録実行方法

1.ルートフォルダに移行。
Set-Location -LiteralPath 'C:\Users\taisei_fujita\Desktop\TONOPS-SCH-backend\TONOPS-SCH-backend'

2.初期設定スクリプトを実行。
python -m DataBase.setup_database

--------------------------------------------------------------------------------------------------------------
DataBase配下のDB・テーブル作成とデモデータ登録を行う初期設定用プログラム。
製品・工程・実行候補をM_Product・M_ProductProcesses・M_ProductProcessResourcesへ登録する。
工程ルートの選択・版管理は行わず、工程はProductIDで製品に直接紐づける。
製品コード・単位・製品と工程の属性は持たず、分類属性はオーダーに登録する。

バックエンドのルートで python -m DataBase.setup_database を実行する。
query配下のSQLはSSMS用として保持し、この処理ではモデルから直接DBを操作する。
拠点はLocationモデルを使い、M_LocationsとLocationID等の定義で作成・登録する。
計算実行の保存先は、SolverRunモデルのT_SolverRunResultとして作成する。
デモはパン6製品、製品工程18件、実行候補18件、店舗向けオーダー7件、タスク21件、下書き計画2件を登録する。
計画名は「各店舗向けパン製造・通常計画」「各店舗向けパン製造・見直し計画」とする。
新規テーブルには、同じ拠点内で計画名を重複させない現在のモデル定義を適用する。
デモ組織が登録済みの場合は、以前の内容も含めて既存データを保持する。
"""
import argparse

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from app import models  # noqa: F401  全テーブルの定義を登録する。
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.models.masters import Organization
from app.services.demo_seed import DEMO_ORGANIZATION_NAME, seed_demo


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
    """新しい3階層のDB・テーブル作成と、未登録デモデータの追加を順に行う。"""
    ensure_database()
    # 現在のモデルで未作成テーブルを追加する。既存DBの列削除・名称変更は行わないため、構成変更後は新規DBを使う。
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        # 共通のデモ組織名で登録済みを確認し、初期設定の再実行による重複を防ぐ。
        demo_id = db.scalar(select(Organization.OrganizationID).where(Organization.OrganizationName == DEMO_ORGANIZATION_NAME))
        if demo_id is None:
            # 初期データの登録件数を受け取り、下書き計画も作成されたことを通知する。
            result = seed_demo(db)
            print(f"パン工場の仮データを登録しました（オーダー{result['orders']}件・下書き計画{result['plans']}件）。")
        else:
            # 登録済みの内容を保持したことを明示し、新しいデモへ更新されたとの誤解を避ける。
            print("デモデータは登録済みのため、追加・変更を行いませんでした。")


def main() -> None:
    """コマンドから初期設定を実行し、完了メッセージだけを表示する。"""
    # 未定義のオプションで誤って実行しないよう、引数を確認する。
    parser = argparse.ArgumentParser(prog="python -m DataBase.setup_database", description=__doc__)
    parser.parse_args()
    setup_database()
    print("DB・テーブル・デモデータを作成しました。")


if __name__ == "__main__":
    main()
