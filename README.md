<!-- アプリの構成、利用手順、APIとDBの対応を説明する資料。 -->

> 最新の日時仕様：DBは日本時間の`datetime2(7)`、通常APIは日本時間（`+09:00`）で入出力。ボードは描画用に時差表記なしの日本時間を使用する。DBは再作成して使用する。過去のUTCに関する記録は変更当時の仕様。詳細はバックエンドの`docs/DATETIME_JST.md`を参照。

> 現行構成（2026-11-11）：`M_Product` → `M_ProductProcesses` → `M_ProductProcessResources`。組織を削除し、曜日・時間帯を`M_Calendars`へ統合。拠点ごとの週次勤務を使い、終了時刻が開始時刻より後の同日勤務だけを登録する。例外は休日・設備停止として扱う。以下の日付付き記録は変更当時の仕様。

# TONOPS-SCH-backend

> 作業者4マスタを追加し、全27テーブル・313カラムへ更新。作業者3人・全工程リンク54件・勤務36件・不在1件を登録する。既存の工程新規追加時にも担当不可のリンクを生成する。作業者画面・CRUD API・計画計算への接続は今回追加しない。[仕様と作成手順](docs/WORKER_MASTERS.md)を参照。

> 2026-11-11：`M_Organizations`と関連`OrganizationID`、`M_CalendarPatterns`を削除。`M_Calendars`に曜日・勤務開始終了・勤務名を持たせ、拠点の`DefaultCalendarID`を`CalendarID`へ変更。カレンダー例外は`StartTime`・`EndTime`へ改名し、`IsWorking`を削除。共通監査列`UpdatedAt`・`UpdatedBy`は継続する。[変更内容とDB作成手順](docs/DB_SCHEMA_UPDATE_20261111.md)を参照。

> 2026-11-10：切替時間・切替ルール・計算設定・作業実績のテーブルと関連列を改名。各コード列・拠点TimeZone・計画番号・違反コードを廃止し、オーダーをWBSNumber・DeadLine・ShippingDate、計画の備考をRemarksへ変更。追加で設備の時間単価・属性、親オーダーID、親タスクID・節目指定・予定工数を廃止。作り直した空のDBを対象とする。[変更内容とDB作成手順](docs/DB_SCHEMA_UPDATE_20261110.md)を参照。

> 2026-10-30: 表示用語を、マスタは「工程」、オーダー・計画は「タスク」へ戻した。集計の表示名やエラーメッセージも同じ呼び方に揃え、Product系の名称・API項目・DB構造・計算条件は維持する。

> 2026-10-30: 製品モデル・列名・APIをProduct系へ統一。`M_Product.ProductID`・`ProductCode`・`ProductName`、`/products`、製品の属性区分 `PRODUCT` を使う。IDの数値と計算処理は維持する。実DBはテーブル・列・属性区分を手動で変更してから利用する。`DataBase/query` 内の製品に関係するSQL2ファイルも更新したが、実行していない。

> 2026-10-30: 計算実行の保存先を `T_SolverRunResult` へ変更。既存DBのテーブル名は手動で変更してから利用する。列・保存値と `/solver-runs` のAPIは維持する。`DataBase/query` 内の新規作成SQLも同じ名称へ更新済み。実DBへの変更は行っていない。

> 2026-10-30: 拠点のモデル・APIをLocation系へ統一。`/api/v1/locations` と `locationId` を使い、DBでは `M_Locations`・`LocationID`・`LocationCode`・`LocationName` を参照する。実DBと `DataBase/query` 内の保存済みSQLは今回変更していない。既存DBを手動で改称してから利用する。初期設定プログラムは既存テーブルの改称を行わない。

> 2026-10-30: プログラムとAPIはOrder/Ordersへ改称。DBもT_Orders・OrderID等へ変更される前提で動作する。実DBの変更は未実施のため、DB側の名称変更後に利用する。既存のSYSTEM_OVERVIEW.md等に記載されたJob名は変更前の構成を含む。現行APIは/api/v1/orders。


TONOPS-SCH（業種に依存しない生産・プロジェクト生産スケジューラ）のバックエンドです。
REST API（FastAPI）、スケジューリングエンジン（Google OR-Tools CP-SAT）、ソルバーワーカーを含みます。

