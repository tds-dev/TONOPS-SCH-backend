<!-- アプリの構成、利用手順、APIとDBの対応を説明する資料。 -->
# TONOPS-SCH-backend

> 2026-10-30: プログラムとAPIはOrder/Ordersへ改称。DBもT_Orders・OrderID等へ変更される前提で動作する。実DBの変更は未実施のため、DB側の名称変更後に利用する。既存のSYSTEM_OVERVIEW.md等に記載されたJob名は変更前の構成を含む。現行APIは/api/v1/orders。


TONOPS-SCH（業種に依存しない生産・プロジェクトスケジューラ）のバックエンドです。
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

主なパッケージ: `fastapi`, `uvicorn`, `sqlalchemy`（2.x）, `pydantic`（2.x）, `pyodbc`, `ortools`, `tzdata`, `pytest`。

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

### 2.4 データベースとテーブルの作成

```bat
python -m scripts.create_schema
```

* データベース `TONOPS-SCH` がなければ作成し（`scripts/create_database.py`）、全テーブルを作成します。
* 既存のテーブルは変更しません（未作成のテーブルだけ作ります）。

### 2.5 デモデータの登録（任意）

```bat
python -m scripts.seed_demo
```

工場A（配合 → 充填 → 包装、設備 6 台）、標準カレンダー（月〜土 06:00–12:00 / 13:00–22:00）、
品目 6 件、オーダー 7 件（翌日 06:00 以降が納期）、段取り替えマトリクス、制約ルール 1 件、計画プロファイル「納期優先」を登録します。

### 2.6 作り直し（開発用）

テーブル構成を変えたときやデモデータを入れ直すとき:

```bat
python -m scripts.create_schema --drop
python -m scripts.seed_demo
```

> `--drop` は **TONOPS-SCH の全テーブルのデータを削除** します。本番では使わないでください。

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

画面の「計算実行」は計算依頼を `T_SolverRuns` に登録するだけで、**実際の計算はワーカーが行います**。
ワーカーが起動していないと、計算は「待機中」のまま進みません（起動すると待機中の依頼から順に処理します）。

### 3.3 フロントエンド

