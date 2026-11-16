<!-- 作業者4マスタの列構成、全工程リンク生成、仮データ、実装範囲を定義する資料。 -->
# 作業者マスタ（通常稼働時間・例外休日・スキルマップ対応）

作業者本人・担当工程・週次勤務・不在日時の既存4テーブルを使用する。
追加部分はJSONを使わず、数値・文字列・時刻・日時の通常列で保存する。
2026-11-16：本人の基本情報に加え、曜日別通常稼働時間・例外休日・スキルマップの設定画面とAPIを追加した。
現行の操作・入力確認・保持する動作は[作業者の設定画面仕様](WORKER_SETTINGS_20261116.md)を参照する。
作業者制約の計画計算への反映は未実装。既存の設備計算は継続する。

## 追加する表と列

| テーブル | 列数 | 保存する列 |
|---|---:|---|
| M_Workers | 5 | WorkerID、LocationID、WorkerName、Remarks、DeleteFlag |
| M_WorkerSkillMap | 6 | WorkerSkillMapID、WorkerID、ProductProcessID、CanExecute、MaxDailyQuantity、Remarks |
| M_WorkerCalendars | 11 | WorkerCalendarsID、WorkerID、DayOfWeek、StartTime、EndTime、WorkName、CreatedAt、CreatedBy、UpdatedAt、UpdatedBy、DeleteFlag |
| M_WorkerCalendarExceptions | 9 | ExceptionID、WorkerID、StartAt、EndAt、Remark、CreatedAt、CreatedBy、UpdatedAt、UpdatedBy |

テーブル名M_WorkerSkillMap、通常勤務の主キーWorkerCalendarsID、例外の単数形Remarkは維持する。例外休日の参照列はWorkerIDへ変更した。
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
- 通常勤務と例外休日は、どちらもWorkerIDでM_Workersを直接参照する。
- 勤務を削除しても例外休日は変更・削除しない。作業者の削除APIは本人のDeleteFlagだけを更新し、担当工程・勤務・不在の既存行を保持する。

DayOfWeekは既存と同じ日曜0～土曜6。勤務のStartTime・EndTimeはTIMEで、EndTime > StartTimeの同日勤務だけを許可する。
不在のStartAt・EndAtは日本時間のDATETIME2(7)で、EndAt > StartAtとする。複数日にまたがる不在も保存できる。
週表示ではWorkerIDから本人の通常勤務と例外休日を直接取得し、稼働時間から休日を差し引く。作業者設定の計画計算への反映は未実装。

## 全工程分のリンク生成

画面で製品工程を新規追加した場合、既存の工程保存処理からadd_worker_skill_mapsを呼ぶ。
その工程と同じ拠点に属する未削除作業者を抽出し、まだ存在しない組合せだけをCanExecute=0、MaxDailyQuantity=NULLで追加する。
既存の担当可否・数量上限・備考を上書きしない。工程の名称変更・並べ替えではリンクを作り直さない。
処理は工程の保存と同じトランザクションに含め、途中で失敗した場合は工程とリンクの両方を取り消す。

作業者の新規登録APIではadd_process_skill_mapsを呼び、同じ拠点の有効な製品に属する全工程との担当不可リンクを作る。
工程追加と作業者追加は、不足する組合せだけを作る共通処理を使い、既存の担当可否・日上限・備考を上書きしない。
SQLで作業者を直接追加するときは、従来どおり同じ拠点の全工程とのリンクも登録する。
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
作業者自身の名前・備考は、サイドバーの「マスタ」→「作業者」から編集する。

## 初回テーブル追加時の変更ファイル

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
README.md
docs/SYSTEM_OVERVIEW.md
docs/DB_SCHEMA_UPDATE_20261111.md
docs/WORKER_MASTERS.md（新規）