* フロントエンド: [tds-dev/TONOPS-SCH-frontend](https://github.com/tds-dev/TONOPS-SCH-frontend)
* システム全体の説明（スケジューリングロジック、DB スキーマ、画面とテーブルの対応、API 一覧）:
  **[docs/SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md)**
* 開発の経緯（フェーズごとの内容）: [docs/PHASES.md](docs/PHASES.md)

---

## 1. 必要な環境

| ソフトウェア | バージョン | 備考 |
|---|---|---|
| Windows | 10 / 11 | Linux・macOS でも動作します（手順のコマンドを読み替えてください） |
| Python | 3.12 推奨（3.11 以上） | `py -3.12 --version` で確認 |
| SQL Server | 2017 以降（Express 可） | ローカルの既定インスタンスを想定 |
| ODBC Driver for SQL Server | 17（18 も可） | 他の社内システムと同じ 17 を既定にしています |
| Git | 任意 | |

> SQL Server に **Windows 認証** でログインでき、データベースを作成できる権限（sysadmin または dbcreator）が必要です。
> 権限がない場合は、DBA に空の `TONOPS-SCH` データベースを作ってもらえば、テーブル作成以降は db_owner 権限で動きます。

インストール済みの ODBC ドライバーは PowerShell で確認できます:

```powershell
Get-OdbcDriver | Where-Object Name -like "*SQL Server*" | Select-Object Name
```

---

## 2. インストール

### 2.1 ソースの取得

```bat
cd %USERPROFILE%\Documents
git clone https://github.com/tds-dev/TONOPS-SCH-backend.git
cd TONOPS-SCH-backend
```

### 2.2 Python 仮想環境と依存パッケージ

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

主なパッケージ: `fastapi`, `uvicorn`, `sqlalchemy`（2.x）, `pydantic`（2.x）, `pyodbc`, `ortools`, `tzdata`。

> フォルダーを移動・名前変更した場合、`.venv` は作り直してください（中に絶対パスが残るため）。

### 2.3 設定ファイル（.env）

```bat
copy .env.example .env
```

`.env` の主な項目:

| 項目 | 既定値 | 説明 |
|---|---|---|
| `DATABASE_URL` | `mssql+pyodbc://@localhost/TONOPS-SCH?driver=ODBC+Driver+17+for+SQL+Server` | 接続先。ユーザー名なし = Windows 認証 |
| `CORS_ORIGINS` | `http://localhost:4200` | API を呼び出せるオリジン（カンマ区切り） |
| `WORKER_POLL_SECONDS` | `2` | ワーカーが計算依頼を確認する間隔（秒） |

接続先の例（`.env.example` にも記載）:

```ini
# SQL Server Express（名前付きインスタンス）
DATABASE_URL=mssql+pyodbc://@localhost\SQLEXPRESS/TONOPS-SCH?driver=ODBC+Driver+17+for+SQL+Server

# SQL Server 認証
DATABASE_URL=mssql+pyodbc://USER:PASSWORD@localhost:1433/TONOPS-SCH?driver=ODBC+Driver+17+for+SQL+Server

# ODBC Driver 18（暗号化が既定で必須のため TrustServerCertificate を付ける）
DATABASE_URL=mssql+pyodbc://@localhost/TONOPS-SCH?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
```

`.env` は Git に含めません（`.gitignore` 済み）。パスワードを書く場合も共有しないでください。

### 2.4 DB・テーブル・デモデータの初期設定

```bat
python -m DataBase.setup_database
```

* アプリの接続設定に従い、DBがなければ作成して、未作成のテーブルを追加します。
* 既存のテーブルは変更しません（未作成のテーブルだけ作ります）。
* 共通のデモ拠点名「パン工場」が登録済みの場合は、デモデータの追加をスキップします。
* 拠点は`M_Locations`に作成し、関連テーブルは`LocationID`で紐付けます。手動実行用SQLも同じ定義です。

パン工場に、ミキサー・オーブン・包装機を各2台、製品6件、製品工程18件、実行候補18件、オーダー7件、タスク21件、下書き計画2件を登録します。
標準カレンダーは月〜土の06:00–12:00 / 13:00–18:00、日曜は休みです。
曜日・時間帯ごとの12行を`M_Calendars`に直接登録し、同じ`LocationID`の勤務行をまとめて1つの週次カレンダーとして使います。拠点の`CalendarID`は代表する勤務行を指します。休日・設備停止は、その週次勤務から指定日時を除外します。

下書きの計画名は「各店舗向けパン製造・通常計画」「各店舗向けパン製造・見直し計画」です。
駅前店・中央店・北口店向けの既存オーダーを想定し、両方とも翌日06:00から3日間、計算設定は「パン製造・納期優先」にそろえます。
計画名は同じ拠点内で重複させません。登録直後は計算前の下書きで、割付・評価値は各計画のボードで「計算実行」した後に確認できます。

| 製品名 | オーダーに設定するパンの分類 |
|---|---|
| 食パン | 食事パン |
| バターロール | 食事パン |
| フランスパン | 食事パン |
| あんパン | 菓子パン |
| メロンパン | 菓子パン |
| くるみパン | ナッツ入り |

製品は作るパンそのもの、製品工程は「こねる → 焼く → 包装する」の順に実行する各作業、タスクはオーダーごとの実行対象です。
製品は`M_Product`、製品に直接紐づく工程は`M_ProductProcesses`、工程の実行候補は`M_ProductProcessResources`、オーダーごとのタスクは`T_Tasks`に保存します。
製品コード・単位・製品と工程の属性、および工程ルートの名称・版・既定指定は持ちません。パンの分類属性はオーダーに設定し、タスクへ引き継ぎます。
所要時間は準備＋固定時間＋個数×単位当たり時間で計算し、発酵60分・冷却30分は工程間の待ち時間として表現します。
食パン200個の場合、作業時間はこねる40分、焼く55分、包装する35分です。時間はデモ用の仮設定です。
パン分類によるミキサーの段取り替え、くるみパンの平日製造制約、プラン計算設定「パン製造・納期優先」も登録します。

登録済みのデモデータは更新しません。以前のデモがあるDBでは追加・変更をスキップするため、パン製造デモを新しく登録する場合は新規DBまたはデモ未登録のDBを使ってください。

今回の構成は新規DB用です。この初期設定は既存テーブル・カラムを削除・変換しないため、旧構成のDBは作り直してから実行してください。
SSMSで手動作成する場合は、`DataBase/query/create_database_sqlserver.sql` → `schema_sqlserver.sql` → `seed_demo_sqlserver.sql`の順に実行します。Pythonの初期設定と手動SQLのデータ登録は、どちらか一方を使ってください。
SQLファイルや実行結果のファイル出力は行いません。既存の手動実行用SQLは`DataBase/query`フォルダにあります。

---

## 3. 起動

**API とソルバーワーカーの 2 つのプロセス** を起動します。どちらも `.venv` を有効にしたターミナルで実行します。

### 3.1 API サーバー（ターミナル 1）

```bat
cd %USERPROFILE%\Documents\TONOPS-SCH-backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

* API: http://localhost:8000/api/v1/...
* Swagger UI（API の一覧と試行）: http://localhost:8000/docs
* 死活監視: http://localhost:8000/health

### 3.2 ソルバーワーカー（ターミナル 2）

```bat
cd %USERPROFILE%\Documents\TONOPS-SCH-backend
.venv\Scripts\activate
python -m app.worker
```

画面の「計算実行」は計算依頼を `T_SolverRunResult` に登録するだけで、**実際の計算はワーカーが行います**。
ワーカーが起動していないと、計算は「待機中」のまま進みません（起動すると待機中の依頼から順に処理します）。

### 3.3 フロントエンド

画面を使う場合は [TONOPS-SCH-frontend](https://github.com/tds-dev/TONOPS-SCH-frontend) の README に従って
`npm start` し、http://localhost:4200 を開きます。

---

## 4. 動作確認

### 4.1 画面から

1. **計画一覧** → 仮データの「各店舗向けパン製造・通常計画」を開く。自分で作る場合は「＋ 新しい計画」で重複しない計画名・開始日 = 翌日・06:00・3日を入力 →「作成してボードを開く」
2. **計画ボード** →「計算実行」→ 進捗バーが進み、数十秒で割付が表示される
3. ドラッグで調整 →「承認」→ **配台表** で翌日の作業を確認

### 4.2 Swagger UI から（画面なし）

1. `POST /api/v1/plans`:
   `{"locationId": 1, "horizonStart": "2026-10-28T06:00:00", "horizonEnd": "2026-10-31T06:00:00", "planName": "第44週・計画A"}`
   （オフセットなしの日時は拠点の現地時刻。日付は翌日にしてください）
2. `POST /api/v1/plans/{planId}/solve` に `{"timeLimitSec": 20}`
   （ワーカーなしで試す場合は `{"wait": true}` を付けるとリクエスト内で計算します）
3. `GET /api/v1/solver-runs/{runId}` で `status` が `SUCCEEDED` になるまで確認
4. `GET /api/v1/plans/{planId}/board`、`/kpis`、`/violations` で結果を確認
5. `POST /api/v1/plans/{planId}/approve` → `GET /api/v1/dispatch?locationId=1&date=2026-10-28`

---

## 5. ディレクトリ構成

```
TONOPS-SCH-backend/
├── app/
│   ├── main.py                 FastAPI アプリ（ルーター登録、CORS、/health）
│   ├── worker.py               ソルバーワーカー（T_SolverRunResult をポーリング）
│   ├── core/                   設定（config）、DB エンジン（db）、時刻ユーティリティ（timeutil）
│   ├── models/                 SQLAlchemy モデル
│   │   ├── masters.py          M_* マスタテーブル
│   │   ├── transactions.py     T_* トランザクションテーブル
│   │   ├── base.py             監査列・論理削除列
│   │   └── types.py            列型（SQL Server: NVARCHAR / DATETIME2）
│   ├── schemas/base.py         Pydantic 共通（camelCase の JSON、UTC 日時、CRUD スキーマ自動生成）
│   ├── routers/                REST エンドポイント
│   │   ├── crud.py             マスタ用の汎用 CRUD
│   │   ├── masters.py          マスタの CRUD 登録
│   │   ├── orders.py             オーダー・作業（タスク生成など）
│   │   ├── plans.py            計画・計算・承認・SSE
│   │   └── board.py            計画ボード・手動編集・比較・配台表
│   ├── services/               業務ロジック（計画作成、承認、編集、ボード整形、カレンダー、タスク生成、デモデータ）
│   └── engine/                 スケジューリングエンジン
│       ├── problem.py          ソルバー入力（Problem）の型
│       ├── snapshot.py         DB → Problem
│       ├── model_builder.py    Problem → CP-SAT モデル → 解
│       ├── evaluate.py         割付の検証（違反）と KPI
│       ├── edit.py / compare.py 手動編集・計画比較（純粋関数）
│       ├── solve.py            計算の実行と結果の保存
│       └── rules/              制約ルールのプラグイン
├── DataBase/
│   ├── setup_database.py       DB・テーブルの作成とデモデータ登録
│   └── query/                  SSMSで手動実行するSQL
│       ├── create_database_sqlserver.sql
│       ├── schema_sqlserver.sql
│       └── seed_demo_sqlserver.sql
├── docs/                       設計資料
├── .env.example                設定のひな形
├── requirements.txt
└── pyproject.toml              プロジェクト情報・ruff の設定
```

---

## 6. よく使うコマンド

| 目的 | コマンド |
|---|---|
| API 起動 | `uvicorn app.main:app --reload` |
| ワーカー起動 | `python -m app.worker` |
| DB・テーブルの作成とデモデータ登録 | `python -m DataBase.setup_database` |

---

## 7. トラブルシューティング

Order系へ変更したSQLファイルの内容と実行順は、[DB作成・初期データSQL](docs/DB_SQL.md)を参照してください。

| 症状 | 原因と対処 |
|---|---|
| `IM002 データ ソース名および指定された既定のドライバーが見つかりません` | `.env` の `driver=` の ODBC ドライバーが未インストール。`setup_database` がインストール済みのドライバーを表示するので、そのどれかに変更（空白は `+`） |
| `Login failed` / `Cannot open database` | Windows 認証のユーザーに SQL Server のログイン・権限がない。SSMS でログインを追加するか、SQL Server 認証の URL に変更 |
| `CREATE DATABASE permission denied` | DB 作成権限がない。DBA に空の `TONOPS-SCH` を作ってもらい、`setup_database` を再実行 |
| サーバーが見つからない（タイムアウト） | Express などの名前付きインスタンスは `localhost\SQLEXPRESS` と指定。SQL Server サービスが起動しているか確認 |
| 画面で「計算実行」しても「待機中」のまま | ワーカー（`python -m app.worker`）が起動していない |
| 計算が「失敗」になる | ボードの計算パネルにエラーが出ます。多いのは計画期間が短すぎる・リソース候補がない作業。ワーカーのログも確認 |
| 画面に「サーバーに接続できません」 | API（ポート 8000）が起動していない |
| 初期設定を再実行してもデモデータが追加されない | デモ組織が登録済みなら重複登録を避けるため追加をスキップする |
| 計画を作っても割付対象の作業がない | デモのオーダーは「翌日 06:00 以降」が対象。計画の開始日を翌日にする（初期データを登録した日の翌日） |

---

## 8. 開発の規約

* テーブル名は `M_`（マスタ）/ `T_`（トランザクション）、列名は PascalCase、主キーは `<Entity>ID`、
  監査列 `CreatedAt/By`、`UpdatedAt/By`、論理削除 `DeleteFlag`（工程くんと同じ）。
* 日時は DB に **naive な UTC** で保存。API は `...Z` 形式で返し、入力は任意のオフセットを受け付けます。
  例外: 計画ボード・配台表・計画作成は **アプリ共通の日本時間（Asia/Tokyo、オフセットなし）** でやり取りします。
* API の JSON は camelCase（`resourceName`、`locationId`）。
* 認証は未実装。`CreatedBy` / `UpdatedBy` には `X-User-Email` ヘッダーの値（なければ `system`）を記録します。
* コメント・docstring・メッセージは日本語。
* マイグレーションツール（Alembic）は未導入。既存DBの列追加・改称は別途定義変更が必要です。