画面を使う場合は [TONOPS-SCH-frontend](https://github.com/tds-dev/TONOPS-SCH-frontend) の README に従って
`npm start` し、http://localhost:4200 を開きます。

---

## 4. 動作確認

### 4.1 画面から

1. **計画一覧** →「＋ 新しい計画」（開始日 = 翌日、06:00、3 日）→「作成してボードを開く」
2. **計画ボード** →「計算実行」→ 進捗バーが進み、数十秒で割付が表示される
3. ドラッグで調整 →「承認」→ **配台表** で翌日の作業を確認

### 4.2 Swagger UI から（画面なし）

1. `POST /api/v1/plans`:
   `{"siteId": 1, "horizonStart": "2026-10-28T06:00:00", "horizonEnd": "2026-10-31T06:00:00", "planName": "第44週・計画A"}`
   （オフセットなしの日時は拠点の現地時刻。日付は翌日にしてください）
2. `POST /api/v1/plans/{planId}/solve` に `{"timeLimitSec": 20}`
   （ワーカーなしで試す場合は `{"wait": true}` を付けるとリクエスト内で計算します）
3. `GET /api/v1/solver-runs/{runId}` で `status` が `SUCCEEDED` になるまで確認
4. `GET /api/v1/plans/{planId}/board`、`/kpis`、`/violations` で結果を確認
5. `POST /api/v1/plans/{planId}/approve` → `GET /api/v1/dispatch?siteId=1&date=2026-10-28`

---

## 5. テスト

```bat
pytest
```

* テストは **インメモリの SQLite** を使うため、SQL Server や `TONOPS-SCH` のデータには影響しません。
* エンジン（CP-SAT）のテストは数秒〜数十秒かかります。特定のファイルだけなら `pytest tests\test_worktime.py`。
* コードスタイル: `pip install ruff` → `ruff check .`（設定は `pyproject.toml`）。

| ファイル | 内容 |
|---|---|
| `test_worktime.py` | 稼働時間の展開（シフト、日またぎ、例外、タイムゾーン） |
| `test_evaluate.py` | 割付の検証（重なり、稼働時間外、依存関係、段取り）と KPI |
| `test_engine.py` | CP-SAT モデル（割付、依存、段取り、ロック、ルール） |
| `test_edit_compare.py` | 手動編集の適用・差分、計画比較 |
| `test_api_phase1〜3.py` | API（CRUD、計画・計算、承認・編集・比較・配台表） |

---

## 6. ディレクトリ構成

```
TONOPS-SCH-backend/
├── app/
│   ├── main.py                 FastAPI アプリ（ルーター登録、CORS、/health）
│   ├── worker.py               ソルバーワーカー（T_SolverRuns をポーリング）
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
│   │   ├── orders.py             オーダー・タスク（タスク生成など）
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
├── scripts/
│   ├── create_database.py      DB の作成（なければ）
│   ├── create_schema.py        テーブル作成（--drop で作り直し）
│   ├── seed_demo.py            デモデータ登録
│   └── export_ddl.py           SQL Server 用 DDL を db/schema_sqlserver.sql に出力
├── tests/                      pytest
├── docs/                       設計資料
├── .env.example                設定のひな形
├── requirements.txt
└── pyproject.toml              ruff・pytest の設定
```

---

## 7. よく使うコマンド

| 目的 | コマンド |
|---|---|
| API 起動 | `uvicorn app.main:app --reload` |
| ワーカー起動 | `python -m app.worker` |
| DB・テーブル作成 | `python -m scripts.create_schema` |
| 全テーブル作り直し | `python -m scripts.create_schema --drop` |
| デモデータ登録 | `python -m scripts.seed_demo` |
| DB だけ作成 | `python -m scripts.create_database` |
| DB・テーブル作成SQLの出力（実行はしない） | `python -m scripts.export_ddl` → `db/create_database_sqlserver.sql`、`db/schema_sqlserver.sql` |
| デモデータ挿入SQLの出力（実DBへ接続しない） | `python -m scripts.export_seed_sql` → `db/seed_demo_sqlserver.sql` |
| テスト | `pytest` |

---

## 8. トラブルシューティング

Order系へ変更したSQLファイルの内容と実行順は、[DB作成・初期データSQL](docs/DB_SQL.md)を参照してください。

| 症状 | 原因と対処 |
|---|---|
| `IM002 データ ソース名および指定された既定のドライバーが見つかりません` | `.env` の `driver=` の ODBC ドライバーが未インストール。`create_schema` がインストール済みのドライバーを表示するので、そのどれかに変更（空白は `+`） |
| `Login failed` / `Cannot open database` | Windows 認証のユーザーに SQL Server のログイン・権限がない。SSMS でログインを追加するか、SQL Server 認証の URL に変更 |
| `CREATE DATABASE permission denied` | DB 作成権限がない。DBA に空の `TONOPS-SCH` を作ってもらい、`create_schema` を再実行 |
| サーバーが見つからない（タイムアウト） | Express などの名前付きインスタンスは `localhost\SQLEXPRESS` と指定。SQL Server サービスが起動しているか確認 |
| 画面で「計算実行」しても「待機中」のまま | ワーカー（`python -m app.worker`）が起動していない |
| 計算が「失敗」になる | ボードの計算パネルにエラーが出ます。多いのは計画期間が短すぎる・リソース候補がないタスク。ワーカーのログも確認 |
| 画面に「サーバーに接続できません」 | API（ポート 8000）が起動していない |
| `seed_demo` が「Demo data already present」 | 既に登録済み。入れ直す場合は `create_schema --drop` の後に実行 |
| 計画を作っても割付対象のタスクがない | デモのオーダーは「翌日 06:00 以降」が対象。計画の開始日を翌日にする（`seed_demo` を実行した日の翌日） |

---

## 9. 開発の規約

* テーブル名は `M_`（マスタ）/ `T_`（トランザクション）、列名は PascalCase、主キーは `<Entity>ID`、
  監査列 `CreatedAt/By`、`UpdatedAt/By`、論理削除 `DeleteFlag`（工程くんと同じ）。
* 日時は DB に **naive な UTC** で保存。API は `...Z` 形式で返し、入力は任意のオフセットを受け付けます。
  例外: 計画ボード・配台表・計画作成は **拠点の現地時刻（オフセットなし）** でやり取りします。
* API の JSON は camelCase（`resourceName`、`siteId`）。
* 認証は未実装。`CreatedBy` / `UpdatedBy` には `X-User-Email` ヘッダーの値（なければ `system`）を記録します。
* コメント・docstring・メッセージは日本語。
* マイグレーションツール（Alembic）は未導入。列を追加した場合は当面 `create_schema --drop` で作り直します。
