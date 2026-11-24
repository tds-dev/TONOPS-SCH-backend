r"""
--------------------------------------------------------------------------------------------------------------

DB新規作成・テーブル作成・デモデータ登録実行方法

1.ルートフォルダに移動。
Set-Location -LiteralPath 'C:\Users\taisei_fujita\Desktop\TONOPS-SCH-backend\TONOPS-SCH-backend'

2.初期設定スクリプトを実行。
python -m DataBase.setup_database

--------------------------------------------------------------------------------------------------------------
DataBase配下のDB・テーブル作成とデモデータ登録を行う初期設定用プログラム。
製品・工程・実行候補をM_Product・M_ProductProcesses・M_ProductProcessResourcesへ登録する。
準備時間・固定時間・数量当たり時間はM_ProductProcessesへ登録し、実行候補には保持しない。
数量当たりの作業時間はProcessingMinutesとし、準備・固定時間はNULLを許可する。
工程ルートの選択・版管理は行わず、工程はProductIDで製品に直接紐づける。
製品は任意のProductCode（NVARCHAR(100)）を持つ。単位・製品と工程の属性は持たず、タスクにも属性を登録しない。
オーダーは種別・計画の管理元・属性の列を持たない。
オーダーの複数作業者指定はT_OrderWorkers（OrderWorkerID・OrderID・WorkerIDの3列）に保存し、計画計算への反映は行わない。
T_PlanAssignments.WorkerIDはNULL不可とし、仮データ登録時だけ工程に対応する作業者IDを設定する。
通常の計算・手動配置・計画コピーはWorkerIDを設定しないため、新しい割付の保存は後続実装まで未対応となる。

バックエンドのルートで python -m DataBase.setup_database を実行する。
テーブルはモデルから作成し、SQL Serverの仮データはquery/seed_demo_sqlserver.sqlを実行して登録する。
SQLファイル内のUSEは除き、アプリの接続設定で指定したDBへ登録する。
パン工場の全仮データに加え、センシングのマスタ仮データも登録する。
拠点はLocationモデルを使い、M_LocationsとLocationID等の定義で作成・登録する。
計算実行の保存先は、SolverRunモデルのT_SolverRunResultとして作成する。
タスクの設備候補・前後関係の複製テーブルは作らず、製品工程から利用時に組み立てる。
旧属性定義・ルールは作成せず、曜日制限は製品工程に保持する。
段取り替えは前後の製品工程IDを参照し、AttributeKey・FromValue・ToValueは作成しない。
デモはパン6製品、製品工程18件、実行候補18件、店舗向けオーダー7件、タスク21件、下書き計画2件を登録する。
計画名は「11月第3週_パン製造計画」「11月第3週_パン製造計画v2」とする。
両計画は2026-11-16 06:00～2026-11-21 06:00の5日間とし、比較撮影用の割付39件・評価値14件も登録する。
新規テーブルには、同じ拠点内で計画名を重複させない現在のモデル定義を適用する。
タスクは作業番号・集約指定・進捗率・属性の列を持たず、TaskIDで識別する。
SQL Serverでは拠点が1件でも登録済みの場合、仮データ登録をスキップして既存データを保持する。
既存DBへの不足データ追加やテーブル変更は行わず、全データの再登録にはDBを再作成する。
SQLite用の従来のパン工場データ登録はapp/services/demo_seed.pyを使用する。
勤務時間はM_Calendarsへ直接登録し、組織・カレンダーパターンは作成しない。
作業者3人・全工程リンク54件・勤務36件・例外休日1件も作成する。作業者の画面・APIは実装済みで、計算連携は行わない。
例外休日はWorkerIDで本人へ直接関連付け、通常稼働時間の登録・削除から独立させる。
2026-11-13: 全23テーブル・255列。担当工程はM_WorkerSkillMap・WorkerSkillMapIDで識別する。
設備は所属拠点の勤務を共有し、計画・停止例外・計算実行の開始終了列をStartAt・EndAtへ統一する。
2026-11-16: 拠点のCalendarIDを廃止し、週間勤務・停止予定はLocationIDで直接関連付ける。
開発用DBの構成を変更した場合は、DBを削除して現在の定義で再作成する。
計算時間上限は持たず、作業中の実績はEndAt・StatusともNULL、終了時はDONEまたはSUSPENDEDとする。
"""
import argparse
from pathlib import Path
import re

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from app import models  # noqa: F401  全テーブルの定義を登録する。
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.models.masters import Location
from app.services.demo_seed import DEMO_LOCATION_NAME, seed_demo


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