フロントエンド:
README.md
docs/Book1.xlsx
```


## 初回テーブル追加時の確認記録

- Python変更7ファイルをpython -m py_compileで構文確認。
- DB接続を持たないBaseで実際のモデルを読み込み、SQL Server対応版のDDLを文字列として生成。全27表313列の列名・列順・型・NULL可否、新規4表の制約名が保存済みSQLと一致。
- ExcelとSQLも全27表313列の列名・列順・型・NULL可否が一致。追加箇所以外の既存セル・書式・行列寸法・表示倍率を維持し、印刷範囲だけ拡張。
- 仮データSQLの233件のINSERTで列と値の対応を確認。既存139件のINSERTは変更前と一致。
- 作業者3人・リンク54件（可18/不可36）・勤務36件・不在1件の件数、全組合せ、参照先、同一拠点、日上限、同日勤務、不在の日時順を確認。
- 実際のリンク生成関数をDB接続のない保存先で確認。同拠点・未削除だけを対象にし、既存値を保持、不足だけ追加、再実行で重複しないことを確認。
- 実DB接続・SQL実行・DB作成・仮データ投入・ブラウザー操作・ビルド・解析コマンド・Git操作・外部通信は行っていない。

## 基本情報画面だけを追加した時点の記録（2026-11-16）

この節は基本情報画面を追加した時点の記録。通常稼働時間・例外休日・スキルマップの現在の仕様は[設定画面仕様](WORKER_SETTINGS_20261116.md)を参照する。

変更前は、作業者のテーブルと仮データ、工程追加時の担当リンク生成だけがあり、作業者を画面から保存する経路がなかった。
変更後は、サイドバーの「マスタ」→「作業者」（`/workers`）で、選択中の拠点の作業者を管理できる。

### 画面の仕様

- 他のマスタと同じ`PageHeaderComponent`と`MasterEditorComponent`を使用する。
- 作業者名は必須・100文字以内、備考は任意・500文字以内とする。
- 一覧・検索・再読込・新規登録・行内編集・削除確認・未保存での画面移動確認を共用する。
- 行をクリックすると編集欄を開き、同じ行を再度クリックすると閉じる。
- 拠点を変更した際は、その拠点の作業者一覧を取得し直す。
- 新しいCSSや外部ライブラリは追加せず、共通の表・入力欄・ボタン・エラー表示を使う。

### APIと保存の仕様

| 操作 | API |
| --- | --- |
| 拠点別一覧 | GET /api/v1/workers?locationId={locationId} |
| 1件取得 | GET /api/v1/workers/{workerId} |
| 登録 | POST /api/v1/workers |
| 部分更新 | PATCH /api/v1/workers/{workerId} |
| 論理削除 | DELETE /api/v1/workers/{workerId} |

登録項目は`locationId`・`workerName`・`remarks`。名前・備考の前後の空白を除き、空の備考はNULLとする。
作業者名の必須・文字数、備考の文字数、有効な拠点、登録後の拠点移動禁止をサーバー側でも確認する。
登録・編集用の入力から削除状態を変更することは許可せず、削除はDELETEの操作で行う。

共通CRUDの専用保存・削除の仕組みを使用し、既存のM_Workersの5列を維持する。
作業者テーブルには登録者・更新者などの監査列がないため、作業者用の保存処理ではそれらを渡さない。
DB定義、DB作成クエリ、仮データ挿入クエリ、Excelの変更は不要。

新規作業者は、同じ拠点の有効な製品に属する全工程との担当関係をCanExecute=Falseで作成する。
本人情報と担当関係は同じ保存単位で確定する。工程未登録の拠点では本人だけを登録でき、後から工程を追加すると担当関係が生成される。
既存の工程追加時の処理と、重複確認・初期値・保存処理を共通化し、既存の担当可否・日上限・備考を上書きしない。
削除はDeleteFlagだけを更新する論理削除とし、担当工程・個別勤務・不在の関連行は保持する。

担当工程・個別勤務・不在の編集画面/APIと、作業者による計画計算の制約は今回追加していない。
既存の製品・工程、拠点カレンダー、リソース、計画計算の仕様は維持する。

### 今回の変更ファイル

| 対象 | ファイル | 内容 |
| --- | --- | --- |
| フロントエンド | `src/app/components/main/workers/workers.component.ts` | 作業者画面を新規作成 |
| フロントエンド | `src/app/app.routes.ts` | 画面URLと未保存確認を追加 |
| フロントエンド | `src/app/app.component.ts` | サイドバーのマスタへ作業者を追加 |
| フロントエンド | `src/app/components/common/icons/material-icon.component.ts` | 作業者の人物アイコンを追加 |
| フロントエンド | `src/app/interfaces/master-editor.interface.ts` | 共通マスタAPIの型へworkersを追加 |
| フロントエンド | `src/app/services/page-hints.ts` | 作業者メニューの説明を追加 |
| フロントエンド | `src/app/services/master-reference.service.ts` | 拠点カレンダー削除の古い説明コメントを現行仕様へ修正 |
| フロントエンド | `README.md` | 実装済みの作業者画面と今後の対象を記載 |
| バックエンド | `app/routers/masters.py` | 作業者CRUD APIを追加 |
| バックエンド | `app/services/worker_service.py` | 本人情報の保存・検証・論理削除を新規作成 |
| バックエンド | `app/services/worker_process_service.py` | 作業者追加に対応し、担当リンク作成を共通化 |
| バックエンド | `README.md` | 実装済みの作業者APIを記載 |
| バックエンド | `docs/SYSTEM_OVERVIEW.md` | 画面・APIと実装範囲を更新 |
| バックエンド | `docs/WORKER_MASTERS.md` | 今回の仕様・変更内容・確認結果を記録 |

### 確認結果と画面での確認点

- 登録・取得・部分更新・拠点別一覧・論理削除、誤入力時の保存取消しを確認。
- 担当関係の作成範囲・既存設定の保持・再実行時の重複防止、作業者削除後の勤務・不在保持を確認。
- ブラウザ操作・ビルド・解析コマンド・Git操作・実DB変更は未実施。

画面では、メニューから開けること、選択拠点の作業者だけが表示されること、検索・登録・行内編集・削除が使えることを確認する。
入力途中で画面を移動する場合の確認と、保存失敗時に入力内容が保持されることも確認する。
