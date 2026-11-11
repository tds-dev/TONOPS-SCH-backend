<!-- 作業者4マスタの列構成、全工程リンク生成、仮データ、実装範囲を定義する資料。 -->
# 作業者マスタの追加（2026-11-11）

作業者本人・担当工程・週次勤務・不在日時の4テーブルを追加する。全27テーブル・313カラム。
追加部分はJSONを使わず、数値・文字列・時刻・日時の通常列で保存する。
今回のプログラム変更はモデル登録・Python仮データ・既存の工程追加に連動した担当リンク生成までとする。
作業者画面・4表のCRUD API・作業者制約の計画計算への反映は今回の対象に含めない。既存の設備計算は継続する。

## 追加する表と列

| テーブル | 列数 | 保存する列 |
|---|---:|---|
| M_Workers | 5 | WorkerID、LocationID、WorkerName、Remarks、DeleteFlag |
| M_WorkerProcessesLink | 6 | WorkerProcessLinkID、WorkerID、ProductProcessID、CanExecute、MaxDailyQuantity、Remarks |
| M_WorkerCalendars | 11 | WorkerCalendarsID、WorkerID、DayOfWeek、StartTime、EndTime、WorkName、CreatedAt、CreatedBy、UpdatedAt、UpdatedBy、DeleteFlag |
| M_WorkerCalendarExceptions | 9 | ExceptionID、WorkerCalendarsID、StartAt、EndAt、Remark、CreatedAt、CreatedBy、UpdatedAt、UpdatedBy |

テーブル名M_WorkerProcessesLink、列名WorkerCalendarsID、例外の単数形Remarkはユーザー指定を維持する。
WokerIDは、参照先と同じWorkerIDへ表記を修正する。
WorkerID等の主キーはINT・自動採番。WorkerNameはNVARCHAR(100)、WorkNameはNVARCHAR(50)、Remarks・RemarkはNVARCHAR(500)。
作業者本人と工程リンクには指定されていない監査列を追加しない。監査4列は勤務・不在だけに持たせる。

## 制約と関連付け

- WorkerID＋ProductProcessIDを一意にし、同じ担当関係の重複登録を防ぐ。
- CanExecuteのアプリ初期値は0。未登録・担当不可は、将来の計算で担当候補から除外する前提。
- MaxDailyQuantityはNUMERIC(18,3)、NULL可。NULLは追加上限なし、指定値は正数とする。現在の計画計算にはまだ適用しない。
- 作業者のLocationIDは既存M_Locationsを参照する。
- 工程リンクはM_Workersと製品別のM_ProductProcessesを参照する。
- 未使用の製品工程を削除すると、対応する作業者工程リンクも連動削除する。既存タスクがある工程の削除保護は継続する。
- 勤務はM_Workersを参照し、例外はM_WorkerCalendars.WorkerCalendarsIDを参照する。
- 勤務を物理削除した場合はその勤務行の例外を連動削除する。作業者CRUDは未実装のため、削除APIは追加しない。

DayOfWeekは既存と同じ日曜0～土曜6。勤務のStartTime・EndTimeはTIMEで、EndTime > StartTimeの同日勤務だけを許可する。
不在のStartAt・EndAtは日本時間のDATETIME2(7)で、EndAt > StartAtとする。複数日にまたがる不在も保存できる。
将来計算へ接続するときは、勤務行を経由して作業者を特定し、その作業者の勤務全体から不在を差し引く方針とする。現段階では不在の保存まで。

## 全工程分のリンク生成

画面で製品工程を新規追加した場合、既存の工程保存処理からadd_worker_process_linksを呼ぶ。
その工程と同じ拠点に属する未削除作業者を抽出し、まだ存在しない組合せだけをCanExecute=0、MaxDailyQuantity=NULLで追加する。
既存の担当可否・数量上限・備考を上書きしない。工程の名称変更・並べ替えではリンクを作り直さない。
処理は工程の保存と同じトランザクションに含め、途中で失敗した場合は工程とリンクの両方を取り消す。