def seed_sqlserver() -> None:
    """手動登録と同じSQLから、パン工場とセンシングを含む全仮データを登録する。"""
    # 実行ディレクトリに依存せず、初期設定スクリプトと同じフォルダのSQLを読む。
    seed_path = Path(__file__).resolve().parent / "query" / "seed_demo_sqlserver.sql"
    script = seed_path.read_text(encoding="utf-8-sig")
    # USEによる別DBへの切替を除き、SSMS専用のGOも取り除いて一つのバッチとして実行する。
    script = re.sub(r"(?im)^[ \t]*USE[ \t]+\[TONOPS-SCH\];[ \t]*\r?$", "", script)
    script = re.sub(r"(?im)^[ \t]*GO[ \t]*\r?$", "", script)
    # 登録SQL自身がトランザクションを管理するため、ドライバー側の自動開始を無効にする。
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        if connection.scalar(select(Location.LocationID).limit(1)) is not None:
            print("既存データがあるため、仮データの追加・変更を行いませんでした。全件再登録にはDBを再作成してください。")
            return
        cursor = connection.connection.cursor()
        try:
            cursor.execute(script)
            # SQL Serverの全実行結果を読み進め、後半のINSERTやCOMMITのエラーも検出する。
            while cursor.nextset():
                pass
        finally:
            cursor.close()
    print("seed_demo_sqlserver.sqlの全仮データを登録しました（パン工場・センシング）。")


def setup_database() -> None:
    """DB・テーブルを作成し、SQL Serverでは共通SQLから全仮データを登録する。"""
    ensure_database()
    # 現在のモデル定義でテーブルを作成する。DB構成を変更した場合は、DBを削除してから実行する。
    Base.metadata.create_all(engine)
    if engine.dialect.name == "mssql":
        seed_sqlserver()
        return
    # SQLite接続では、従来のPythonデモ登録を維持する。
    with SessionLocal() as db:
        # 削除済みも含めてデモ拠点を確認し、再実行による重複を防ぐ。
        demo_id = db.scalar(select(Location.LocationID).where(Location.LocationName == DEMO_LOCATION_NAME))
        if demo_id is None:
            # 初期データの登録件数を受け取り、下書き計画も作成されたことを通知する。
            result = seed_demo(db)
            print(f"パン工場の仮データを登録しました（オーダー{result['orders']}件・下書き計画{result['plans']}件・"
                  f"作業者{result['workers']}人・工程リンク{result['workerSkillMaps']}件・"
                  f"作業者勤務{result['workerCalendars']}件・不在{result['workerCalendarExceptions']}件）。")
        else:
            # 登録済みの内容を保持したことを明示し、新しいデモへ更新されたとの誤解を避ける。
            print("デモデータは登録済みのため、追加・変更を行いませんでした。")


def main() -> None:
    """コマンドから初期設定を実行し、完了メッセージだけを表示する。"""
    # 未定義のオプションで誤って実行しないよう、引数を確認する。
    parser = argparse.ArgumentParser(prog="python -m DataBase.setup_database", description=__doc__)
    parser.parse_args()
    setup_database()
    print("DBの初期設定が完了しました。")


if __name__ == "__main__":
    main()