作業者の新規登録APIはまだ作成しないため、SQLで作業者を直接追加するときは、同じ拠点の全工程とのリンクも登録する。
Python仮データは、既存の工程追加時と同じリンク生成処理を再利用する。

## 仮データ

| 内容 | 件数・設定 |
|---|---|
| 作業者 | 3人。こねる担当・焼く担当・包装担当 |
| 作業者工程リンク | 3人×18工程＝54件。担当可18件・担当不可36件 |
| 工程別日上限 | こねる600、焼く600、包装1200。担当不可の行はNULL |
| 作業者勤務 | 3人×月～土×午前午後＝36件。06:00～12:00、13:00～18:00 |
| 不在 | 作業者Aの10:00～11:00の研修1件 |

SQLの不在日は既存デモに合わせた2026-10-31、Pythonはデモ開始日に合わせる。
既存の製品6件・製品工程18件・工程候補18件・設備6件・オーダー7件・タスク21件・下書き計画2件は維持する。
手動SQLとPythonの初期設定で、同じ表・列・担当関係・件数を登録する。

## 作成手順と既存機能への影響

SSMSではcreate_database_sqlserver.sql → schema_sqlserver.sql → seed_demo_sqlserver.sqlの順で実行する。
Pythonではバックエンドのルートでpython -m DataBase.setup_databaseを実行する。どちらか一方を使う。
Pythonの初期設定はデモ拠点が登録済みの場合にデータ追加をスキップする既存動作を維持する。既存デモへの作業者仮データの後付けは行わない。
新規DB向けの更新であり、実DBへの接続・作成・データ登録は今回実行しない。

既存の画面、CRUD API、設備の自動計算・計画複製・比較・承認は維持する。
変更される既存動作は、製品工程の新規登録時に担当不可の作業者リンクも保存する点。
確認する操作は、既存の製品工程画面で新規工程を追加し、同拠点の全有効作業者分のリンクが1件ずつ作られること、工程更新・並べ替えで担当設定が維持されること。
作業者自身を編集する画面はまだ追加しない。

## 変更ファイル

```text
バックエンド:
DataBase/query/schema_sqlserver.sql
DataBase/query/seed_demo_sqlserver.sql
DataBase/setup_database.py
app/models/masters.py
app/models/__init__.py
app/services/worker_process_service.py（新規）
app/services/product_process_service.py
app/services/demo_seed.py
tests/test_order_crud.py
README.md
docs/SYSTEM_OVERVIEW.md
docs/DB_SCHEMA_UPDATE_20261111.md
docs/WORKER_MASTERS.md（新規）

フロントエンド:
README.md
docs/Book1.xlsx
```


## 実施した確認

- Python変更7ファイルをpython -m py_compileで構文確認。
- DB接続を持たないBaseで実際のモデルを読み込み、SQL Server対応版のDDLを文字列として生成。全27表313列の列名・列順・型・NULL可否、新規4表の制約名が保存済みSQLと一致。
- ExcelとSQLも全27表313列の列名・列順・型・NULL可否が一致。追加箇所以外の既存セル・書式・行列寸法・表示倍率を維持し、印刷範囲だけ拡張。
- 仮データSQLの233件のINSERTで列と値の対応を確認。既存139件のINSERTは変更前と一致。
- 作業者3人・リンク54件（可18/不可36）・勤務36件・不在1件の件数、全組合せ、参照先、同一拠点、日上限、同日勤務、不在の日時順を確認。
- 実際のリンク生成関数をDB接続のない保存先で確認。同拠点・未削除だけを対象にし、既存値を保持、不足だけ追加、再実行で重複しないことを確認。
- 既存の工程API用テストへ、担当リンクの追加・保持・工程削除との連動を確認するケースを追加。DBを使うAPIテスト自体は今回は実行していない。
- 実DB接続・SQL実行・DB作成・仮データ投入・ブラウザー操作・ビルド・解析コマンド・Git操作・外部通信は行っていない。
